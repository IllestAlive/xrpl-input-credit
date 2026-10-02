# Parameter sources

Checked 2026-10-02. "Verified" means the number was read in the source itself
(PDF text extracted and searched), not taken from a search-engine summary.
Source PDFs are not redistributed in this repository.

| Parameter | Value | Source | Status |
|---|---|---|---|
| Maize yield, national 2024 | 2.60 t/ha | MoFA-SRID, *Agriculture in Ghana: Facts & Figures 2024*, Tables 4.1, 4.4, 4.7 | verified |
| Maize potential yield | 5.50 t/ha | same, Tables 4.6–4.7 | verified |
| Maize rural wholesale price 2024 | 9,285.91 GHS/t (nominal) | same, Table 7.1 | verified |
| Landholding, forest zone | median 1.62 ha; 55% < 2 ha; 89% < 5 ha | Chamberlin (2008), IFPRI DP 00823, Table 1 (GLSS5 2005/06) | verified, old data |
| N agronomic efficiency | 18 kg grain/kg N; 18% non-responsive plots | Ichami et al. (2019), *Nutr Cycl Agroecosyst* 113(1):1–19 | verified |
| Return on trial plots | 3.58 (=$215/$60 per acre) | Fosu & Dittoh (2011) via Karlan et al. (2014), fn. 1 | secondary |
| Return at farmer level (RCT) | grant alone: +64.82 harvest value (s.e. 89.76), n.s. | Karlan, Osei, Osei-Akoto & Udry (2014), *QJE* 129(2), Table IV | verified |
| Agricultural loan default | 58% of borrowers (May 2009) | Karlan, Kutsoati, McMillan & Udry (2010), J-PAL working paper | verified, single pilot |
| Credit use | agricultural credit 0–6%; any credit < 20% | Chamberlin (2008), Table 10 | verified |
| Urea price Q1 2024 | 421–450 GHS / 50 kg | Dela Michel (blog, March 2024), one market, no institutional source | **not verified** |

## What the sources say together

**The return to input credit is the most uncertain number in the model.**
Three readings of it differ by almost an order of magnitude:

| Reading | Gross return per GHS | Basis |
|---|---|---|
| Naive agronomic | ~8.8 | 18 kg grain/kg N x 2024 maize price / urea N cost |
| On-farm trials | 3.58 | Fosu & Dittoh (2011), via Karlan et al. (2014) |
| Farmer-level RCT | ~1 (no detectable profit) | Karlan et al. (2014), Table IV |

The gap is itself informative: agronomic arithmetic ignores labour, timing,
other nutrients, non-responsive soils (18% of plots in Ichami et al.) and
weather. Karlan et al. conclude that uninsured risk, not credit, is the
binding constraint for farmers in northern Ghana. The simulation therefore
runs all three as scenarios instead of picking one. The naive figure is an
upper bound only: it mixes a verified 2024 maize price with an unverified urea price.

**The 58% default rate comes from one pilot** (one rural bank, one season,
with a price collapse risk the product was designed around). It is used as
the upper end of a range, not as a point estimate.

**Assumptions without a source** (village and individual yield shocks,
saturation of returns, credit menu, leakage by custody model) are listed in
`params.yaml` under `simulation` and all enter the sensitivity analysis.
The leakage values are motivated by the enforcement analysis (part A,
S4c/S5/S6a), not measured.
