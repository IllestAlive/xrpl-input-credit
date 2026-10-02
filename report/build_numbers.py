"""Write report/numbers.tex from results/*.json, so no number in the note is typed by hand.

Run from the repository root:  uv run python report/build_numbers.py
"""

import json
from pathlib import Path

import numpy as np
from scipy.stats import norm

R = Path("results")
DATE = "2026-10-02"
load = lambda name: json.loads((R / f"{name}_{DATE}.json").read_text())
enf, alloc, sim, risk, sens = (load(n) for n in ("enforcement", "allocation", "simulation", "risk", "sensitivity"))

out: list[str] = []
mac = lambda name, value: out.append(f"\\newcommand{{\\{name}}}{{{value}}}")
pct = lambda v, d=1: f"{v:+.{d}f}\\%"
tt = lambda s: "\\texttt{" + s.replace("_", "\\_") + "}"

# --- Part A -------------------------------------------------------------------
oc = enf["outcomes"]
mac("EnfN", len(oc))
mac("EnfMatch", sum(o["matches"] for o in oc))
rows = []
for o in oc:
    obs = o["observed"].replace("not observable on-ledger", "not observable")
    rows.append(f"{o['id']} & {o['route']} & {tt(obs)} & {o['enforced_by'].replace('->', '$\\to$')} \\\\")
out.append("\\newcommand{\\EnfRows}{" + "\n".join(r.replace("->", "$\\to$") for r in rows) + "}")

# --- Part B -------------------------------------------------------------------
inst = alloc["instances"]
names = {"greedy_risk": "Risk-aware greedy", "greedy": "Budget-only greedy", "uniform": "Equal amounts",
         "land": "Proportional to farm size", "random (best of 200)": "Random, best of 200",
         "random (mean of 200)": "Random, mean of 200"}
rows = []
for k, label in names.items():
    s = 100 * np.array([r["share_of_optimum"][k] for r in inst])
    rows.append(f"{label} & {np.median(s):.1f} & {s.min():.1f}--{s.max():.1f} \\\\")
out.append("\\newcommand{\\GapRows}{" + "\n".join(rows) + "}")
mac("NInst", len(inst))
gr = 100 * np.array([r["share_of_optimum"]["greedy_risk"] for r in inst])
gb = 100 * np.array([r["share_of_optimum"]["greedy"] for r in inst])
mac("GreedyRiskMed", f"{np.median(gr):.1f}")
mac("GreedyRiskMin", f"{gr.min():.1f}")
mac("GreedyMed", f"{np.median(gb):.1f}")
fr = alloc["frontier"]
mac("GreedyTightest", f"{100 * fr[0]['greedy'] / fr[0]['milp']:.0f}")
mac("MilpSecs", f"{np.median([r['milp_seconds'] for r in inst]):.1f}")

# --- Part C -------------------------------------------------------------------
res = sim["results"]
mac("SimReps", f"{sim['replications']:,}")
rows = []
nice = {"rct_like": "RCT-like (1.0)", "trial_plots": "Trial plots (3.58)", "naive_agronomic": "Naive agronomic (8.8)"}
for key, v in res.items():
    ret, cust = key.split("/")
    d = v["paired_gain"]["ledger_vs_no_history"]
    g = lambda p: f"{v[p]['gain']['mean'] / 1e6:.2f}"
    rows.append(f"{nice[ret]} & {cust.replace('_', '-')} & {g('equal')} & {g('no_history')} & {g('ledger')} & "
                f"{g('known_type')} & {pct(d['pct_of_baseline'])} & {v['ledger']['final_fund']['mean']:.2f} \\\\")
out.append("\\newcommand{\\SimRows}{" + "\n".join(rows) + "}")
lv = [v["paired_gain"]["ledger_vs_no_history"]["pct_of_baseline"] for v in res.values()]
tv = [v["paired_gain"]["no_history_vs_equal"]["pct_of_baseline"] for v in res.values()]
cost = [100 * (res[f"{r}/self_custody"]["ledger"]["gain"]["mean"] / res[f"{r}/custodial"]["ledger"]["gain"]["mean"] - 1)
        for r in nice]
fund_rct = [res[f"rct_like/{c}"][p]["final_fund"]["mean"] for c in ("custodial", "self_custody")
            for p in ("equal", "no_history", "ledger", "known_type")]
mac("TargetLo", f"{min(tv):.0f}"); mac("TargetHi", f"{max(tv):.0f}")
mac("LedgerLo", f"{sorted(lv)[1]:.0f}"); mac("LedgerHi", f"{max(lv):.0f}"); mac("LedgerMin", f"{min(lv):.1f}")
mac("CustodyLo", f"{-max(cost):.0f}"); mac("CustodyHi", f"{-min(cost):.0f}")
mac("FundRctLo", f"{100 * min(fund_rct):.0f}"); mac("FundRctHi", f"{100 * max(fund_rct):.0f}")
rc = res["rct_like/custodial"]
mac("RctLedgerPct", f"{rc['paired_gain']['ledger_vs_no_history']['pct_of_baseline']:.0f}")
mac("RctTypePct", f"{rc['paired_gain']['known_type_vs_no_history']['pct_of_baseline']:.0f}")

