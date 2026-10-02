"""One-at-a-time sensitivity of the headline results to unsourced assumptions.

Base case: trial-plot returns. Each assumption is moved to a low and a high
value with everything else at base; every point runs the same seeds for both
custody models and all policies (common random numbers), so the measured
changes are not luck. Headline quantities:

  ledger_gain    ledger-history policy vs no-history policy, % gain (custodial)
  targeting_gain risk-aware (no history) vs equal amounts, % gain (custodial)
  custody_cost   self-custody vs custodial, % change in gain (ledger policy)
  fund_left      fund after the last season / initial fund (ledger, custodial)

Output: results/sensitivity_<date>.json, results/fig_tornado.png
"""

import datetime as dt
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

from .model import Config
from .run_simulation import run_replication

REPLICATIONS = 500

# name in Config -> (label, low, high). Ranges: +-50% unless params.yaml states one.
RANGES = {
    "village_shock_sd": ("Village weather shock (sd)", 0.125, 0.375),
    "idiosyncratic_shock_sd": ("Own weather shock (sd)", 0.075, 0.225),
    "saturation_per_ha": ("Saturation of returns (GHS/ha)", 450, 1800),
    "default_target": ("Default rate anchor", 0.10, 0.58),
    "farmer_type_sd": ("Spread of repayment types", 0.5, 1.5),
    "shock_default_sensitivity": ("Default response to weather", 1.0, 3.0),
    "diversion_default_logit": ("Default response to diversion", 0.5, 1.5),
    "capacity_default_logit": ("Default response to capacity", 0.5, 1.5),
    "interest_rate": ("Interest rate", 0.075, 0.225),
    "return_sigma": ("Spread of farmer returns", 0.15, 0.45),
    "loss_cap_share": ("Expected-loss cap", 0.075, 0.225),
    "budget_share": ("Fund size", 0.15, 0.45),
    "diversion_observed": ("On-ledger share of diversion", 0.0, 1.0),
    "leak_custodial": ("Leakage, custodial", 0.025, 0.10),
    "leak_self": ("Leakage, self-custody", 0.15, 0.45),
}

SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
LOW, HIGH = "#2a78d6", "#eb6834"


def configs(sim: dict, name: str | None = None, value: float | None = None) -> tuple[Config, Config]:
    ret = sim["return_scenarios"]["trial_plots"]
    leak_c, leak_s = sim["leakage_by_custody"]["custodial"], sim["leakage_by_custody"]["self_custody"]
    overrides = {}
    if name == "leak_custodial":
        leak_c = value
    elif name == "leak_self":
        leak_s = value
    elif name is not None:
        overrides[name] = value
    return (Config.from_params(sim, ret=ret, leakage=leak_c, **overrides),
            Config.from_params(sim, ret=ret, leakage=leak_s, **overrides))


def headline(pool, sim: dict, name: str | None = None, value: float | None = None) -> dict:
    cust_cfg, self_cfg = configs(sim, name, value)
    cust = list(pool.map(run_replication, [(cust_cfg, s) for s in range(REPLICATIONS)], chunksize=8))
    self_ = list(pool.map(run_replication, [(self_cfg, s) for s in range(REPLICATIONS)], chunksize=8))

    def pct(a, b):
        return float(100 * (np.mean(a) - np.mean(b)) / np.mean(b))

    g = lambda reps, p: np.array([r[p]["gain"] for r in reps])
    return {
        "ledger_gain": pct(g(cust, "ledger"), g(cust, "no_history")),
        "targeting_gain": pct(g(cust, "no_history"), g(cust, "equal")),
        "custody_cost": pct(g(self_, "ledger"), g(cust, "ledger")),
        "fund_left": float(np.nanmean([r["ledger"]["final_fund"] for r in cust])),
    }


def main() -> int:
    sim = yaml.safe_load(Path("params.yaml").read_text())["simulation"]
    out = {"replications": REPLICATIONS, "ranges": {k: v[1:] for k, v in RANGES.items()}}
    with ProcessPoolExecutor() as pool:
        out["base"] = headline(pool, sim)
        print("base", {k: round(v, 2) for k, v in out["base"].items()}, flush=True)
        out["points"] = {}
        for name, (label, lo, hi) in RANGES.items():
            out["points"][name] = {"low": headline(pool, sim, name, lo), "high": headline(pool, sim, name, hi)}
            pts = out["points"][name]
            print(f"{label:<34} " + "  ".join(
                f"{m}: {pts['low'][m]:+.1f}/{pts['high'][m]:+.1f}" for m in out["base"]), flush=True)
    stamp = dt.date.today().isoformat()
    Path("results", f"sensitivity_{stamp}.json").write_text(json.dumps({"date": stamp, **out}, indent=2))
    plot(out, Path("results", "fig_tornado.png"))
    return 0


def plot(out: dict, path: Path) -> None:
    panels = [("ledger_gain", "Ledger history vs no history\n(% more harvest gain, custodial)"),
              ("custody_cost", "Self-custody vs custodial\n(% change in harvest gain)")]
    order = sorted(RANGES, key=lambda n: abs(out["points"][n]["high"]["ledger_gain"] - out["points"][n]["low"]["ledger_gain"]))
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 5.6), facecolor=SURFACE, sharey=True)
    for ax, (metric, title) in zip(axes, panels):
        base = out["base"][metric]
        ax.set_facecolor(SURFACE)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(INK_2)
        ax.tick_params(colors=INK_2, labelsize=8.5, length=0)
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for y, name in enumerate(order):
            lo, hi = out["points"][name]["low"][metric], out["points"][name]["high"][metric]
            ax.barh(y + 0.19, lo - base, left=base, height=0.34, color=LOW, edgecolor=SURFACE, linewidth=1)
            ax.barh(y - 0.19, hi - base, left=base, height=0.34, color=HIGH, edgecolor=SURFACE, linewidth=1)
        ax.axvline(base, color=INK, linewidth=1)
        ax.axvline(0, color=INK_2, linewidth=0.8, linestyle=":")
        ax.set_title(title, fontsize=9.5, color=INK, loc="left")
    axes[0].set_yticks(range(len(order)), [RANGES[n][0] for n in order], color=INK)
    handles = [plt.Rectangle((0, 0), 1, 1, color=LOW), plt.Rectangle((0, 0), 1, 1, color=HIGH)]
    fig.legend(handles, ["Assumption at low value", "Assumption at high value"], frameon=False, fontsize=8.5,
               labelcolor=INK, loc="lower center", ncol=2)
    fig.suptitle("Which assumptions move the headline results? (solid line: base case; dotted: zero)",
                 x=0.02, ha="left", fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(path, dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    sys.exit(main())
