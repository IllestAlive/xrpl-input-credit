"""Escape-route scenarios for restricted-spend credit (plan part A).

Each scenario performs real testnet transactions against a fresh World and
records the engine result next to what the configuration is expected to
enforce. Scenarios run in order on the same World, so balances carry over;
assertions are on balance *changes*, never on absolute balances.
Output: results/enforcement_<date>.json plus a Markdown table.
"""

import datetime as dt
import json
import sys
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path

from xrpl.models import (
    AccountLines,
    AccountSet,
    AccountSetAsfFlag,
    Clawback,
    CredentialAccept,
    CredentialCreate,
    IssuedCurrencyAmount,
    OfferCreate,
    PathStep,
    Payment,
    PermissionedDomainSet,
    TrustSet,
    TrustSetFlag,
)
from xrpl.models.transactions.deposit_preauth import Credential
from xrpl.utils import str_to_hex, xrp_to_drops

from .world import CURRENCY, TRUST_LIMIT, World, build_world, require_success, submit_full

VENDOR_CREDENTIAL = str_to_hex("APPROVED_VENDOR")


@dataclass
class Outcome:
    id: str
    route: str
    expected: str
    observed: str
    enforced_by: str
    note: str = ""
    tx_hash: str = ""        # the decisive transaction, verifiable on a testnet explorer
    ledger_index: int = 0    # validated ledger it landed in (0 if rejected before validation)

    @property
    def matches(self) -> bool:
        return self.observed == self.expected


def line(w: World, account, peer) -> dict:
    """The CRD trust line between `account` and `peer`, from `account`'s side."""
    lines = w.client.request(AccountLines(account=account.classic_address, peer=peer.classic_address)).result["lines"]
    found = [ln for ln in lines if ln["currency"] == CURRENCY]
    return found[0] if found else {}


def crd(w: World, account) -> Decimal:
    return Decimal(line(w, account, w.issuer).get("balance", "0"))


def fmt(delta: Decimal) -> str:
    text = f"{delta:+f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


LAST: dict = {}


def send(w: World, tx, wallet) -> str:
    """Submit and keep the hash and ledger index of the transaction as evidence."""
    code, result = submit_full(w.client, tx, wallet)
    LAST.clear()
    LAST.update(tx_hash=result.get("hash", ""), ledger_index=result.get("ledger_index", 0))
    return code


def evidence(o: Outcome) -> Outcome:
    o.tx_hash, o.ledger_index = LAST.get("tx_hash", ""), LAST.get("ledger_index", 0)
    return o


def pay(w: World, sender, receiver, value: str = "10") -> str:
    tx = Payment(account=sender.classic_address, destination=receiver.classic_address, amount=w.crd(value))
    return send(w, tx, sender)


def s1_farmer_to_vendor(w: World) -> Outcome:
    return evidence(Outcome("S1", "farmer -> approved vendor", "tesSUCCESS",
                            pay(w, w.farmer_a, w.vendor), "-"))


def s2_farmer_to_farmer(w: World) -> Outcome:
    return evidence(Outcome("S2", "farmer -> farmer (direct payment)", "tecNO_PERMISSION",
                            pay(w, w.farmer_a, w.farmer_b), "L1: DepositAuth on receiver"))


def s3_farmer_to_stranger(w: World) -> Outcome:
    # The stranger holds an unauthorized trust line, so no path can deliver CRD.
    return evidence(Outcome("S3", "farmer -> unauthorized account", "tecPATH_DRY",
                            pay(w, w.farmer_a, w.stranger), "L1: RequireAuth on issuer"))


