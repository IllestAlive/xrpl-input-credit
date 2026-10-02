"""Assemble web/data.json from results/*.json for the static results explorer.

The page shows only numbers computed by the analysis; nothing is recomputed
or interpolated in the browser. Run from the repository root:
    uv run python web/build_data.py
"""

import json
from pathlib import Path

import numpy as np
import yaml

from xrpl_input_credit.sim.sensitivity import RANGES

R = Path("results")
DATE = "2026-10-02"
load = lambda name: json.loads((R / f"{name}_{DATE}.json").read_text())
enf, alloc, sim, risk, sens = (load(n) for n in ("enforcement", "allocation", "simulation", "risk", "sensitivity"))
params = yaml.safe_load(Path("params.yaml").read_text())

METHODS = {"greedy_risk": "Risk-aware greedy, λ searched", "greedy_fixed": "Risk-aware greedy, λ fixed",
           "greedy": "Budget-only greedy", "uniform": "Equal amounts",
           "land": "Proportional to farm size", "random (best of 200)": "Random, best of 200",
           "random (mean of 200)": "Random, mean of 200"}
gap = []
for key, label in METHODS.items():
    s = 100 * np.array([r["share_of_optimum"][key] for r in alloc["instances"]])
    gap.append({"method": label, "median": round(float(np.median(s)), 2),
                "min": round(float(s.min()), 2), "max": round(float(s.max()), 2)})

scenarios = {}
for key, v in sim["results"].items():
    scenarios[key] = {
        "policies": {p: {"gain": v[p]["gain"]["mean"], "gain_ci": v[p]["gain"]["ci95"],
                         "default_rate": v[p]["default_rate"]["mean"], "final_fund": v[p]["final_fund"]["mean"]}
                     for p in ("equal", "no_history", "ledger", "known_type")},
        "paired": {k: {"pct": d["pct_of_baseline"], "ci_pct": 100 * d["ci95"] / (d["mean"] / d["pct_of_baseline"] * 100)}
                   for k, d in v["paired_gain"].items()},
    }

auc = {}
for key, ev in risk["evaluation"].items():
    auc[key] = {fs: [round(s["mean"], 4) for s in ev[fs]["auc_by_test_season"]]
                for fs in ("land", "history", "ledger", "all_div", "known_type")}

price = params["literature"]["maize_price_2024"]
data = {
    "date": DATE,
    "ussd": {"year": 2024, "ghs_per_100kg": round(price["value"] / 10, 2), "source": "MoFA-SRID"},
    "enforcement": {"accounts": enf["accounts"], "outcomes": enf["outcomes"]},
    "allocation": {"instances": len(alloc["instances"]), "gap": gap, "frontier": alloc["frontier"]},
    "simulation": {"replications": sim["replications"], "scenarios": scenarios,
                   "returns": params["simulation"]["return_scenarios"],
                   "leakage": params["simulation"]["leakage_by_custody"]},
    "risk": {"replications": risk["replications"], "seasons": risk["seasons"], "auc": auc,
             "observability": risk["observability"]},
    "sensitivity": {"replications": sens["replications"], "base": sens["base"], "points": sens["points"],
                    "labels": {k: v[0] for k, v in RANGES.items()},
                    "ranges": {k: [v[1], v[2]] for k, v in RANGES.items()}},
}
Path("web/data.json").write_text(json.dumps(data, indent=1))
print("wrote web/data.json", Path("web/data.json").stat().st_size, "bytes")
