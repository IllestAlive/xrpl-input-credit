import itertools

import numpy as np
import pytest

from xrpl_input_credit.model.allocation import (
    feasible, greedy, greedy_risk, land, milp, objective, random_alloc, uniform,
)
from xrpl_input_credit.model.instance import load_params, synthetic


def small(seed: int):
    prm = load_params() | {"farmers": 6, "villages": 3, "vendors": 2, "levels": [0, 50, 100, 150]}
    return synthetic(seed, prm)


def brute_force_optimum(inst) -> float:
    best = 0.0
    for combo in itertools.product(range(len(inst.levels)), repeat=inst.n):
        level = np.array(combo)
        if feasible(inst, level):
            best = max(best, objective(inst, level))
    return best


@pytest.mark.parametrize("seed", range(5))
def test_milp_matches_brute_force(seed):
    inst = small(seed)
    assert milp(inst).objective == pytest.approx(brute_force_optimum(inst), rel=1e-9)


@pytest.mark.parametrize("seed", range(5))
def test_heuristics_feasible_and_bounded_by_optimum(seed):
    inst = small(seed)
    rng = np.random.default_rng(seed)
    best = milp(inst).objective
    for result in (greedy(inst), greedy_risk(inst), uniform(inst, rng), land(inst), random_alloc(inst, rng)):
        assert feasible(inst, result.level)
        assert result.objective <= best + 1e-9


def test_synthetic_gains_concave_in_levels():
    inst = synthetic(0)
    increments = np.diff(inst.gain, axis=1)
    assert (increments > 0).all()
    assert (np.diff(increments, axis=1) < 0).all()


def test_risk_aware_greedy_never_worse_than_budget_only():
    # lam = 0 is in the grid, so the risk-aware variant can only match or improve.
    for seed in range(3):
        inst = synthetic(seed)
        assert greedy_risk(inst).objective >= greedy(inst).objective - 1e-9
