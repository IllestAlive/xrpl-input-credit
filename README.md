# xrpl-input-credit

Restricted-spend agricultural input credit on the XRP Ledger: which parts of
"credit that can only be spent at approved input vendors" the ledger enforces
at protocol level, which parts fall to key custody and field institutions, and
how much the resulting transaction history improves budget-constrained credit
allocation.

All farmer data in this repository is **synthetic**. Nothing here describes or
makes claims about any deployed system.

## Status

| Part | Content | State |
|---|---|---|
| A | XRPL enforcement analysis (testnet) | done: 14 outcomes, 5 findings |
| B | Allocation optimisation (MILP vs greedy vs baselines) | done on placeholder parameters |
| C | Agent-based Monte Carlo simulation | done: 6 scenarios x 4 policies x 1,000 replications |
| D | Credit-risk model on ledger history | — |
| E | Research note | — |

## Amendment status (validated ledgers, 2026-10-02)

Read from the on-ledger `Amendments` object, not from a server's `feature`
output. Full output: [`results/amendments_2026-10-02.txt`](results/amendments_2026-10-02.txt).

All of DepositAuth, DepositPreauth, Credentials, PermissionedDomains,
PermissionedDEX, Clawback, DeepFreeze, TokenEscrow and MPTokensV1 are enabled
on both testnet and mainnet; SingleAssetVault and LendingProtocol are not.

## Enforcement results (testnet, 2026-10-02)

Fresh accounts per run, 14 outcomes, all as expected. Accounts and results:
[`results/enforcement_2026-10-02.json`](results/enforcement_2026-10-02.json).

| # | Route | Expected | Observed | Enforced by | Note |
|---|---|---|---|---|---|
| S1 | farmer -> approved vendor | `tesSUCCESS` | `tesSUCCESS` | - |  |
| S2 | farmer -> farmer (direct payment) | `tecNO_PERMISSION` | `tecNO_PERMISSION` | L1: DepositAuth on receiver |  |
| S3 | farmer -> unauthorized account | `tecPATH_DRY` | `tecPATH_DRY` | L1: RequireAuth on issuer |  |
| S4a | ripple CRD through farmer B, trust-line flags as created | `tesSUCCESS; B CRD +10` | `tesSUCCESS; B CRD +10` | nobody: B's issuer line is created without NoRipple | B NoRipple: issuer line=False, A line=True. DepositAuth alone does not stop transfers to B, and B signs nothing |
| S4b | same, after NoRipple is set on B's issuer line | `tecPATH_DRY; B CRD +0` | `tecPATH_DRY; B CRD +0` | L1: NoRipple on both of B's lines | B NoRipple: issuer line=True, A line=True |
| S4c | same, after B clears that NoRipple again | `tesSUCCESS; B CRD +10` | `tesSUCCESS; B CRD +10` | nobody on L1: B controls its own NoRipple flag | like S5, the hardening holds only if the farmer cannot sign |
| S5 | farmer clears own DepositAuth, then farmer -> farmer | `tesSUCCESS` | `tesSUCCESS` | nobody on L1: depends on who holds the farmer's key |  |
| S6a | farmer sells credit for XRP on the open DEX, farmer buys | `tesSUCCESS; B CRD +10` | `tesSUCCESS; B CRD +10` | nobody on L1: offers bypass DepositAuth | credit converted to cash: the diversion the restriction exists to stop |
| S6b | farmer places an offer in the vendor-only permissioned DEX | `tecNO_PERMISSION` | `tecNO_PERMISSION` | L1: Permissioned DEX membership | but S6a stays open: a domain restricts its own book, not the token |
| S6c | control: vendor places an offer in the same domain | `tesSUCCESS` | `tesSUCCESS` | - | shows the domain itself works |
| S7 | farmer and vendor settle off-ledger | `not observable on-ledger` | `not observable on-ledger` | field: audits, vendor incentives | vendor accepts CRD and hands over cash instead of inputs; the ledger records an ordinary farmer -> vendor payment (identical to S1) |
| S8a | issuer freezes farmer A's line; A -> vendor | `tecPATH_DRY` | `tecPATH_DRY` | L1: issuer Freeze | also blocks legitimate spending: a blunt instrument |
| S8b | issuer claws back 5 CRD from farmer A | `tesSUCCESS; A CRD -5` | `tesSUCCESS; A CRD -5` | L1: issuer Clawback | recovers diverted credit only if it is still on A's line; the issuer can take any holder's balance |

The expectation for S4a was revised after the first run: I expected new trust
lines to carry NoRipple on the farmer's side by default, but the farmer's line
to the issuer was created without it. The table records the corrected
expectation; the first run's surprise is the finding.

### What the ledger does and does not enforce

1. **DepositAuth alone is not enough (S4a).** A farmer can push credit into
   another farmer's account by rippling through it. The receiving farmer
   signs nothing. Farmer lines to the issuer must also carry NoRipple (S4b).
2. **Every farmer-side protection sits behind the farmer's key (S4c, S5).**
   DepositAuth and NoRipple are flags the account holder can clear. Whether
   the restriction holds is a question of key custody, not of the ledger.
3. **The open DEX turns credit into cash (S6a).** Offers deliver tokens
   regardless of DepositAuth. A permissioned domain restricts who may use
   *its* order book (S6b, S6c), not where the token can trade.
4. **The issuer's tools work but are blunt (S8).** Freeze also stops
   legitimate spending; Clawback can take any holder's balance. Both concentrate
   power in the issuer.
