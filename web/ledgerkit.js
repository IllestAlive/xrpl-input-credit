// Shared XRPL testnet helpers for the live demos (live.js, custodial.js).
// Mirrors src/xrpl_input_credit/ledger/world.py. Testnet only.
"use strict";

(function (root) {
  const URL_WSS = "wss://s.altnet.rippletest.net:51233";
  const EXPLORER = "https://testnet.xrpl.org";
  const CRD = "CRD", LIMIT = "1000000";
  // Ledger flag values (rippled): AccountSet asf* and TrustSet tf*.
  const ASF = { requireAuth: 2, defaultRipple: 8, depositAuth: 9, allowClawback: 16 };
  const TF = { setAuth: 0x00010000, setNoRipple: 0x00020000, clearNoRipple: 0x00040000, setFreeze: 0x00100000, clearFreeze: 0x00200000 };

  async function open(log) {
    const client = new xrpl.Client(URL_WSS);
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
    const crd = (value, issuer) => ({ currency: CRD, issuer, value });
    const balance = async (wallet, issuer) => {
      const r = await client.request({ command: "account_lines", account: wallet.classicAddress, peer: issuer });
      const line = r.result.lines.find(l => l.currency === CRD);
      return line ? Number(line.balance) : 0;
    };

    // Issuer with RequireAuth, DefaultRipple and clawback; holders get authorised trust lines.
    const setupIssuer = async (issuer, holders) => {
      const I = issuer.classicAddress;
      for (const [flag, name] of [[ASF.allowClawback, "AllowTrustLineClawback"], [ASF.requireAuth, "RequireAuth"], [ASF.defaultRipple, "DefaultRipple"]])
        await must({ TransactionType: "AccountSet", Account: I, SetFlag: flag }, issuer, `issuer sets ${name}`);
      for (const [w, name] of holders)
        await must({ TransactionType: "TrustSet", Account: w.classicAddress, LimitAmount: crd(LIMIT, I) }, w, `${name} opens trust line`);
    };
    const authorise = async (issuer, w, name) =>
      must({ TransactionType: "TrustSet", Account: issuer.classicAddress, LimitAmount: crd("0", w.classicAddress), Flags: TF.setAuth }, issuer, `issuer authorises ${name}`);
    // Farmer accepts deposits from the issuer only.
    const lockFarmer = async (issuer, w, name) => {
      await must({ TransactionType: "DepositPreauth", Account: w.classicAddress, Authorize: issuer.classicAddress }, w, `${name} preauthorises issuer`);
      await must({ TransactionType: "AccountSet", Account: w.classicAddress, SetFlag: ASF.depositAuth }, w, `${name} sets DepositAuth`);
    };

    return { client, submit, must, fund, crd, balance, setupIssuer, authorise, lockFarmer,
             close: () => client.disconnect().catch(() => {}) };
  }

  function txLink(hash, text) {
    const a = document.createElement("a");
    a.href = `${EXPLORER}/transactions/${hash}`; a.target = "_blank"; a.rel = "noopener";
    a.textContent = text || `${hash.slice(0, 10)}…`;
    a.title = hash;
    return a;
  }

  root.LedgerKit = { open, txLink, ASF, TF, CRD, LIMIT, EXPLORER };
})(window);
