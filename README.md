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
| A | XRPL enforcement analysis (testnet) | amendment check done |
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

## Run

```bash
uv sync
uv run python -m xrpl_input_credit.ledger.amendments   # amendment status
uv run python -m xrpl_input_credit.ledger.accounts     # fund testnet roles
uv run pytest
```
