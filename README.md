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
| A | XRPL enforcement analysis (testnet) | S1–S3, S5 done; S4, S6–S8 next |
| B | Allocation optimisation (MILP vs greedy vs baselines) | — |
| C | Agent-based Monte Carlo simulation | — |
| D | Credit-risk model on ledger history | — |
| E | Research note | — |

## Amendment status (validated ledgers, 2026-10-02)

Read from the on-ledger `Amendments` object, not from a server's `feature`
output. Full output: [`results/amendments_2026-10-02.txt`](results/amendments_2026-10-02.txt).

All of DepositAuth, DepositPreauth, Credentials, PermissionedDomains,
PermissionedDEX, Clawback, DeepFreeze, TokenEscrow and MPTokensV1 are enabled
on both testnet and mainnet; SingleAssetVault and LendingProtocol are not.

## Enforcement results so far (testnet, 2026-10-02)

Fresh accounts per run; transaction results recorded in
[`results/enforcement_2026-10-02.json`](results/enforcement_2026-10-02.json).

| # | Route | Expected | Observed | Enforced by |
|---|---|---|---|---|
| S1 | farmer -> approved vendor | `tesSUCCESS` | `tesSUCCESS` | - |
| S2 | farmer -> farmer (direct payment) | `tecNO_PERMISSION` | `tecNO_PERMISSION` | L1: DepositAuth on receiver |
| S3 | farmer -> unauthorized account | `tecPATH_DRY` | `tecPATH_DRY` | L1: RequireAuth on issuer |
| S5 | farmer clears own DepositAuth, then farmer -> farmer | `tesSUCCESS` | `tesSUCCESS` | nobody on L1: depends on who holds the farmer's key |

S5 is the first finding: the ledger blocks farmer-to-farmer transfers only as
long as the farmer cannot change their own account flags. Whether the
restriction holds is decided by key custody, not by the ledger.

## Run

```bash
uv sync
uv run python -m xrpl_input_credit.ledger.amendments   # amendment status
uv run python -m xrpl_input_credit.ledger.scenarios    # escape routes on testnet (~4 min)
uv run pytest
```