# --- Part D -------------------------------------------------------------------
ev = risk["evaluation"]
labels = {"pooled": "None (pooled rate)", "land": "Land", "history": "+ loan and default history",
          "ledger": "+ on-ledger diversion", "all_div": "+ all diversion (not observable)",
          "known_type": "Known repayment type (benchmark)"}
rows = []
for fs, label in labels.items():
    c, s = ev["trial_plots/custodial"][fs]["auc_last"], ev["trial_plots/self_custody"][fs]["auc_last"]
    rows.append(f"{label} & {c['mean']:.3f} & {s['mean']:.3f} \\\\")
out.append("\\newcommand{\\AucRows}{" + "\n".join(rows) + "}")
mac("RiskReps", risk["replications"])
ob = risk["observability"]
mac("ObsZero", pct(ob["0.0"]["ledger_vs_no_history_pct"]))
mac("ObsFull", pct(ob["1.0"]["ledger_vs_no_history_pct"]))
bl = ev["trial_plots/custodial"]["boosting_vs_logistic_last"]
mac("GbmAuc", f"{bl['boosting']['mean']:.3f}"); mac("LogAuc", f"{bl['logistic']['mean']:.3f}")
cal = ev["trial_plots/self_custody"]["calibration_last_season"]
mac("CalLoPred", f"{cal[0]['pred']:.2f}"); mac("CalLoObs", f"{cal[0]['obs']:.2f}")
mac("CalHiPred", f"{cal[-1]['pred']:.2f}"); mac("CalHiObs", f"{cal[-1]['obs']:.2f}")

# --- Sensitivity --------------------------------------------------------------
pts, base = sens["points"], sens["base"]
def span(metric):
    vals = [pts[n][s][metric] for n in pts for s in ("low", "high")]
    return min(vals), max(vals)
mac("SensReps", sens["replications"])
lo, hi = span("ledger_gain"); mac("SensLedgerLo", f"{lo:.2f}"); mac("SensLedgerHi", f"{hi:.1f}")
lo, hi = span("custody_cost"); mac("SensCustLo", f"{-hi:.0f}"); mac("SensCustHi", f"{-lo:.0f}")
lo, hi = span("fund_left"); mac("SensFundLo", f"{lo:.2f}"); mac("SensFundHi", f"{hi:.2f}")
lo, hi = span("targeting_gain"); mac("SensTargetLo", f"{lo:.1f}"); mac("SensTargetHi", f"{hi:.1f}")
mac("SensDefLow", f"{pts['default_target']['low']['ledger_gain']:.2f}")
mac("SensDefHigh", f"{pts['default_target']['high']['ledger_gain']:.1f}")
mac("SensCapLoose", f"{pts['loss_cap_share']['high']['ledger_gain']:.1f}")
mac("SensCapTight", f"{pts['loss_cap_share']['low']['ledger_gain']:.1f}")

# --- RCT power (illustrative) -------------------------------------------------
# Two-arm cluster-randomised comparison of a binary outcome; alpha 0.05 two-sided, power 0.8.
z = norm.ppf(0.975) + norm.ppf(0.8)
def mde(p, villages_per_arm, per_village, icc):
    de = 1 + (per_village - 1) * icc
    return z * np.sqrt(2 * p * (1 - p) * de / (villages_per_arm * per_village))
p_def = res["trial_plots/custodial"]["no_history"]["default_rate"]["mean"]
rows = []
for k in (20, 40, 80):
    rows.append(f"{k} & " + " & ".join(f"{100 * mde(p_def, k, 50, icc):.1f}" for icc in (0.02, 0.05, 0.10)) + " \\\\")
out.append("\\newcommand{\\PowerRows}{" + "\n".join(rows) + "}")
mac("PowerBaseDefault", f"{p_def:.2f}")
d_led = 100 * (res["trial_plots/custodial"]["no_history"]["default_rate"]["mean"]
               - res["trial_plots/custodial"]["ledger"]["default_rate"]["mean"])
d_cus = 100 * (res["trial_plots/self_custody"]["ledger"]["default_rate"]["mean"]
               - res["trial_plots/custodial"]["ledger"]["default_rate"]["mean"])
mac("EffLedgerPP", f"{d_led:.1f}"); mac("EffCustodyPP", f"{d_cus:.1f}")

Path("report/numbers.tex").write_text("% Generated by report/build_numbers.py -- do not edit.\n" + "\n".join(out) + "\n")
print(f"wrote {len(out)} macros")
