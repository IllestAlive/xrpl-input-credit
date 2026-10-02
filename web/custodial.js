// Feature-phone channel demo: a USSD menu (ussd.js) on the phone, and a custodial
// operator in this tab that holds the farmer's testnet key and turns menu choices
// into XRP Ledger transactions. The phone never sees a key, which is the point:
// with no way to sign, the farmer cannot clear DepositAuth or NoRipple (S4c, S5),
// so the ledger's restrictions hold. The price is trust in the operator and issuer.
"use strict";

(function custodial() {
  const { TF, txLink } = LedgerKit;
  const DIAL = "*384#";
  const VENDORS = [{ id: "agro", name: "Agro inputs" }];
  const $ = id => document.getElementById(id);

  const state = { kit: null, issuer: null, vendor: null, farmer: null, ready: false, session: null };

  // ---------- operator side ----------
  const opsLog = (text, hash) => {
    const row = document.createElement("div");
    row.textContent = text;
    if (hash) { row.append(" "); row.append(txLink(hash)); }
    $("ussd-ops").prepend(row);
  };
  const setStatus = text => { $("ussd-status").textContent = text; };

  async function start() {
    if (typeof xrpl === "undefined") { setStatus("xrpl.js did not load (offline or blocked CDN)."); return; }
    const btn = $("ussd-start");
    btn.disabled = true;
    try {
      setStatus("Operator connecting to testnet…");
      const kit = await LedgerKit.open(opsLog);
      setStatus("Funding issuer, vendor and one farmer from the faucet…");
      const issuer = await kit.fund("issuer"), vendor = await kit.fund("vendor"), farmer = await kit.fund("farmer (key held by operator)");
      const I = issuer.classicAddress;
      setStatus("Configuring: RequireAuth, authorised lines, DepositAuth, NoRipple…");
      await kit.setupIssuer(issuer, [[vendor, "vendor"], [farmer, "farmer"]]);
      await kit.authorise(issuer, vendor, "vendor");
      await kit.authorise(issuer, farmer, "farmer");
      await kit.lockFarmer(issuer, farmer, "farmer");
      // The hardening that S4b showed is needed, and that only a key holder could undo (S4c).
      await kit.must({ TransactionType: "TrustSet", Account: farmer.classicAddress, LimitAmount: kit.crd(LedgerKit.LIMIT, I), Flags: TF.setNoRipple }, farmer, "farmer line: NoRipple");
      await kit.must({ TransactionType: "Payment", Account: I, Destination: farmer.classicAddress, Amount: kit.crd("100", I) }, issuer, "issuer lends 100 credit");
      Object.assign(state, { kit, issuer, vendor, farmer, ready: true });
      VENDORS[0].address = vendor.classicAddress;
      $("ussd-keys").textContent = `Operator holds the farmer key for ${farmer.classicAddress}. The phone only sends menu choices.`;
      setStatus("Ready. Dial *384# on the phone.");
    } catch (e) {
      setStatus(`Stopped: ${e.message}`);
      btn.disabled = false;
    }
  }

  async function execute(action, input) {
    if (!state.ready) { sms("Service unavailable: start the operator first."); return; }
    const { kit, issuer, vendor, farmer } = state;
    const I = issuer.classicAddress;
    const bal = () => kit.balance(farmer, I);
    if (action.kind === "balance") {
      const b = await bal();
      opsLog(`USSD ${input} → account_lines (read only): ${b} credit`);
      sms(`Your credit balance is ${b}.`);
      return;
    }
    const to = action.kind === "pay" ? vendor : issuer;
    const label = action.kind === "pay" ? `USSD ${input} → Payment ${action.amount} to vendor` : `USSD ${input} → Payment ${action.amount} to issuer (repay)`;
    const r = await kit.submit({ TransactionType: "Payment", Account: farmer.classicAddress, Destination: to.classicAddress, Amount: kit.crd(String(action.amount), I) }, farmer, label);
    const b = await bal();
    const what = action.kind === "pay" ? `Paid ${action.amount} credit to ${VENDORS[0].name}` : `Repaid ${action.amount} credit`;
    // The farmer gets plain words; the engine code stays in the operator log.
    const reason = ["tecPATH_PARTIAL", "tecPATH_DRY", "tecUNFUNDED_PAYMENT"].includes(r.code) ? "not enough credit" : "service error";
    sms(r.code === "tesSUCCESS" ? `${what}. Balance ${b}. Ref ${r.hash.slice(0, 8)}.` : `Request failed: ${reason}. Balance ${b}.`);
  }

  // ---------- phone side ----------
  const screen = text => { $("ussd-screen").textContent = text; };
  function sms(text) {
    const row = document.createElement("div");
    row.className = "sms";
    row.textContent = text;
    $("ussd-sms").prepend(row);
  }

  function context() {
    const p = window.APP_DATA?.ussd;
    const priceText = p ? `Maize, ${p.year} avg rural wholesale: GHS ${Math.round(p.ghs_per_100kg)} per 100 kg (${p.source}).` : "Price service unavailable.";
    return { vendors: VENDORS, priceText };
  }

  function send() {
    const input = $("ussd-input").value.trim();
    $("ussd-input").value = "";
    if (state.session === null) {
      if (input !== DIAL) { screen(`Unknown code. Dial ${DIAL}.`); return; }
      state.session = [];
    } else {
      if (input === "") return;
      state.session.push(input);
    }
    const text = state.session.join("*");
    const res = USSD.handle(text, context());
    screen(res.text);
    if (res.type === "END") {
      state.session = null;
      if (res.action) execute(res.action, text);
    }
  }

  function hangUp() {
    state.session = null;
    $("ussd-input").value = "";
    screen(`Dial ${DIAL} to open the credit wallet.`);
  }

  // Keypad.
  const pad = $("ussd-pad");
  for (const k of ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"]) {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = k; b.setAttribute("aria-label", `key ${k}`);
    b.addEventListener("click", () => { $("ussd-input").value += k; $("ussd-input").focus(); });
    pad.append(b);
  }
  $("ussd-send").addEventListener("click", send);
  $("ussd-input").addEventListener("keydown", e => { if (e.key === "Enter") send(); });
  $("ussd-end").addEventListener("click", hangUp);
  $("ussd-start").addEventListener("click", start);
  hangUp();
})();