def s4_ripple_through_farmer(w: World) -> list[Outcome]:
    """Move CRD to farmer B without a payment *to* farmer B.

    Farmer A opens a trust line to farmer B for B-issued "CRD" (worthless IOUs)
    and pays itself along the path A -> issuer -> B -> A: CRD.issuer leaves A,
    ripples through B, and arrives at A as CRD.B. B ends up holding A's
    issuer-backed CRD. DepositAuth does not apply because B is an intermediate
    hop, not the destination, and B signs nothing. Rippling through B is
    blocked only while B has NoRipple on both of the lines involved.
    """
    a, b = w.farmer_a, w.farmer_b
    b_iou = IssuedCurrencyAmount(currency=CURRENCY, issuer=b.classic_address, value=TRUST_LIMIT)
    require_success(w.client, TrustSet(account=a.classic_address, limit_amount=b_iou), a)

    def attempt() -> str:
        before = crd(w, b)
        tx = Payment(
            account=a.classic_address,
            destination=a.classic_address,
            amount=IssuedCurrencyAmount(currency=CURRENCY, issuer=b.classic_address, value="10"),
            send_max=w.crd("10"),
            paths=[[PathStep(account=b.classic_address)]],  # without a path a self-payment is temREDUNDANT
        )
        code = send(w, tx, a)
        return f"{code}; B CRD {fmt(crd(w, b) - before)}"

    def flags() -> str:
        return (f"B NoRipple: issuer line={bool(line(w, b, w.issuer).get('no_ripple'))}, "
                f"A line={bool(line(w, b, a).get('no_ripple'))}")

    def set_b_issuer_line(flag: TrustSetFlag) -> None:
        require_success(w.client, TrustSet(account=b.classic_address, limit_amount=w.crd(TRUST_LIMIT), flags=flag), b)

    default = evidence(Outcome("S4a", "ripple CRD through farmer B, trust-line flags as created",
                      "tesSUCCESS; B CRD +10", attempt(), "nobody: B's issuer line is created without NoRipple",
                      f"{flags()}. DepositAuth alone does not stop transfers to B, and B signs nothing"))

    set_b_issuer_line(TrustSetFlag.TF_SET_NO_RIPPLE)
    hardened = evidence(Outcome("S4b", "same, after NoRipple is set on B's issuer line", "tecPATH_DRY; B CRD +0",
                                attempt(), "L1: NoRipple on both of B's lines", flags()))

    set_b_issuer_line(TrustSetFlag.TF_CLEAR_NO_RIPPLE)
    cleared = evidence(Outcome("S4c", "same, after B clears that NoRipple again", "tesSUCCESS; B CRD +10",
                               attempt(), "nobody on L1: B controls its own NoRipple flag",
                               "like S5, the hardening holds only if the farmer cannot sign"))
    return [default, hardened, cleared]


def s5_receiver_drops_deposit_auth(w: World) -> Outcome:
    # Farmer B controls its own account flags. If the farmer holds the key,
    # nothing stops it from switching DepositAuth off and accepting transfers.
    clear = AccountSet(account=w.farmer_b.classic_address, clear_flag=AccountSetAsfFlag.ASF_DEPOSIT_AUTH)
    require_success(w.client, clear, w.farmer_b)
    observed = pay(w, w.farmer_a, w.farmer_b)
    proof = dict(LAST)
    restore = AccountSet(account=w.farmer_b.classic_address, set_flag=AccountSetAsfFlag.ASF_DEPOSIT_AUTH)
    require_success(w.client, restore, w.farmer_b)
    LAST.update(proof)
    return evidence(Outcome("S5", "farmer clears own DepositAuth, then farmer -> farmer", "tesSUCCESS",
                            observed, "nobody on L1: depends on who holds the farmer's key"))


