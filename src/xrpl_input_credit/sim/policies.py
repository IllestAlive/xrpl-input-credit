"""Allocation rules and default-risk estimators used inside the simulation.

`greedy_prefix` is a vectorised version of part B's risk-aware greedy: all
one-level increments are ranked by gain / (budget share + lam * loss-cap
share) and taken in order until the budget or the loss cap would be
exceeded. Unlike part B it stops at the first increment that does not fit
instead of skipping it, and it ignores vendor capacity (rarely binding in
part B). That makes it fast enough to run thousands of times.
"""

import warnings

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

LAMBDAS = (0.0, 0.5, 1.0, 2.0, 4.0, 8.0)


def _prefix(order_cost: np.ndarray, order_loss: np.ndarray, budget: float, loss_cap: float) -> int:
    fits = (np.cumsum(order_cost) <= budget + 1e-9) & (np.cumsum(order_loss) <= loss_cap + 1e-9)
    return int(np.argmin(fits)) if not fits.all() else len(fits)


def greedy_prefix(gain: np.ndarray, p_hat: np.ndarray, levels: np.ndarray,
                  budget: float, loss_cap: float) -> np.ndarray:
    n, m1 = gain.shape
    step = levels[1] - levels[0]
    if not np.allclose(np.diff(levels), step):
        raise ValueError("credit levels must be equally spaced")
    if budget < step or loss_cap <= 0:
        return np.zeros(n, dtype=int)
    inc = np.diff(gain, axis=1)                         # (n, m), falling in k
    farmer = np.repeat(np.arange(n), m1 - 1)
    best_level, best_value = np.zeros(n, dtype=int), -np.inf
    for lam in LAMBDAS:
        weight = step / budget + lam * p_hat * step / loss_cap
        order = np.argsort(-(inc / weight[:, None]).ravel(), kind="stable")
        taken = order[:_prefix(np.full(order.size, step), (p_hat * step)[farmer[order]], budget, loss_cap)]
        level = np.bincount(farmer[taken], minlength=n)
        value = gain[np.arange(n), level].sum()
        if value > best_value:
            best_level, best_value = level, value
    return best_level


def equal_amounts(n: int, p_hat: np.ndarray, levels: np.ndarray, budget: float,
                  loss_cap: float, order: np.ndarray) -> np.ndarray:
    affordable = [l for l in range(len(levels)) if levels[l] * n <= budget]
    common = max(affordable) if affordable else 0
    if common == 0:
        common = 1 if budget >= levels[1] else 0  # money for some, not all: first come
    level = np.zeros(n, dtype=int)
    if common:
        x = levels[common]
        k = _prefix(np.full(n, x), p_hat[order] * x, budget, loss_cap)
        level[order[:k]] = common
    return level


class HistoryModel:
    """Logistic regression of default on what the ledger shows about a farmer.

    Features, as of the start of the season the loan was made: number of
    earlier loans, earlier defaults, earlier diversions visible on-ledger,
    and log land. Refit every season on all loans so far.
    """

    def __init__(self, n: int, land: np.ndarray, prior: float):
        self.loans = np.zeros(n)
        self.defaults = np.zeros(n)
        self.observed_div = np.zeros(n)
        self.log_land = np.log(land)
        self.prior = prior
        self.X: list[np.ndarray] = []
        self.y: list[np.ndarray] = []

    def features(self) -> np.ndarray:
        return np.column_stack([self.loans, self.defaults, self.observed_div, self.log_land])

    def predict(self) -> np.ndarray:
        y = np.concatenate(self.y) if self.y else np.empty(0)
        if y.size == 0:
            return np.full(len(self.loans), self.prior)
        if y.min() == y.max():
            return np.full(len(self.loans), y.mean())
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            model = LogisticRegression(C=10.0, max_iter=500).fit(np.vstack(self.X), y)
        return model.predict_proba(self.features())[:, 1]

    def record(self, borrower: np.ndarray, defaulted: np.ndarray, diverted_observed: np.ndarray) -> None:
        self.X.append(self.features()[borrower])
        self.y.append(defaulted[borrower].astype(int))
        self.loans += borrower
        self.defaults += defaulted
        self.observed_div += diverted_observed
