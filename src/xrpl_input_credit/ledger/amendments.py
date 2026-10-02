"""Check which XRPL amendments this project depends on are live.

Source of truth is the on-ledger `Amendments` singleton (validated ledger),
not the `feature` RPC of whichever public server answers: that reflects the
server's own build and votes. `feature` is used only to tell retired
amendments (code removed, unconditionally on) from unknown names.
"""

import hashlib
import json
import sys
import urllib.request

NETWORKS = {
    "testnet": "https://s.altnet.rippletest.net:51234",
    "mainnet": "https://xrplcluster.com",
}

# Ledger key of the Amendments singleton object (fixed for every network).
AMENDMENTS_INDEX = "7DB0788C020F02780A673DC74757F23823FA3014C1866E72CC4CD8B226CD6EF4"

# Amendments the enforcement analysis (part A) relies on or discusses.
WATCHED = [
    "DepositAuth",          # farmer accounts refuse payments from strangers
    "DepositPreauth",       # farmer preauthorizes the issuer only
    "Credentials",          # credential-based preauthorization
    "PermissionedDomains",  # credential-gated domains
    "PermissionedDEX",      # domain-restricted order books
    "Clawback",             # issuer recovers diverted tokens
    "DeepFreeze",           # issuer blocks a holder from paying out
    "TokenEscrow",          # escrow of issued tokens (season-long credit)
    "MPTokensV1",           # multi-purpose tokens, alternative to trust lines
    "SingleAssetVault",
    "LendingProtocol",
]


def amendment_id(name: str) -> str:
    return hashlib.sha512(name.encode()).digest()[:32].hex().upper()


def rpc(url: str, method: str, params: dict) -> dict:
    body = json.dumps({"method": method, "params": [params]}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)["result"]


def status(url: str) -> dict[str, str]:
    entry = rpc(url, "ledger_entry", {"index": AMENDMENTS_INDEX, "ledger_index": "validated"})
    node = entry["node"]
    enabled = set(node.get("Amendments", []))
    majorities = {m["Majority"]["Amendment"] for m in node.get("Majorities", [])}
    known = rpc(url, "feature", {}).get("features", {})

    out = {}
    for name in WATCHED:
        aid = amendment_id(name)
        if aid in enabled:
            out[name] = "enabled"
        elif aid in majorities:
            out[name] = "majority (pending activation)"
        elif aid in known:
            out[name] = "not enabled"
        else:
            out[name] = "unknown to server (retired or not in this build)"
    out["_ledger_index"] = str(entry["ledger_index"])
    return out


def main() -> int:
    results = {net: status(url) for net, url in NETWORKS.items()}
    width = max(map(len, WATCHED))
    print(f"{'amendment':<{width}}  " + "  ".join(f"{n:<34}" for n in results))
    for name in WATCHED:
        print(f"{name:<{width}}  " + "  ".join(f"{r[name]:<34}" for r in results.values()))
    print("validated ledger: " + ", ".join(f"{n}={r['_ledger_index']}" for n, r in results.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
