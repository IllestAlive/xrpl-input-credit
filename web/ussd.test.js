// Run with: node web/ussd.test.js
"use strict";
const assert = require("node:assert/strict");
const { handle } = require("./ussd.js");

const ctx = { vendors: [{ id: "agro", name: "Agro inputs" }], priceText: "Maize: GHS 929 per 100 kg" };
const run = text => handle(text, ctx);

// Main menu and exits.
assert.equal(run("").type, "CON");
assert.match(run("").text, /1\. Balance/);
assert.deepEqual(run("0"), { type: "END", text: "Goodbye." });
assert.equal(run("9").text, "Invalid choice.");

// Balance and price end the session; only balance needs the ledger.
assert.deepEqual(run("1").action, { kind: "balance" });
assert.equal(run("4").text, ctx.priceText);
assert.equal(run("4").action, undefined);

// Pay: vendor -> amount -> confirm.
assert.equal(run("2").type, "CON");
assert.equal(run("2*1").type, "CON");
assert.match(run("2*1*50").text, /Pay 50 credit to Agro inputs\?/);
assert.deepEqual(run("2*1*50*1").action, { kind: "pay", vendor: "agro", amount: 50 });
assert.equal(run("2*1*50*2").text, "Cancelled.");
assert.equal(run("2*1*50*2").action, undefined);
assert.equal(run("2*2").text, "Invalid vendor.");
assert.equal(run("2*1*0").text, "Invalid amount.");
assert.equal(run("2*1*1001").text, "Invalid amount.");
assert.equal(run("2*1*5.5").text, "Invalid amount.");
assert.equal(run("2*1*50*1*1").text, "Invalid choice.");

// Repay: amount -> confirm.
assert.deepEqual(run("3*20*1").action, { kind: "repay", amount: 20 });
assert.equal(run("3*abc").text, "Invalid amount.");

// No menu path lets the farmer change account flags: the only ledger actions are these three.
const kinds = new Set();
for (const t of ["1", "2*1*1*1", "3*1*1"]) kinds.add(run(t).action.kind);
assert.deepEqual([...kinds].sort(), ["balance", "pay", "repay"]);

console.log("ussd: all assertions passed");
