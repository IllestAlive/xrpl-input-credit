"""Part B experiments: how far are the heuristics from the exact optimum?

1. Gap: 20 synthetic instances (seeds 0-19); each method's objective as a
   share of the MILP optimum on the same instance.
2. Frontier: on instance 0, sweep the expected-loss cap and solve exactly and
   greedily at each point (expected gain vs. tolerated expected loss).

Output: results/allocation_<date>.json, results/fig_gap.png, results/fig_frontier.png
"""

import datetime as dt
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .allocation import greedy, greedy_risk, land, milp, random_alloc, uniform, usage
from .instance import synthetic

SEEDS = range(20)
RANDOM_DRAWS = 200
LOSS_CAP_SHARES = np.linspace(0.02, 0.24, 12)

# Reference palette (dataviz skill, light mode), validated for these two slots.
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]


def gap_experiment() -> list[dict]:
    rows = []
    for seed in SEEDS:
        inst = synthetic(seed)
        rng = np.random.default_rng(1000 + seed)
        exact = milp(inst)
        spent, loss, per_vendor = usage(inst, exact.level)
        draws = [random_alloc(inst, rng).objective for _ in range(RANDOM_DRAWS)]
        others = {r.method: r for r in (greedy(inst), greedy_risk(inst), uniform(inst, rng), land(inst))}
        rows.append({
            "seed": seed,
            "milp_objective": exact.objective,
            "milp_seconds": exact.seconds,
            "milp_note": exact.note,
            "binding": {
                "budget": bool(spent >= inst.budget - 1e-6),
                "loss": bool(loss >= inst.loss_cap * (1 - 1e-3)),
                "vendors_at_cap": int((per_vendor >= inst.vendor_cap - 1e-6).sum()),
            },
            "share_of_optimum": {
                **{name: r.objective / exact.objective for name, r in others.items()},
                "random (mean of 200)": float(np.mean(draws)) / exact.objective,
                "random (best of 200)": float(np.max(draws)) / exact.objective,
            },
            "greedy_seconds": others["greedy"].seconds,
            "greedy_risk_seconds": others["greedy_risk"].seconds,
            "greedy_risk_lambda": others["greedy_risk"].note,
        })
    return rows


def frontier_experiment() -> list[dict]:
    base = synthetic(0)
    points = []
    for share in LOSS_CAP_SHARES:
        inst = base.with_loss_cap(share * base.budget)
        points.append({"loss_cap_share": float(share),
                       "milp": milp(inst).objective,
                       "greedy": greedy(inst).objective,
                       "greedy_risk": greedy_risk(inst).objective})
    return points


def style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(INK_2)
    ax.tick_params(colors=INK_2, labelsize=9, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


LABELS = {
    "greedy_risk": "Risk-aware greedy",
    "greedy": "Budget-only greedy",
    "uniform": "Equal amounts",
    "land": "Proportional to farm size",
    "random (best of 200)": "Random (best of 200)",
    "random (mean of 200)": "Random (mean of 200)",
}


def plot_gap(rows: list[dict], path: Path) -> None:
    methods = list(rows[0]["share_of_optimum"])
    shares = {m: 100 * np.array([r["share_of_optimum"][m] for r in rows]) for m in methods}
    methods.sort(key=lambda m: np.median(shares[m]))
    fig, ax = plt.subplots(figsize=(7.2, 3.6), facecolor=SURFACE)
    style(ax)
    for y, m in enumerate(methods):
        lo, med, hi = shares[m].min(), np.median(shares[m]), shares[m].max()
        ax.plot([lo, hi], [y, y], color=SERIES[0], linewidth=2, solid_capstyle="round")
        ax.plot(med, y, "o", color=SERIES[0], markersize=7, markeredgecolor=SURFACE, markeredgewidth=1.5)
        ax.text(hi + 0.6, y, f"{med:.1f}%", va="center", fontsize=9, color=INK)
    ax.set_yticks(range(len(methods)), [LABELS[m] for m in methods], color=INK)
    ax.set_xlabel("Expected gain, % of exact optimum (dot: median, line: min–max over 20 instances)",
                  fontsize=9, color=INK_2)
    ax.set_xlim(right=106)
    fig.suptitle("With the loss cap binding, only risk-aware greedy\ngets close to the optimum",
                 x=0.02, ha="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def plot_frontier(points: list[dict], path: Path) -> None:
    x = 100 * np.array([p["loss_cap_share"] for p in points])
    fig, ax = plt.subplots(figsize=(7.2, 3.8), facecolor=SURFACE)
    style(ax)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    for color, key, label in ((SERIES[0], "milp", "Exact (MILP)"), (SERIES[2], "greedy_risk", "Risk-aware greedy"),
                              (SERIES[1], "greedy", "Budget-only greedy")):
        y = np.array([p[key] for p in points]) / 1000
        ax.plot(x, y, color=color, linewidth=2, marker="o", markersize=5, label=label,
                markeredgecolor=SURFACE, markeredgewidth=1)
    ax.set_xlabel("Expected-loss cap, % of budget", fontsize=9, color=INK_2)
    ax.set_ylabel("Expected gain (thousand units)", fontsize=9, color=INK_2)
    ax.set_ylim(bottom=0)
    ax.annotate("exact and risk-aware greedy overlap", xy=(6, 49), xytext=(2, 70),
                fontsize=9, color=INK_2, arrowprops={"arrowstyle": "-", "color": INK_2, "linewidth": 0.8})
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="lower right")
    fig.suptitle("Budget-only greedy loses ground exactly where the loss cap is tight\n(instance 0)",
                 x=0.02, ha="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def main() -> int:
    rows, points = gap_experiment(), frontier_experiment()
    stamp = dt.date.today().isoformat()
    out = Path("results")
    (out / f"allocation_{stamp}.json").write_text(json.dumps(
        {"date": stamp, "instances": rows, "frontier": points}, indent=2))
    plot_gap(rows, out / "fig_gap.png")
    plot_frontier(points, out / "fig_frontier.png")

    print(f"{'method':<22} {'median':>8} {'min':>8} {'max':>8}   (% of optimum, {len(rows)} instances)")
    for m in rows[0]["share_of_optimum"]:
        s = 100 * np.array([r["share_of_optimum"][m] for r in rows])
        print(f"{m:<22} {np.median(s):8.2f} {s.min():8.2f} {s.max():8.2f}")
    secs = np.array([r["milp_seconds"] for r in rows])
    print(f"MILP seconds: median {np.median(secs):.2f}, max {secs.max():.2f}; notes: {sorted({r['milp_note'] for r in rows})}")
    print(f"binding: budget {sum(r['binding']['budget'] for r in rows)}/20, "
          f"loss {sum(r['binding']['loss'] for r in rows)}/20, "
          f"vendors at cap (mean) {np.mean([r['binding']['vendors_at_cap'] for r in rows]):.1f}")
    print("frontier (cap share, greedy/opt, risk-greedy/opt):",
          [(round(p["loss_cap_share"], 2), round(p["greedy"] / p["milp"], 3), round(p["greedy_risk"] / p["milp"], 3))
           for p in points])
    print("risk-greedy lambdas:", sorted({r["greedy_risk_lambda"] for r in rows}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
