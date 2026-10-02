"""Allocation methods for an Instance. Each returns a level index per farmer.

  milp      exact optimum (HiGHS via scipy.optimize.milp)
  greedy    incremental: repeatedly raise the farmer with the best marginal
            gain per unit of budget by one level, skipping steps that would
            break any constraint. Valid as a heuristic because gains are
            concave in equally spaced levels, so each farmer's ratios fall.
            Blind to default risk: it spends the loss cap on whoever is next.
  greedy_risk  the same, but a step's cost is its share of the budget plus
            lam times its share of the loss cap; lam is chosen from a grid
            and the best feasible result is kept (a Lagrangian-style weighting
            of the two shared resources).
  uniform   one common level, assigned in random order while feasible
  land      level proportional to the farmer's maximum gain (a land proxy)
  random    random level per farmer, random order, while feasible
"""

import contextlib
import ctypes
import heapq
import os
import time
from dataclasses import dataclass

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp as scipy_milp
from scipy.sparse import coo_matrix

from .instance import Instance


@dataclass
class Result:
    method: str
    level: np.ndarray
    objective: float
    seconds: float
    note: str = ""


def usage(inst: Instance, level: np.ndarray) -> tuple[float, float, np.ndarray]:
    x = inst.levels[level]
    return x.sum(), (inst.p * x).sum(), np.bincount(inst.vendor, weights=x, minlength=len(inst.vendor_cap))


def objective(inst: Instance, level: np.ndarray) -> float:
    return float(inst.gain[np.arange(inst.n), level].sum())


def feasible(inst: Instance, level: np.ndarray, tol: float = 1e-6) -> bool:
    spent, loss, per_vendor = usage(inst, level)
    return spent <= inst.budget + tol and loss <= inst.loss_cap + tol and bool((per_vendor <= inst.vendor_cap + tol).all())


def _timed(method: str, inst: Instance, fn, note: str = "") -> Result:
    start = time.perf_counter()
    level = fn()
    seconds = time.perf_counter() - start
    if not feasible(inst, level):
        raise AssertionError(f"{method} returned an infeasible allocation")
    return Result(method, level, objective(inst, level), seconds, note)


@contextlib.contextmanager
def _quiet_native_output():
    """HiGHS writes debug lines straight to the process's fds; silence them during a solve."""
    saved = {fd: os.dup(fd) for fd in (1, 2)}
    with open(os.devnull, "w") as devnull:
        for fd in saved:
            os.dup2(devnull.fileno(), fd)
        try:
            yield
        finally:
            ctypes.CDLL(None).fflush(None)  # flush C-level buffers while they still point at devnull
            for fd, copy in saved.items():
                os.dup2(copy, fd)
                os.close(copy)


def milp(inst: Instance, time_limit: float = 120.0) -> Result:
    n, m = inst.n, len(inst.levels) - 1
    note = ""

    def solve() -> np.ndarray:
        nonlocal note
        # y[i, l] = 1 if farmer i gets level l (l = 1..m), flattened as i * m + (l - 1).
        cols = np.arange(n * m)
        farmer = cols // m
        x = np.tile(inst.levels[1:], n)
        rows, data = [], []
        rows.append(farmer); data.append(np.ones(n * m))                           # at most one level
        rows.append(np.full(n * m, n)); data.append(x)                              # budget
        rows.append(np.full(n * m, n + 1)); data.append(inst.p[farmer] * x)         # expected loss
        rows.append(n + 2 + inst.vendor[farmer]); data.append(x)                    # vendor capacity
        r, d = np.concatenate(rows), np.concatenate(data)
        c = np.concatenate([cols] * 4)
        A = coo_matrix((d, (r, c)), shape=(n + 2 + len(inst.vendor_cap), n * m)).tocsr()
        ub = np.concatenate([np.ones(n), [inst.budget, inst.loss_cap], inst.vendor_cap])
        with _quiet_native_output():
            res = scipy_milp(
                c=-inst.gain[:, 1:].ravel(),
                constraints=LinearConstraint(A, -np.inf, ub),
                integrality=np.ones(n * m),
                bounds=Bounds(0, 1),
                options={"time_limit": time_limit, "mip_rel_gap": 1e-9},
            )
        if res.x is None:
            raise RuntimeError(f"MILP failed: {res.message}")
        note = f"status={res.status}, mip_gap={getattr(res, 'mip_gap', float('nan')):.2e}"
        y = res.x.reshape(n, m).round()
        return np.where(y.any(axis=1), y.argmax(axis=1) + 1, 0)

    result = _timed("milp", inst, solve)
    result.note = note
    return result


