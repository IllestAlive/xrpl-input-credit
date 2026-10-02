"""Fund the four testnet roles from the faucet and persist their seeds.

Seeds are testnet-only and live in `.testnet-wallets.json`, which is
git-ignored. Re-running reuses existing wallets instead of re-funding.
"""

import json
import sys
from pathlib import Path

from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet, generate_faucet_wallet

TESTNET_URL = "https://s.altnet.rippletest.net:51234"
WALLETS_FILE = Path(".testnet-wallets.json")
ROLES = ["issuer", "vendor", "farmer_a", "farmer_b"]


def load_wallets() -> dict[str, Wallet]:
    seeds = json.loads(WALLETS_FILE.read_text())
    return {role: Wallet.from_seed(seed) for role, seed in seeds.items()}


def main() -> int:
    if WALLETS_FILE.exists():
        wallets = load_wallets()
    else:
        client = JsonRpcClient(TESTNET_URL)
        wallets = {role: generate_faucet_wallet(client) for role in ROLES}
        WALLETS_FILE.write_text(json.dumps({r: w.seed for r, w in wallets.items()}, indent=2))
    for role, wallet in wallets.items():
        print(f"{role:<9} {wallet.classic_address}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
