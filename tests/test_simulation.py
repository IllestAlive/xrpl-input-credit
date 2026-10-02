from dataclasses import replace

import numpy as np
import pytest
import yaml
from scipy.special import expit

from xrpl_input_credit.sim.model import Config, calibrate_alpha, draw_world
from xrpl_input_credit.sim.policies import equal_amounts, greedy_prefix
from xrpl_input_credit.sim.run_simulation import POLICIES, run_policy


@pytest.fixture(scope="module")
def cfg() -> Config:
    sim = yaml.safe_load(open("params.yaml"))["simulation"]
    return Config.from_params(sim, ret=3.58, leakage=0.05, farmers=200, villages=5)


def test_common_random_numbers_make_runs_reproducible(cfg):
    for policy in POLICIES:
        assert run_policy(cfg, 7, policy) == run_policy(cfg, 7, policy)


def test_alpha_hits_target_default_at_calibration_point(cfg):
    a = calibrate_alpha(0.25, 1.0, 2.0, 0.3)
    rng = np.random.default_rng(0)
    latent = rng.normal(0, 1.0, 400_000) - 2.0 * rng.normal(0, 0.3, 400_000)
    assert expit(a + latent).mean() == pytest.approx(0.25, abs=0.003)


def test_no_fund_means_no_loans_and_no_gain(cfg):
    out = run_policy(replace(cfg, budget_share=0.0), 1, "ledger")
    assert out["loans"] == 0 and out["gain"] == 0


def test_full_diversion_means_no_gain(cfg):
    assert run_policy(replace(cfg, leakage=1.0), 1, "no_history")["gain"] == 0


@pytest.mark.parametrize("seed", range(5))
def test_allocations_respect_budget_and_loss_cap(cfg, seed):
    rng = np.random.default_rng(seed)
    n, levels = 300, cfg.credit_levels
    sat = rng.uniform(200, 2000, n)[:, None]
    gain = 2.0 * sat * (1 - np.exp(-levels[None, :] / sat))
    p = rng.uniform(0.05, 0.6, n)
    budget, loss_cap = 0.3 * n * levels[-1], 0.15 * 0.3 * n * levels[-1]
    for level in (greedy_prefix(gain, p, levels, budget, loss_cap),
                  equal_amounts(n, p, levels, budget, loss_cap, rng.permutation(n))):
        x = levels[level]
        assert x.sum() <= budget + 1e-6
        assert (p * x).sum() <= loss_cap + 1e-6
