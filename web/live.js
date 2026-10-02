// Live testnet run of the escape-route scenarios, in the browser, with xrpl.js.
// Mirrors src/xrpl_input_credit/ledger/scenarios.py. Testnet only: the wallets
// are created from the public faucet, live only in this tab, and hold no value.
"use strict";

(function live() {
  const { ASF, TF, LIMIT, txLink } = LedgerKit;

  const SCENARIOS = [
    { id: "S1", route: "farmer → approved vendor", expected: "tesSUCCESS" },
    { id: "S2", route: "farmer → farmer (direct payment)", expected: "tecNO_PERMISSION" },
    { id: "S3", route: "farmer → unauthorised account", expected: "tecPATH_DRY" },
    { id: "S4a", route: "ripple credit through farmer B, flags as created", expected: "tesSUCCESS; B +10" },
    { id: "S4b", route: "same, after NoRipple on B's issuer line", expected: "tecPATH_DRY; B +0" },
    { id: "S4c", route: "same, after B clears that NoRipple", expected: "tesSUCCESS; B +10" },
    { id: "S5", route: "B clears own DepositAuth, then farmer → farmer", expected: "tesSUCCESS" },
    { id: "S6a", route: "farmer sells credit for XRP on the open DEX", expected: "tesSUCCESS; B +10" },
    { id: "S8a", route: "issuer freezes A's line; A → vendor", expected: "tecPATH_DRY" },
    { id: "S8b", route: "issuer claws back 5 credit from A", expected: "tesSUCCESS; A −5" },
  ];

  const $ = id => document.getElementById(id);
  const status = text => { $("live-status").textContent = text; };
  const log = (text, hash) => {
    const row = document.createElement("div");
    row.textContent = text;
    if (hash) { row.append(" "); row.append(txLink(hash)); }
    $("live-log").prepend(row);
  };

  function renderTable() {
    const t = $("live-table");
    const head = document.createElement("tr");
    ["#", "Route", "Expected", "Observed", "Result", "Transaction"].forEach(h => {
      const th = document.createElement("th"); th.textContent = h; head.append(th);
    });
    const body = document.createElement("tbody");
    for (const s of SCENARIOS) {
      const tr = document.createElement("tr");
      tr.id = `live-${s.id}`;
      [s.id, s.route, s.expected, "", "", ""].forEach((v, i) => {
        const td = document.createElement("td");
        if (i === 2) { const c = document.createElement("code"); c.textContent = v; td.append(c); } else td.textContent = v;
        tr.append(td);
      });
      body.append(tr);
    }
    const thead = document.createElement("thead"); thead.append(head);
    t.replaceChildren(thead, body);
  }

  function setRow(id, observed, hash) {
    const s = SCENARIOS.find(x => x.id === id), tr = $(`live-${id}`);
    const obs = document.createElement("code"); obs.textContent = observed;
    tr.children[3].replaceChildren(obs);
    const chip = document.createElement("span");
    const ok = observed === s.expected;
    chip.className = `chip ${ok ? "good" : "bad"}`;
    chip.textContent = ok ? "✓ as expected" : "✕ unexpected";
    tr.children[4].replaceChildren(chip);
    if (hash) tr.children[5].replaceChildren(txLink(hash, "view"));
  }

  async function run() {
    const btn = $("live-run");
    btn.disabled = true;
    renderTable();
    $("live-log").replaceChildren();
    let kit;
    try {
      status("Connecting to testnet…");
      kit = await LedgerKit.open(log);
      const { submit, must, fund, crd, balance } = kit;

      status("Funding five testnet accounts from the faucet…");
      const issuer = await fund("issuer"), vendor = await fund("vendor");
      const a = await fund("farmer A"), b = await fund("farmer B"), stranger = await fund("stranger");
      const I = issuer.classicAddress;
      const c = value => crd(value, I);
      const bal = w => balance(w, I);
      const pay = (from, to, value = "10") => submit({ TransactionType: "Payment", Account: from.classicAddress, Destination: to.classicAddress, Amount: c(value) }, from, `${from === a ? "A" : "B"} pays ${value}`);

      status("Configuring issuer, trust lines and farmer accounts…");
      await kit.setupIssuer(issuer, [[vendor, "vendor"], [a, "A"], [b, "B"], [stranger, "stranger"]]);
      for (const [w, name] of [[vendor, "vendor"], [a, "A"], [b, "B"]]) await kit.authorise(issuer, w, name);
      for (const [w, name] of [[a, "A"], [b, "B"]]) {
        await kit.lockFarmer(issuer, w, name);
        await must({ TransactionType: "Payment", Account: I, Destination: w.classicAddress, Amount: c("100") }, issuer, `issuer lends 100 to ${name}`);
      }

      status("Running escape routes…");
      let r = await pay(a, vendor); setRow("S1", r.code, r.hash);
      r = await pay(a, b); setRow("S2", r.code, r.hash);
      r = await pay(a, stranger); setRow("S3", r.code, r.hash);

      await must({ TransactionType: "TrustSet", Account: a.classicAddress, LimitAmount: crd(LIMIT, b.classicAddress) }, a, "A trusts B-issued credit");
      const ripple = async id => {
        const before = await bal(b);
        const res = await submit({
          TransactionType: "Payment", Account: a.classicAddress, Destination: a.classicAddress,
          Amount: crd("10", b.classicAddress), SendMax: c("10"), Paths: [[{ account: b.classicAddress }]],
        }, a, `${id}: A ripples through B`);
        const delta = (await bal(b)) - before;
        setRow(id, `${res.code}; B ${delta >= 0 ? "+" : "−"}${Math.abs(delta)}`, res.hash);
      };
      await ripple("S4a");
      await must({ TransactionType: "TrustSet", Account: b.classicAddress, LimitAmount: c(LIMIT), Flags: TF.setNoRipple }, b, "B sets NoRipple");
      await ripple("S4b");
      await must({ TransactionType: "TrustSet", Account: b.classicAddress, LimitAmount: c(LIMIT), Flags: TF.clearNoRipple }, b, "B clears NoRipple");
      await ripple("S4c");

      await must({ TransactionType: "AccountSet", Account: b.classicAddress, ClearFlag: ASF.depositAuth }, b, "B clears DepositAuth");
      r = await pay(a, b); setRow("S5", r.code, r.hash);
      await must({ TransactionType: "AccountSet", Account: b.classicAddress, SetFlag: ASF.depositAuth }, b, "B restores DepositAuth");

      await must({ TransactionType: "OfferCreate", Account: a.classicAddress, TakerGets: c("10"), TakerPays: xrpl.xrpToDrops(10) }, a, "A offers 10 credit for 10 XRP");
      let before = await bal(b);
      r = await submit({ TransactionType: "OfferCreate", Account: b.classicAddress, TakerGets: xrpl.xrpToDrops(10), TakerPays: c("10") }, b, "B takes the offer");
      let delta = (await bal(b)) - before;
      setRow("S6a", `${r.code}; B ${delta >= 0 ? "+" : "−"}${Math.abs(delta)}`, r.hash);

      await must({ TransactionType: "TrustSet", Account: I, LimitAmount: crd("0", a.classicAddress), Flags: TF.setFreeze }, issuer, "issuer freezes A");
      r = await pay(a, vendor); setRow("S8a", r.code, r.hash);
      await must({ TransactionType: "TrustSet", Account: I, LimitAmount: crd("0", a.classicAddress), Flags: TF.clearFreeze }, issuer, "issuer unfreezes A");
      before = await bal(a);
      r = await submit({ TransactionType: "Clawback", Account: I, Amount: crd("5", a.classicAddress) }, issuer, "issuer claws back 5 from A");
      delta = (await bal(a)) - before;
      setRow("S8b", `${r.code}; A ${delta >= 0 ? "+" : "−"}${Math.abs(delta)}`, r.hash);

      const rows = SCENARIOS.map(s => $(`live-${s.id}`).children[4].textContent);
      status(`Done: ${rows.filter(t => t.startsWith("✓")).length} of ${SCENARIOS.length} as expected. S6b/S6c (permissioned DEX) and S7 (off-ledger) are covered by the Python suite only.`);
    } catch (e) {
      status(`Stopped: ${e.message}`);
      log(`stopped: ${e.message}`);
    } finally {
      if (kit) await kit.close();
      btn.disabled = false;
    }
  }

  renderTable();
  $("live-run").addEventListener("click", () => {
    if (typeof xrpl === "undefined") { status("xrpl.js did not load (offline or blocked CDN)."); return; }
    run();
  });
})();
