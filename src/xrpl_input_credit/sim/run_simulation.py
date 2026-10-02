"""Part C: revolving fund over several seasons, policies compared on common draws.

Scenarios: return {rct_like, trial_plots, naive_agronomic} x custody
{custodial, self_custody}. Policies:
  equal        equal amounts, random order, mean risk
  no_history   risk-aware greedy, one pooled default rate for everyone
  ledger       risk-aware greedy, default risk from a model on ledger history
  known_type   risk-aware greedy, knowing each farmer's repayment type
               (benchmark for the value of information, not attainable)

Output: results/simulation_<date>.json
"""

import argparse
import datetime as dt
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import yaml

from .model import Config, draw_world, expected_gain_table, realise, known_type_prob
from .policies import HistoryModel, equal_amounts, greedy_prefix

POLICIES = ("equal", "no_history", "ledger", "known_type")


def run_policy(cfg: Config, seed: int, policy: str) -> dict:
    w = draw_world(cfg, seed)
    order = np.random.default_rng(seed + 10**6).permutation(cfg.farmers)
    gain_table = expected_gain_table(cfg, w)
    history = HistoryModel(cfg.farmers, w.land, prior=cfg.default_target)
    type_p = known_type_prob(cfg, w)
    capital = cfg.initial_fund
    pooled_loans = pooled_defaults = 0
    total_gain = loans = defaults = 0.0
    for t in range(cfg.seasons):
        if policy == "known_type":
            p_hat = type_p
        elif policy == "ledger":
            p_hat = history.predict()
        else:
            rate = pooled_defaults / pooled_loans if pooled_loans else cfg.default_target
            p_hat = np.full(cfg.farmers, rate)
        loss_cap = cfg.loss_cap_share * capital
        if policy == "equal":
            level = equal_amounts(cfg.farmers, p_hat, cfg.credit_levels, capital, loss_cap, order)
        else:
            level = greedy_prefix(gain_table, p_hat, cfg.credit_levels, capital, loss_cap)
        out = realise(cfg, w, t, level)
        capital += out.repaid - out.lent
        total_gain += out.gain
        loans += out.loans
        defaults += out.defaults
        pooled_loans += out.loans
        pooled_defaults += out.defaults
        history.record(level > 0, out.defaulted, out.diverted_observed)
    return {"gain": total_gain, "default_rate": defaults / loans if loans else np.nan,
            "loans": loans, "final_fund": capital / cfg.initial_fund if cfg.initial_fund else np.nan}


def run_replication(args) -> dict:
    cfg, seed = args
    return {p: run_policy(cfg, seed, p) for p in POLICIES}


def summarise(reps: list[dict]) -> dict:
    out = {}
    for p in POLICIES:
        out[p] = {}
        for metric in ("gain", "default_rate", "final_fund", "loans"):
            v = np.array([r[p][metric] for r in reps], dtype=float)
            out[p][metric] = {"mean": float(np.nanmean(v)),
                              "ci95": float(1.96 * np.nanstd(v, ddof=1) / np.sqrt(np.sum(~np.isnan(v))))}
    # Paired differences in total gain (common random numbers make these tight).
    def paired(a, b):
        d = np.array([r[a]["gain"] - r[b]["gain"] for r in reps])
        base = np.mean([r[b]["gain"] for r in reps])
        return {"mean": float(d.mean()), "ci95": float(1.96 * d.std(ddof=1) / np.sqrt(len(d))),
                "pct_of_baseline": float(100 * d.mean() / base) if base else float("nan")}
    out["paired_gain"] = {
        "no_history_vs_equal": paired("no_history", "equal"),
        "ledger_vs_no_history": paired("ledger", "no_history"),
        "known_type_vs_no_history": paired("known_type", "no_history"),
    }
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replications", type=int)
    args = parser.parse_args()
    sim = yaml.safe_load(Path("params.yaml").read_text())["simulation"]
    reps = args.replications or sim["replications"]

    results, start = {}, time.perf_counter()
    with ProcessPoolExecutor() as pool:
        for ret_name, ret in sim["return_scenarios"].items():
            for custody, leakage in sim["leakage_by_custody"].items():
                cfg = Config.from_params(sim, ret=ret, leakage=leakage)
                rows = list(pool.map(run_replication, [(cfg, seed) for seed in range(reps)], chunksize=8))
                key = f"{ret_name}/{custody}"
                results[key] = summarise(rows)
                s = results[key]
                print(f"{key:<30} " + "  ".join(
                    f"{p}: gain {s[p]['gain']['mean'] / 1e3:7.0f}k def {s[p]['default_rate']['mean']:.3f} "
                    f"fund {s[p]['final_fund']['mean']:.2f}" for p in POLICIES), flush=True)
    stamp = dt.date.today().isoformat()
    Path("results", f"simulation_{stamp}.json").write_text(json.dumps(
        {"date": stamp, "replications": reps, "results": results}, indent=2))
    print(f"{reps} replications x {len(results)} scenarios in {time.perf_counter() - start:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
