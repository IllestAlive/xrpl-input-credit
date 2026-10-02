"""Individual-based stochastic simulation of a revolving input-credit fund (plan part C).

Farmers are heterogeneous individuals followed over repeated seasons; they do not
optimise or interact strategically, so this is not an agent-based model in the
behavioural sense.

One replication draws a farmer population and every random number it will
ever need (weather, diversion, default, detection) up front. Policies are
then run on the *same* draws: common random numbers, so differences between
policies are not blurred by different luck.

Per season:
  1. the policy allocates credit levels within the fund's capital and a cap
     on expected loss, using its own default-risk estimate p_hat
  2. a loan is diverted (no inputs bought) with probability `leakage`, set by
     the custody model (part A: S4c, S5, S6a)
  3. input credit raises the harvest: r_i * s_i * (1 - exp(-inputs / s_i)),
     scaled by the season's weather (village shock + own shock)
  4. default ~ Bernoulli(sigmoid(alpha + z_i + delta * diverted - gamma * shock
                                 - kappa * (gain / amount due - 1)))
     The last term is repayment capacity: a loan whose inputs pay for
     themselves is easier to repay. alpha is calibrated so that mean default
     equals `default_target` when gain exactly covers the amount due, so the
     realised default rate differs across return scenarios by design.
  5. the fund is repaid principal + interest by non-defaulters
"""

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.optimize import brentq
from scipy.special import expit


@dataclass(frozen=True)
class Config:
    farmers: int
    villages: int
    seasons: int
    land_median_ha: float
    land_sigma: float
    non_responsive_share: float
    credit_levels: np.ndarray
    ret: float                     # return scenario, gross GHS per GHS at x = 0
    return_sigma: float
    saturation_per_ha: float
    village_shock_sd: float
    idiosyncratic_shock_sd: float
    leakage: float
    default_target: float
    farmer_type_sd: float
    shock_default_sensitivity: float
    diversion_default_logit: float
    capacity_default_logit: float
    diversion_observed: float
    interest_rate: float
    budget_share: float
    loss_cap_share: float

    @classmethod
    def from_params(cls, sim: dict, ret: float, leakage: float, **overrides) -> "Config":
        cfg = dict(
            farmers=sim["farmers"], villages=sim["villages"], seasons=sim["seasons"],
            land_median_ha=sim["land_median_ha"], land_sigma=sim["land_sigma"],
            non_responsive_share=sim["non_responsive_share"],
            credit_levels=np.asarray(sim["credit_levels_ghs"], dtype=float),
            ret=ret, return_sigma=sim["return_sigma"], saturation_per_ha=sim["saturation_ghs_per_ha"],
            village_shock_sd=sim["village_shock_sd"], idiosyncratic_shock_sd=sim["idiosyncratic_shock_sd"],
            leakage=leakage, default_target=sim["default_target"], farmer_type_sd=sim["farmer_type_sd"],
            shock_default_sensitivity=sim["shock_default_sensitivity"],
            diversion_default_logit=sim["diversion_default_logit"],
            capacity_default_logit=sim["capacity_default_logit"],
            diversion_observed=sim["diversion_observed_on_ledger"], interest_rate=sim["interest_rate"],
            budget_share=sim["budget_share"], loss_cap_share=sim["loss_cap_share"],
        )
        cfg.update(overrides)
        return cls(**cfg)

    @property
    def initial_fund(self) -> float:
        return self.budget_share * self.farmers * self.credit_levels[-1]

    @property
    def alpha(self) -> float:
        return calibrate_alpha(self.default_target, self.farmer_type_sd, self.shock_default_sensitivity,
                               float(np.hypot(self.village_shock_sd, self.idiosyncratic_shock_sd)))


