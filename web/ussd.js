// USSD menu logic for a feature-phone credit wallet. Pure: no network, no DOM.
//
// Mirrors how USSD gateways talk to a backend: every request carries the whole
// session so far as one string of choices joined by "*" (e.g. "2*1*50*1"), and
// the reply starts with "CON" (session continues, show menu) or "END" (session
// over). Actions that touch the ledger are not done inside the session; the
// reply says a confirmation SMS will follow, because a USSD session times out
// long before a farmer can be made to wait on anything slow.
"use strict";

(function (root) {
  const MAX_AMOUNT = 1000;

  function handle(text, ctx) {
    const parts = text === "" ? [] : text.split("*");
    const con = body => ({ type: "CON", text: body });
    const end = (body, action) => ({ type: "END", text: body, ...(action ? { action } : {}) });
    const amountOf = s => (/^\d{1,4}$/.test(s) && +s > 0 && +s <= MAX_AMOUNT ? +s : null);

    if (parts.length === 0) {
      return con("Input credit wallet\n1. Balance\n2. Pay vendor\n3. Repay loan\n4. Maize price\n0. Exit");
    }
    const [choice, ...rest] = parts;
    switch (choice) {
      case "0":
        return end("Goodbye.");
      case "1":
        return rest.length ? end("Invalid choice.") : end("Balance request received. You will get an SMS.", { kind: "balance" });
      case "4":
        return rest.length ? end("Invalid choice.") : end(ctx.priceText);
      case "2": {
        if (rest.length === 0) return con("Choose vendor\n" + ctx.vendors.map((v, i) => `${i + 1}. ${v.name}`).join("\n"));
        const vendor = ctx.vendors[Number(rest[0]) - 1];
        if (!vendor || !/^\d+$/.test(rest[0])) return end("Invalid vendor.");
        if (rest.length === 1) return con(`Amount to pay ${vendor.name} (1-${MAX_AMOUNT}):`);
        const amount = amountOf(rest[1]);
        if (amount === null) return end("Invalid amount.");
        if (rest.length === 2) return con(`Pay ${amount} credit to ${vendor.name}?\n1. Confirm\n2. Cancel`);
        if (rest.length === 3 && rest[2] === "1") return end("Payment request received. You will get an SMS.", { kind: "pay", vendor: vendor.id, amount });
        if (rest.length === 3 && rest[2] === "2") return end("Cancelled.");
        return end("Invalid choice.");
      }
      case "3": {
        if (rest.length === 0) return con(`Amount to repay (1-${MAX_AMOUNT}):`);
        const amount = amountOf(rest[0]);
        if (amount === null) return end("Invalid amount.");
        if (rest.length === 1) return con(`Repay ${amount} credit?\n1. Confirm\n2. Cancel`);
        if (rest.length === 2 && rest[1] === "1") return end("Repayment request received. You will get an SMS.", { kind: "repay", amount });
        if (rest.length === 2 && rest[1] === "2") return end("Cancelled.");
        return end("Invalid choice.");
      }
      default:
        return end("Invalid choice.");
    }
  }

  const api = { handle, MAX_AMOUNT };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.USSD = api;
})(typeof window !== "undefined" ? window : globalThis);
