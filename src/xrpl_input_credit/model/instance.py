"""Allocation problem instances.

A farmer receives one credit level from a fixed menu (0 included). Choosing
level l for farmer i yields expected gain G[i, l], costs levels[l] of the
budget and adds p[i] * levels[l] to expected loss. Each farmer buys inputs
from one vendor, whose capacity bounds the credit routed to it.

The synthetic generator below uses placeholder parameters (params.yaml,
`allocation_synthetic`); they are assumptions, not estimates, and are
replaced with literature-sourced values on days 6-8.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml


@dataclass(frozen=True)
class Instance:
    levels: np.ndarray      # (m+1,) credit amounts, levels[0] == 0, equally spaced
    gain: np.ndarray        # (n, m+1) expected gain, gain[:, 0] == 0, concave in l
    p: np.ndarray           # (n,) default probability
    vendor: np.ndarray      # (n,) vendor index of each farmer
    vendor_cap: np.ndarray  # (V,) credit capacity per vendor
    budget: float
    loss_cap: float         # bound on expected loss sum(p_i * x_i)

    @property
    def n(self) -> int:
        return len(self.p)

    def with_loss_cap(self, loss_cap: float) -> "Instance":
        return Instance(self.levels, self.gain, self.p, self.vendor, self.vendor_cap, self.budget, loss_cap)


def load_params(path: Path = Path("params.yaml")) -> dict:
    return yaml.safe_load(path.read_text())["allocation_synthetic"]


def synthetic(seed: int, params: dict | None = None) -> Instance:
    """Heterogeneous farmers with saturating (concave) returns to input credit."""
    prm = params or load_params()
    rng = np.random.default_rng(seed)
    n, villages, vendors = prm["farmers"], prm["villages"], prm["vendors"]
    levels = np.asarray(prm["levels"], dtype=float)

    land = rng.lognormal(np.log(prm["land_median_ha"]), prm["land_sigma"], n)
    ret = rng.lognormal(np.log(prm["initial_return"]), prm["return_sigma"], n)
    saturation = prm["saturation_per_ha"] * land
    # gain(x) = r * s * (1 - exp(-x / s)): slope r at x = 0, flattening at x ~ s.
    gain = ret[:, None] * saturation[:, None] * (1 - np.exp(-levels[None, :] / saturation[:, None]))
    p = rng.beta(prm["default_beta_a"], prm["default_beta_b"], n)

    village = rng.integers(0, villages, n)
    vendor = village % vendors
    budget = prm["budget_share"] * n * levels[-1]
    vendor_cap = np.full(vendors, prm["vendor_cap_slack"] * budget / vendors)
    return Instance(levels, gain, p, vendor, vendor_cap, budget, prm["loss_cap_share"] * budget)