5. **Vendor collusion is invisible on-ledger (S7).** It looks exactly like S1.

For the simulation (part C) this means the share of credit that leaks away
from inputs is not a constant: it depends on the custody model (custodial
wallet vs. farmer-held key) and on field-level vendor auditing.

## Allocation results (synthetic placeholder instances, 2026-10-02)

**Model.** Each of 1,000 farmers gets one credit level from {0, 50, 100, 150,
200}. Maximise total expected gain (concave in credit) subject to a budget, a
cap on expected loss (sum of default probability x credit), and per-vendor
capacity. Exact solution: MILP (HiGHS), verified against brute-force
enumeration on small instances in `tests/test_allocation.py`.

**Parameters are placeholders** (`params.yaml`, `allocation_synthetic`),
chosen so every constraint can bind, not estimated from data. They will be
replaced with literature-sourced values. Read the numbers below as a property
of the methods on this instance family, not as a statement about farmers.

![Gap to optimum](results/fig_gap.png)

| Method | Median % of optimum | Min–max (20 instances) |
|---|---|---|
| Risk-aware greedy | 99.6 | 99.0–100.0 |
| Budget-only greedy | 84.0 | 82.5–84.9 |
| Equal amounts | 73.1 | 70.4–74.7 |
| Proportional to farm size | 65.4 | 64.4–66.9 |
| Random (best of 200) | 57.3 | 55.5–58.9 |
| Random (mean of 200) | 52.4 | 51.0–53.1 |

MILP solved every instance to proven optimality (reported gap 0) in about 0.5 s
(max ~1.2 s across runs). Budget and loss cap were binding in all 20 instances; vendor
capacity rarely (0.6 vendors at cap on average).

![Frontier](results/fig_frontier.png)

**Finding.** The first greedy ranked steps by gain per unit of *budget* only
and reached 84% of the optimum. The frontier shows why: it is near-optimal
when the loss cap is slack (>= 20% of budget) and falls to 50% when it is
tight, because it spends the scarce loss allowance on high-risk farmers.
Pricing each step in both resources (budget share + lam x loss-cap share,
lam picked from a small grid) recovers 99–100% at every cap. The risk
estimate p is therefore what makes cheap allocation work, which is the
question part D asks of the ledger history.

## Simulation results (2026-10-02, 1,000 replications per scenario)

A revolving fund lends to 1,000 farmers in 20 villages for 4 seasons. Land,
yields, prices, non-responsive plots and the default anchor come from the
literature ([docs/parameters.md](docs/parameters.md)); behavioural parameters
are assumptions listed in `params.yaml`. Every policy runs on the same random
draws (common random numbers), so the paired differences below are tight.

Total harvest gain over 4 seasons, million GHS (2024 prices):

| Scenario (return / custody) | Equal | Risk-aware, no history | Risk-aware, ledger history | Known type (benchmark) | Ledger vs no history | Fund after 4 seasons (ledger) |
|---|---|---|---|---|---|---|
| rct_like/custodial | 0.58 | 0.68 | 0.79 | 1.26 | +16.1% (±0.6) | 0.63 |
| rct_like/self_custody | 0.37 | 0.42 | 0.47 | 0.83 | +12.0% (±0.5) | 0.56 |
| trial_plots/custodial | 3.43 | 4.08 | 4.62 | 5.20 | +13.2% (±0.3) | 0.88 |
| trial_plots/self_custody | 1.67 | 1.96 | 2.24 | 3.25 | +14.7% (±0.5) | 0.65 |
| naive_agronomic/custodial | 9.78 | 12.30 | 12.47 | 13.47 | +1.4% (±0.1) | 1.04 |
| naive_agronomic/self_custody | 4.77 | 5.46 | 6.32 | 8.24 | +15.8% (±0.5) | 0.71 |

The ± values are 95% intervals on the paired difference across replications.
They describe simulation noise, not uncertainty in the assumptions, which is
the job of the sensitivity analysis (day 11).

### What the simulation says (under these assumptions)

1. **Allocating by expected gain and risk beats equal amounts by 14–26%** in
   every scenario.
2. **Ledger history adds 12–16% more**, except when returns are so high that
   defaults are rare (naive agronomic, custodial: +1.4%): there is little to
   learn when almost everyone repays.
3. **Ledger history captures only part of the value of knowing each farmer's
   type.** Under RCT-like returns, history gains 16% of a possible 84% after
   4 seasons. Four seasons of on-ledger history is a thin record.
4. **Custody dominates allocation.** Moving from custodial wallets (5%
   leakage) to farmer-held keys (30%) costs 35–52% of the gain and pushes up
   defaults, larger than any allocation improvement. This is part A's
   finding, priced.
5. **No allocation rule rescues the fund if returns are RCT-like.** With a
   gross return near 1, the fund keeps 55–69% of its capital after 4 seasons
   under every rule, including the known-type benchmark. This matches Karlan et al. (2014): when risk, not
   credit, binds, better targeting of credit is not enough.

## Run

```bash
uv sync
uv run python -m xrpl_input_credit.ledger.amendments   # amendment status
uv run python -m xrpl_input_credit.ledger.scenarios    # escape routes on testnet (~7 min)
uv run python -m xrpl_input_credit.model.run_allocation # part B experiments (~30 s)
uv run python -m xrpl_input_credit.sim.run_simulation   # part C (~30 s, all cores)
uv run pytest
```