def _greedy_levels(inst: Instance, lam: float) -> np.ndarray:
    level = np.zeros(inst.n, dtype=int)
    step = inst.levels[1] - inst.levels[0]
    # Cost of one step for farmer i, in shares of the two shared resources.
    weight = step / inst.budget + lam * inst.p * step / inst.loss_cap
    spent, loss = 0.0, 0.0
    per_vendor = np.zeros(len(inst.vendor_cap))
    heap = [(-(inst.gain[i, 1] - inst.gain[i, 0]) / weight[i], i) for i in range(inst.n)]
    heapq.heapify(heap)
    while heap:
        _, i = heapq.heappop(heap)
        v, extra_loss = inst.vendor[i], inst.p[i] * step
        if (spent + step > inst.budget or loss + extra_loss > inst.loss_cap
                or per_vendor[v] + step > inst.vendor_cap[v]):
            continue  # resources only shrink, so this farmer can never be raised again
        level[i] += 1
        spent, loss, per_vendor[v] = spent + step, loss + extra_loss, per_vendor[v] + step
        if level[i] < len(inst.levels) - 1:
            ratio = (inst.gain[i, level[i] + 1] - inst.gain[i, level[i]]) / weight[i]
            heapq.heappush(heap, (-ratio, i))
    return level


def greedy(inst: Instance) -> Result:
    return _timed("greedy", inst, lambda: _greedy_levels(inst, lam=0.0))


LAMBDA_GRID = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0)


def greedy_risk(inst: Instance) -> Result:
    chosen = {}

    def solve() -> np.ndarray:
        candidates = [(objective(inst, lv), lam, lv) for lam in LAMBDA_GRID
                      for lv in [_greedy_levels(inst, lam)]]
        best = max(candidates, key=lambda c: c[0])
        chosen["lam"] = best[1]
        return best[2]

    result = _timed("greedy_risk", inst, solve)
    result.note = f"lam={chosen['lam']}"
    return result


def _fill(inst: Instance, order: np.ndarray, wanted: np.ndarray) -> np.ndarray:
    """Give each farmer, in order, the highest level <= wanted that still fits."""
    level = np.zeros(inst.n, dtype=int)
    spent, loss = 0.0, 0.0
    per_vendor = np.zeros(len(inst.vendor_cap))
    for i in order:
        v = inst.vendor[i]
        for l in range(wanted[i], 0, -1):
            x = inst.levels[l]
            if spent + x <= inst.budget and loss + inst.p[i] * x <= inst.loss_cap and per_vendor[v] + x <= inst.vendor_cap[v]:
                level[i], spent, loss, per_vendor[v] = l, spent + x, loss + inst.p[i] * x, per_vendor[v] + x
                break
    return level


def uniform(inst: Instance, rng: np.random.Generator) -> Result:
    def solve() -> np.ndarray:
        common = max((l for l in range(len(inst.levels)) if inst.levels[l] * inst.n <= inst.budget), default=0)
        return _fill(inst, rng.permutation(inst.n), np.full(inst.n, common))

    return _timed("uniform", inst, solve)


def land(inst: Instance) -> Result:
    def solve() -> np.ndarray:
        size = inst.gain[:, -1]  # saturating gain scales with land
        target = inst.budget * size / size.sum()
        wanted = np.clip(np.searchsorted(inst.levels, target, side="right") - 1, 0, len(inst.levels) - 1)
        return _fill(inst, np.argsort(-size), wanted)

    return _timed("land", inst, solve)


def random_alloc(inst: Instance, rng: np.random.Generator) -> Result:
    def solve() -> np.ndarray:
        return _fill(inst, rng.permutation(inst.n), rng.integers(0, len(inst.levels), inst.n))

    return _timed("random", inst, solve)
