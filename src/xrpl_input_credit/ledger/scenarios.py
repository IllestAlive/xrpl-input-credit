"""Escape-route scenarios for restricted-spend credit (plan part A).

Each scenario performs real testnet transactions against a fresh World and
records the engine result next to what the configuration is expected to
enforce. Output: results/enforcement_<date>.json plus a Markdown table.
"""

import datetime as dt
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from xrpl.models import AccountSet, AccountSetAsfFlag, Payment

from .world import World, build_world, submit


@dataclass
class Outcome:
    id: str
    route: str
    expected: str
    observed: str
    enforced_by: str

    @property
    def matches(self) -> bool:
        return self.observed == self.expected


def pay(w: World, sender, receiver, value: str = "10") -> str:
    tx = Payment(account=sender.classic_address, destination=receiver.classic_address, amount=w.crd(value))
    return submit(w.client, tx, sender)


def s1_farmer_to_vendor(w: World) -> Outcome:
    return Outcome("S1", "farmer -> approved vendor", "tesSUCCESS",
                   pay(w, w.farmer_a, w.vendor), "-")


def s2_farmer_to_farmer(w: World) -> Outcome:
    return Outcome("S2", "farmer -> farmer (direct payment)", "tecNO_PERMISSION",
                   pay(w, w.farmer_a, w.farmer_b), "L1: DepositAuth on receiver")


def s3_farmer_to_stranger(w: World) -> Outcome:
    # The stranger holds an unauthorized trust line, so no path can deliver CRD.
    return Outcome("S3", "farmer -> unauthorized account", "tecPATH_DRY",
                   pay(w, w.farmer_a, w.stranger), "L1: RequireAuth on issuer")


def s5_receiver_drops_deposit_auth(w: World) -> Outcome:
    # Farmer B controls its own account flags. If the farmer holds the key,
    # nothing stops it from switching DepositAuth off and accepting transfers.
    clear = AccountSet(account=w.farmer_b.classic_address, clear_flag=AccountSetAsfFlag.ASF_DEPOSIT_AUTH)
    if submit(w.client, clear, w.farmer_b) != "tesSUCCESS":
        raise RuntimeError("could not clear DepositAuth on farmer_b")
    observed = pay(w, w.farmer_a, w.farmer_b)
    restore = AccountSet(account=w.farmer_b.classic_address, set_flag=AccountSetAsfFlag.ASF_DEPOSIT_AUTH)
    submit(w.client, restore, w.farmer_b)
    return Outcome("S5", "farmer clears own DepositAuth, then farmer -> farmer", "tesSUCCESS",
                   observed, "nobody on L1: depends on who holds the farmer's key")


SCENARIOS = [s1_farmer_to_vendor, s2_farmer_to_farmer, s3_farmer_to_stranger, s5_receiver_drops_deposit_auth]


def to_markdown(outcomes: list[Outcome]) -> str:
    rows = ["| # | Route | Expected | Observed | Enforced by |", "|---|---|---|---|---|"]
    for o in outcomes:
        mark = "" if o.matches else " **(unexpected)**"
        rows.append(f"| {o.id} | {o.route} | `{o.expected}` | `{o.observed}`{mark} | {o.enforced_by} |")
    return "\n".join(rows)


def main() -> int:
    w = build_world()
    outcomes = [scenario(w) for scenario in SCENARIOS]
    stamp = dt.date.today().isoformat()
    out = Path("results") / f"enforcement_{stamp}.json"
    out.write_text(json.dumps({
        "date": stamp,
        "network": "testnet",
        "accounts": {role: getattr(w, role).classic_address
                     for role in ("issuer", "vendor", "farmer_a", "farmer_b", "stranger")},
        "outcomes": [asdict(o) | {"matches": o.matches} for o in outcomes],
    }, indent=2))
    print(to_markdown(outcomes))
    return 0 if all(o.matches for o in outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
