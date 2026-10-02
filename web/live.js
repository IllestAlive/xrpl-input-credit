// Live testnet run of the escape-route scenarios, in the browser, with xrpl.js.
// Mirrors src/xrpl_input_credit/ledger/{world,scenarios}.py. Testnet only: the
// wallets are created from the public faucet, live only in this tab, and hold no value.
"use strict";

(function live() {
  const URL_WSS = "wss://s.altnet.rippletest.net:51233";
  const EXPLORER = "https://testnet.xrpl.org";
  const CRD = "CRD", LIMIT = "1000000";
  // Ledger flag values (rippled): AccountSet asf* and TrustSet tf*.
  const ASF = { requireAuth: 2, defaultRipple: 8, depositAuth: 9, allowClawback: 16 };
  const TF = { setAuth: 0x00010000, setNoRipple: 0x00020000, clearNoRipple: 0x00040000, setFreeze: 0x00100000, clearFreeze: 0x00200000 };

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
    if (hash) {
      row.append(" ");
      const a = document.createElement("a");
      a.href = `${EXPLORER}/transactions/${hash}`; a.target = "_blank"; a.rel = "noopener";
      a.textContent = `${hash.slice(0, 10)}…`;
      row.append(a);
    }
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
    if (hash) {
      const a = document.createElement("a");
      a.href = `${EXPLORER}/transactions/${hash}`; a.target = "_blank"; a.rel = "noopener"; a.textContent = "view";
      tr.children[5].replaceChildren(a);
    }
  }

  async function run() {
    const btn = $("live-run");
    btn.disabled = true;
    renderTable();
    $("live-log").replaceChildren();
    const client = new xrpl.Client(URL_WSS);
    try {
      status("Connecting to testnet…");
      await client.connect();

      // Submit and wait; a rejection is data, so return its engine code instead of throwing.
      const submit = async (tx, wallet, label) => {
        try {
          const r = await client.submitAndWait(tx, { wallet, autofill: true });
          const code = r.result.meta.TransactionResult;
          log(`${label}: ${code}`, r.result.hash);
          return { code, hash: r.result.hash };
        } catch (e) {
          const m = /\b(te[cfmlr][A-Z_]+)\b/.exec(e?.data?.engine_result || e?.message || "");
          const code = m ? m[1] : `error: ${e.message}`;
          log(`${label}: ${code}`);
          return { code, hash: null };
        }
      };
      const must = async (tx, wallet, label) => {
        const r = await submit(tx, wallet, label);
        if (r.code !== "tesSUCCESS") throw new Error(`setup step failed: ${label} → ${r.code}`);
      };
      const fund = async role => {
        for (let attempt = 0; attempt < 4; attempt++) {
          try {
            const { wallet } = await client.fundWallet();
            log(`funded ${role}: ${wallet.classicAddress}`);
            return wallet;
          } catch (e) {
            log(`faucet retry for ${role} (${e.message})`);
            await new Promise(r => setTimeout(r, 4000 * 2 ** attempt));
          }
        }
        throw new Error("the testnet faucet did not respond; try again later");
      };

      status("Funding five testnet accounts from the faucet…");
      const issuer = await fund("issuer"), vendor = await fund("vendor");
      const a = await fund("farmer A"), b = await fund("farmer B"), stranger = await fund("stranger");
      const I = issuer.classicAddress;
      const crd = (value, iss = I) => ({ currency: CRD, issuer: iss, value });
      const balance = async (w, peer = I) => {
        const r = await client.request({ command: "account_lines", account: w.classicAddress, peer });
        const line = r.result.lines.find(l => l.currency === CRD);
        return line ? Number(line.balance) : 0;
      };
      const pay = (from, to, value = "10") => submit({ TransactionType: "Payment", Account: from.classicAddress, Destination: to.classicAddress, Amount: crd(value) }, from, `${from === a ? "A" : "B"} pays ${value}`);

      status("Configuring issuer, trust lines and farmer accounts…");
      for (const [flag, name] of [[ASF.allowClawback, "AllowTrustLineClawback"], [ASF.requireAuth, "RequireAuth"], [ASF.defaultRipple, "DefaultRipple"]])
        await must({ TransactionType: "AccountSet", Account: I, SetFlag: flag }, issuer, `issuer sets ${name}`);
      for (const [w, name] of [[vendor, "vendor"], [a, "A"], [b, "B"], [stranger, "stranger"]])
        await must({ TransactionType: "TrustSet", Account: w.classicAddress, LimitAmount: crd(LIMIT) }, w, `${name} opens trust line`);
      for (const [w, name] of [[vendor, "vendor"], [a, "A"], [b, "B"]])
        await must({ TransactionType: "TrustSet", Account: I, LimitAmount: crd("0", w.classicAddress), Flags: TF.setAuth }, issuer, `issuer authorises ${name}`);
      for (const [w, name] of [[a, "A"], [b, "B"]]) {
        await must({ TransactionType: "DepositPreauth", Account: w.classicAddress, Authorize: I }, w, `${name} preauthorises issuer`);
        await must({ TransactionType: "AccountSet", Account: w.classicAddress, SetFlag: ASF.depositAuth }, w, `${name} sets DepositAuth`);
        await must({ TransactionType: "Payment", Account: I, Destination: w.classicAddress, Amount: crd("100") }, issuer, `issuer lends 100 to ${name}`);
      }

      status("Running escape routes…");
      let r = await pay(a, vendor); setRow("S1", r.code, r.hash);
      r = await pay(a, b); setRow("S2", r.code, r.hash);
      r = await pay(a, stranger); setRow("S3", r.code, r.hash);

      await must({ TransactionType: "TrustSet", Account: a.classicAddress, LimitAmount: crd(LIMIT, b.classicAddress) }, a, "A trusts B-issued credit");
      const ripple = async id => {
        const before = await balance(b);
        const res = await submit({
          TransactionType: "Payment", Account: a.classicAddress, Destination: a.classicAddress,
          Amount: crd("10", b.classicAddress), SendMax: crd("10"), Paths: [[{ account: b.classicAddress }]],
        }, a, `${id}: A ripples through B`);
        const delta = (await balance(b)) - before;
        setRow(id, `${res.code}; B ${delta >= 0 ? "+" : "−"}${Math.abs(delta)}`, res.hash);
      };
      await ripple("S4a");
      await must({ TransactionType: "TrustSet", Account: b.classicAddress, LimitAmount: crd(LIMIT), Flags: TF.setNoRipple }, b, "B sets NoRipple");
      await ripple("S4b");
      await must({ TransactionType: "TrustSet", Account: b.classicAddress, LimitAmount: crd(LIMIT), Flags: TF.clearNoRipple }, b, "B clears NoRipple");
      await ripple("S4c");

      await must({ TransactionType: "AccountSet", Account: b.classicAddress, ClearFlag: ASF.depositAuth }, b, "B clears DepositAuth");
      r = await pay(a, b); setRow("S5", r.code, r.hash);
      await must({ TransactionType: "AccountSet", Account: b.classicAddress, SetFlag: ASF.depositAuth }, b, "B restores DepositAuth");

      await must({ TransactionType: "OfferCreate", Account: a.classicAddress, TakerGets: crd("10"), TakerPays: xrpl.xrpToDrops(10) }, a, "A offers 10 credit for 10 XRP");
      let before = await balance(b);
      r = await submit({ TransactionType: "OfferCreate", Account: b.classicAddress, TakerGets: xrpl.xrpToDrops(10), TakerPays: crd("10") }, b, "B takes the offer");
      let delta = (await balance(b)) - before;
      setRow("S6a", `${r.code}; B ${delta >= 0 ? "+" : "−"}${Math.abs(delta)}`, r.hash);

      await must({ TransactionType: "TrustSet", Account: I, LimitAmount: crd("0", a.classicAddress), Flags: TF.setFreeze }, issuer, "issuer freezes A");
      r = await pay(a, vendor); setRow("S8a", r.code, r.hash);
      await must({ TransactionType: "TrustSet", Account: I, LimitAmount: crd("0", a.classicAddress), Flags: TF.clearFreeze }, issuer, "issuer unfreezes A");
      before = await balance(a);
      r = await submit({ TransactionType: "Clawback", Account: I, Amount: crd("5", a.classicAddress) }, issuer, "issuer claws back 5 from A");
      delta = (await balance(a)) - before;
      setRow("S8b", `${r.code}; A ${delta >= 0 ? "+" : "−"}${Math.abs(delta)}`, r.hash);

      const rows = SCENARIOS.map(s => $(`live-${s.id}`).children[4].textContent);
      status(`Done: ${rows.filter(t => t.startsWith("✓")).length} of ${SCENARIOS.length} as expected. S6b/S6c (permissioned DEX) and S7 (off-ledger) are covered by the Python suite only.`);
    } catch (e) {
      status(`Stopped: ${e.message}`);
      log(`stopped: ${e.message}`);
    } finally {
      try { await client.disconnect(); } catch (_) { /* already closed */ }
      btn.disabled = false;
    }
  }

  renderTable();
  $("live-run").addEventListener("click", () => {
    if (typeof xrpl === "undefined") { status("xrpl.js did not load (offline or blocked CDN)."); return; }
    run();
  });
})();
