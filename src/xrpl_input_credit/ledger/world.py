"""Build a fresh restricted-credit setup on testnet.

Roles: one issuer, one approved vendor, two farmers, and a stranger who opens
a trust line but is never authorized. Every run uses freshly funded accounts,
so scenarios cannot inherit state (e.g. a flag toggled by an earlier run).

Configuration under test:
  issuer   RequireAuth (only authorized trust lines may hold CRD),
           DefaultRipple (holders can pay each other through the issuer),
           AllowTrustLineClawback (must be set before any trust line exists)
  farmers  DepositAuth, with only the issuer preauthorized
  vendor   no DepositAuth: accepts payment from any CRD holder
"""

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import httpx

from xrpl.clients import JsonRpcClient
from xrpl.models import (
    AccountSet,
    AccountSetAsfFlag,
    DepositPreauth,
    IssuedCurrencyAmount,
    Payment,
    TrustSet,
    TrustSetFlag,
)
from xrpl.models.requests import Tx
from xrpl.transaction import XRPLReliableSubmissionException, autofill_and_sign, submit_and_wait
from xrpl.wallet import Wallet, generate_faucet_wallet

TESTNET_URL = "https://s.altnet.rippletest.net:51234"
CURRENCY = "CRD"
TRUST_LIMIT = "1000000"
INITIAL_CREDIT = "100"


@dataclass
class World:
    client: JsonRpcClient
    issuer: Wallet
    vendor: Wallet
    farmer_a: Wallet
    farmer_b: Wallet
    stranger: Wallet

    def crd(self, value: str) -> IssuedCurrencyAmount:
        return IssuedCurrencyAmount(currency=CURRENCY, issuer=self.issuer.classic_address, value=value)


def submit_full(client: JsonRpcClient, tx, wallet: Wallet) -> tuple[str, dict]:
    """Like `submit`, but also return the validated transaction.

    The transaction is signed first so its hash is known before submission. A
    tec result is still applied to a validated ledger (fee charged, sequence
    consumed), so on rejection the transaction is looked up by hash and its
    ledger index returned as evidence.
    """
    signed = autofill_and_sign(tx, client, wallet)
    tx_hash = signed.get_hash()
    try:
        result = submit_and_wait(signed, client).result
    except XRPLReliableSubmissionException as exc:
        code = str(exc).removeprefix("Transaction failed: ").strip()
        found = client.request(Tx(transaction=tx_hash)).result
        return code, {"hash": tx_hash, "ledger_index": found.get("ledger_index", 0)}
    return result["meta"]["TransactionResult"], result


def submit(client: JsonRpcClient, tx, wallet: Wallet) -> str:
    """Submit and wait; return the engine result code (tesSUCCESS, tec..., tem...).

    xrpl-py raises on any non-success result, including tec codes that were
    applied to a validated ledger. For the scenarios a rejection is data, not
    an error, so the code is recovered from the exception message.
    """
    try:
        result = submit_and_wait(tx, client, wallet).result
    except XRPLReliableSubmissionException as exc:
        return str(exc).removeprefix("Transaction failed: ").strip()
    return result["meta"]["TransactionResult"]


def require_success(client: JsonRpcClient, tx, wallet: Wallet) -> None:
    code = submit(client, tx, wallet)
    if code != "tesSUCCESS":
        raise RuntimeError(f"setup step {type(tx).__name__} from {wallet.classic_address} failed: {code}")


def fund(client: JsonRpcClient, attempts: int = 4) -> Wallet:
    """Faucet funding with backoff: the public faucet times out under bursts."""
    for attempt in range(attempts):
        try:
            return generate_faucet_wallet(client)
        except httpx.TransportError:
            if attempt == attempts - 1:
                raise
            time.sleep(5 * 2**attempt)
    raise AssertionError("unreachable")


def build_world(url: str = TESTNET_URL) -> World:
    client = JsonRpcClient(url)
    with ThreadPoolExecutor(max_workers=2) as pool:
        wallets = list(pool.map(lambda _: fund(client), range(5)))
    w = World(client, *wallets)
    issuer = w.issuer.classic_address

    for flag in (
        AccountSetAsfFlag.ASF_ALLOW_TRUSTLINE_CLAWBACK,
        AccountSetAsfFlag.ASF_REQUIRE_AUTH,
        AccountSetAsfFlag.ASF_DEFAULT_RIPPLE,
    ):
        require_success(client, AccountSet(account=issuer, set_flag=flag), w.issuer)

    for holder in (w.vendor, w.farmer_a, w.farmer_b, w.stranger):
        require_success(client, TrustSet(account=holder.classic_address, limit_amount=w.crd(TRUST_LIMIT)), holder)

    for holder in (w.vendor, w.farmer_a, w.farmer_b):
        auth = TrustSet(
            account=issuer,
            limit_amount=IssuedCurrencyAmount(currency=CURRENCY, issuer=holder.classic_address, value="0"),
            flags=TrustSetFlag.TF_SET_AUTH,
        )
        require_success(client, auth, w.issuer)

    for farmer in (w.farmer_a, w.farmer_b):
        account = farmer.classic_address
        require_success(client, DepositPreauth(account=account, authorize=issuer), farmer)
        require_success(client, AccountSet(account=account, set_flag=AccountSetAsfFlag.ASF_DEPOSIT_AUTH), farmer)
        require_success(client, Payment(account=issuer, destination=account, amount=w.crd(INITIAL_CREDIT)), w.issuer)

    return w