@lru_cache(maxsize=None)
def calibrate_alpha(target: float, type_sd: float, gamma: float, shock_sd: float) -> float:
    """Intercept such that mean default, without diversion, equals `target`."""
    rng = np.random.default_rng(12345)
    latent = rng.normal(0, type_sd, 200_000) - gamma * rng.normal(0, shock_sd, 200_000)
    return brentq(lambda a: expit(a + latent).mean() - target, -20, 20)


@dataclass(frozen=True)
class World:
    """Population and all random draws for one replication."""
    land: np.ndarray        # (n,)
    ret: np.ndarray         # (n,) farmer's own return; 0 if non-responsive
    saturation: np.ndarray  # (n,)
    z: np.ndarray           # (n,) unobserved repayment type
    shock: np.ndarray       # (T, n) log-yield shock
    u_divert: np.ndarray    # (T, n)
    u_default: np.ndarray   # (T, n)
    u_observe: np.ndarray   # (T, n)


def draw_world(cfg: Config, seed: int) -> World:
    rng = np.random.default_rng(seed)
    n, T = cfg.farmers, cfg.seasons
    land = np.clip(rng.lognormal(np.log(cfg.land_median_ha), cfg.land_sigma, n), 0.1, 50)
    responsive = rng.random(n) >= cfg.non_responsive_share
    s = cfg.return_sigma
    ret = cfg.ret * rng.lognormal(-s * s / 2, s, n) * responsive
    village = rng.integers(0, cfg.villages, n)
    shock = (rng.normal(0, cfg.village_shock_sd, (T, cfg.villages))[:, village]
             + rng.normal(0, cfg.idiosyncratic_shock_sd, (T, n)))
    return World(
        land=land, ret=ret, saturation=cfg.saturation_per_ha * land,
        z=rng.normal(0, cfg.farmer_type_sd, n), shock=shock,
        u_divert=rng.random((T, n)), u_default=rng.random((T, n)), u_observe=rng.random((T, n)),
    )


def expected_gain_table(cfg: Config, w: World) -> np.ndarray:
    """What the lender expects from each level: average return, known land, known leakage."""
    x = cfg.credit_levels[None, :]
    sat = w.saturation[:, None]
    return cfg.ret * sat * (1 - np.exp(-x / sat)) * (1 - cfg.leakage)


def known_type_prob(cfg: Config, w: World) -> np.ndarray:
    """Default risk from the farmer's type and the custody model only.

    Weather is averaged out and repayment capacity is left at its calibration
    point, so this is what a lender who knew every farmer's z would use. It is
    a benchmark for the value of information, not the true realised risk.
    """
    a = cfg.alpha
    return (cfg.leakage * expit(a + w.z + cfg.diversion_default_logit)
            + (1 - cfg.leakage) * expit(a + w.z))


@dataclass
class SeasonOutcome:
    level: np.ndarray
    lent: float
    repaid: float
    gain: float
    loans: int
    defaults: int
    defaulted: np.ndarray
    diverted_observed: np.ndarray


def realise(cfg: Config, w: World, t: int, level: np.ndarray) -> SeasonOutcome:
    x = cfg.credit_levels[level]
    borrower = x > 0
    diverted = borrower & (w.u_divert[t] < cfg.leakage)
    inputs = np.where(diverted, 0.0, x)
    gain = w.ret * w.saturation * (1 - np.exp(-inputs / w.saturation)) * np.exp(w.shock[t])
    due = x * (1 + cfg.interest_rate)
    capacity = np.clip(np.divide(gain, due, out=np.ones_like(due), where=due > 0) - 1, -1, 3)
    p = expit(cfg.alpha + w.z + cfg.diversion_default_logit * diverted
              - cfg.shock_default_sensitivity * w.shock[t] - cfg.capacity_default_logit * capacity)
    defaulted = borrower & (w.u_default[t] < p)
    repaid = due[borrower & ~defaulted].sum()
    return SeasonOutcome(level, x.sum(), repaid, gain.sum(), int(borrower.sum()), int(defaulted.sum()),
                         defaulted, diverted & (w.u_observe[t] < cfg.diversion_observed))