def s6_dex(w: World) -> list[Outcome]:
    """Sell credit for XRP on the DEX, open and permissioned."""
    a, b = w.farmer_a, w.farmer_b

    # S6a: open order book. A sells 10 CRD for 10 XRP; B takes it. B receives
    # CRD through its own offer, which DepositAuth does not cover.
    require_success(w.client, OfferCreate(account=a.classic_address, taker_gets=w.crd("10"),
                                          taker_pays=xrp_to_drops(10)), a)
    before = crd(w, b)
    code = send(w, OfferCreate(account=b.classic_address, taker_gets=xrp_to_drops(10),
                               taker_pays=w.crd("10")), b)
    open_dex = evidence(Outcome("S6a", "farmer sells credit for XRP on the open DEX, farmer buys",
                       "tesSUCCESS; B CRD +10", f"{code}; B CRD {fmt(crd(w, b) - before)}",
                       "nobody on L1: offers bypass DepositAuth",
                       "credit converted to cash: the diversion the restriction exists to stop"))

    # Permissioned domain whose only accepted credential is "approved vendor",
    # issued to the vendor alone.
    issuer = w.issuer.classic_address
    require_success(w.client, CredentialCreate(account=issuer, subject=w.vendor.classic_address,
                                               credential_type=VENDOR_CREDENTIAL), w.issuer)
    require_success(w.client, CredentialAccept(account=w.vendor.classic_address, issuer=issuer,
                                               credential_type=VENDOR_CREDENTIAL), w.vendor)
    code, tx = submit_full(w.client, PermissionedDomainSet(
        account=issuer, accepted_credentials=[Credential(issuer=issuer, credential_type=VENDOR_CREDENTIAL)]),
        w.issuer)
    if code != "tesSUCCESS":
        raise RuntimeError(f"PermissionedDomainSet failed: {code}")
    domain_id = next(n["CreatedNode"]["LedgerIndex"] for n in tx["meta"]["AffectedNodes"]
                     if n.get("CreatedNode", {}).get("LedgerEntryType") == "PermissionedDomain")

    # S6b: a farmer without the credential cannot use the domain's book.
    code = send(w, OfferCreate(account=a.classic_address, taker_gets=w.crd("1"),
                               taker_pays=xrp_to_drops(1), domain_id=domain_id), a)
    farmer_in_domain = evidence(Outcome("S6b", "farmer places an offer in the vendor-only permissioned DEX",
                               "tecNO_PERMISSION", code, "L1: Permissioned DEX membership",
                               "but S6a stays open: a domain restricts its own book, not the token"))

    # S6c (control): the credentialed vendor can trade in the domain.
    code = send(w, OfferCreate(account=w.vendor.classic_address, taker_gets=xrp_to_drops(1),
                               taker_pays=w.crd("1"), domain_id=domain_id), w.vendor)
    vendor_in_domain = evidence(Outcome("S6c", "control: vendor places an offer in the same domain",
                               "tesSUCCESS", code, "-", "shows the domain itself works"))
    return [open_dex, farmer_in_domain, vendor_in_domain]


def s7_offchain_vendor_collusion(w: World) -> Outcome:
    note = ("vendor accepts CRD and hands over cash instead of inputs; "
            "the ledger records an ordinary farmer -> vendor payment (identical to S1)")
    return Outcome("S7", "farmer and vendor settle off-ledger", "not observable on-ledger",
                   "not observable on-ledger", "field: audits, vendor incentives", note)


def s8_issuer_intervention(w: World) -> list[Outcome]:
    a = w.farmer_a
    a_line = IssuedCurrencyAmount(currency=CURRENCY, issuer=a.classic_address, value="0")
    issuer = w.issuer.classic_address

    require_success(w.client, TrustSet(account=issuer, limit_amount=a_line,
                                       flags=TrustSetFlag.TF_SET_FREEZE), w.issuer)
    frozen = evidence(Outcome("S8a", "issuer freezes farmer A's line; A -> vendor", "tecPATH_DRY",
                              pay(w, a, w.vendor), "L1: issuer Freeze",
                              "also blocks legitimate spending: a blunt instrument"))
    require_success(w.client, TrustSet(account=issuer, limit_amount=a_line,
                                       flags=TrustSetFlag.TF_CLEAR_FREEZE), w.issuer)

    before = crd(w, a)
    code = send(w, Clawback(account=issuer, amount=IssuedCurrencyAmount(
        currency=CURRENCY, issuer=a.classic_address, value="5")), w.issuer)
    clawed = evidence(Outcome("S8b", "issuer claws back 5 CRD from farmer A", "tesSUCCESS; A CRD -5",
                     f"{code}; A CRD {fmt(crd(w, a) - before)}", "L1: issuer Clawback",
                     "recovers diverted credit only if it is still on A's line; the issuer can take any holder's balance"))
    return [frozen, clawed]


SCENARIOS = [
    s1_farmer_to_vendor,
    s2_farmer_to_farmer,
    s3_farmer_to_stranger,
    s4_ripple_through_farmer,
    s5_receiver_drops_deposit_auth,
    s6_dex,
    s7_offchain_vendor_collusion,
    s8_issuer_intervention,
]


def run_all(w: World) -> list[Outcome]:
    outcomes = []
    for scenario in SCENARIOS:
        result = scenario(w)
        outcomes.extend(result if isinstance(result, list) else [result])
    return outcomes


def to_markdown(outcomes: list[Outcome]) -> str:
    rows = ["| # | Route | Expected | Observed | Enforced by | Note |", "|---|---|---|---|---|---|"]
    for o in outcomes:
        mark = "" if o.matches else " **(unexpected)**"
        rows.append(f"| {o.id} | {o.route} | `{o.expected}` | `{o.observed}`{mark} | {o.enforced_by} | {o.note} |")
    return "\n".join(rows)


def main() -> int:
    w = build_world()
    outcomes = run_all(w)
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
