// Results explorer. Renders web/data.json (built from results/*.json); computes nothing itself.
"use strict";

const SVGNS = "http://www.w3.org/2000/svg";
const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)"];

// ---------- small helpers ----------
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") node.textContent = v;
    else if (k === "class") node.className = v;
    else node.setAttribute(k, v);
  }
  for (const c of children) node.append(c);
  return node;
}
function svg(tag, attrs = {}) {
  const node = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}
function svgText(x, y, text, attrs = {}) {
  const t = svg("text", { x, y, ...attrs });
  t.textContent = text;
  return t;
}
const pct = (v, d = 1) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(d)}%`;
const share = (v, d = 1) => `${(100 * v).toFixed(d)}%`;
const millions = v => `${(v / 1e6).toFixed(2)}M GH₵`;
const niceStep = range => {
  const raw = range / 5, mag = 10 ** Math.floor(Math.log10(raw)), n = raw / mag;
  return (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * mag;
};
const widthOf = container => Math.max(340, Math.round(container.clientWidth || 560));
const redraws = [];
let resizeTimer;
addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => redraws.forEach(f => f()), 120); });
function onResize(f) { redraws.push(f); f(); }
// Category-label column: fixed on wide screens, a share of the width on phones.
const narrow = W => W < 480;
const labelCol = (W, wide) => narrow(W) ? Math.round(W * 0.46) : Math.min(wide, W * 0.4);
const labelSize = W => narrow(W) ? 10.5 : 12;

function ticks(lo, hi) {
  const step = niceStep(hi - lo), out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}

// ---------- tooltip ----------
const tip = document.getElementById("tooltip");
function showTip(evt, title, rows) {
  tip.replaceChildren();
  tip.append(el("div", { class: "tt-title", text: title }));
  for (const r of rows) {
    const row = el("div", { class: "tt-row" });
    if (r.color) { const key = el("i"); key.style.background = r.color; row.append(key); }
    row.append(el("b", { text: r.value }), el("span", { text: r.label }));
    tip.append(row);
  }
  tip.style.display = "block";
  const pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
  let x = evt.clientX + pad, y = evt.clientY + pad;
  if (x + w > innerWidth - 8) x = evt.clientX - w - pad;
  if (y + h > innerHeight - 8) y = evt.clientY - h - pad;
  tip.style.left = `${x}px`;
  tip.style.top = `${y}px`;
}
const hideTip = () => { tip.style.display = "none"; };
function focusTip(node, title, rows) {
  node.setAttribute("tabindex", "0");
  node.addEventListener("focus", () => {
    const b = node.getBoundingClientRect();
    showTip({ clientX: b.right, clientY: b.top }, title, rows);
  });
  node.addEventListener("blur", hideTip);
}

// ---------- tables ----------
function table(headers, rows, numeric = []) {
  const t = el("table", { class: "data" });
  const head = el("tr");
  headers.forEach((h, i) => head.append(el("th", { text: h, class: numeric.includes(i) ? "num" : "" })));
  t.append(el("thead", {}, head));
  const body = el("tbody");
  for (const r of rows) {
    const tr = el("tr");
    r.forEach((c, i) => tr.append(el("td", { text: c, class: numeric.includes(i) ? "num" : "" })));
    body.append(tr);
  }
  t.append(body);
  return el("div", { class: "table-wrap" }, t);
}
function setTable(id, headers, rows, numeric) {
  document.getElementById(`${id}-table`).replaceChildren(table(headers, rows, numeric));
}
document.addEventListener("click", e => {
  const b = e.target.closest("button[data-table]");
  if (!b) return;
  const view = document.getElementById(`${b.dataset.table}-table`);
  view.hidden = !view.hidden;
  b.textContent = view.hidden ? "Table" : "Chart only";
});

function legend(id, items) {
  const box = document.getElementById(id);
  box.replaceChildren();
  for (const it of items) {
    const key = el("i", { class: it.kind === "box" ? "box" : it.kind === "dash" ? "dash" : "" });
    if (it.kind !== "dash") key.style.background = it.color;
    box.append(el("span", {}, key, document.createTextNode(it.label)));
  }
}

function segmented(id, options, initial, onChange) {
  const box = document.getElementById(id);
  box.replaceChildren();
  const buttons = options.map(o => {
    const b = el("button", { type: "button", text: o.label, "aria-pressed": String(o.value === initial) });
    b.addEventListener("click", () => {
      buttons.forEach(x => x.setAttribute("aria-pressed", "false"));
      b.setAttribute("aria-pressed", "true");
      onChange(o.value);
    });
    box.append(b);
    return b;
  });
}

// ---------- charts ----------
// Horizontal dot (median) + range (min-max) per row.
function dotRange(container, rows, { xLabel, fmt }) {
  const W = widthOf(container), left = labelCol(W, 170), right = 56, rowH = 34, top = 8, H = top + rows.length * rowH + 34;
  const lo = Math.floor(Math.min(...rows.map(r => r.min)) / 10) * 10, hi = 100;
  const x = v => left + (v - lo) / (hi - lo) * (W - left - right);
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": xLabel });
  for (const t of ticks(lo, hi)) {
    s.append(svg("line", { x1: x(t), x2: x(t), y1: top, y2: H - 30, style: "stroke:var(--grid)" }));
    s.append(svgText(x(t), H - 14, t, { "text-anchor": "middle", "font-size": 11, style: "fill:var(--text-muted)" }));
  }
  rows.forEach((r, i) => {
    const y = top + i * rowH + rowH / 2;
    const g = svg("g", { class: "hit" });
    g.append(svg("rect", { x: 0, y: y - rowH / 2, width: W, height: rowH, fill: "transparent" }));
    g.append(svgText(left - 10, y + 4, r.label, { "text-anchor": "end", "font-size": labelSize(W), style: "fill:var(--text-primary)" }));
    g.append(svg("line", { x1: x(r.min), x2: x(r.max), y1: y, y2: y, "stroke-width": 2, "stroke-linecap": "round", style: "stroke:var(--series-1)" }));
    g.append(svg("circle", { cx: x(r.median), cy: y, r: 5, "stroke-width": 2, style: "fill:var(--series-1);stroke:var(--surface-1)" }));
    g.append(svgText(x(r.max) + 8, y + 4, fmt(r.median), { "font-size": 11.5, style: "fill:var(--text-secondary)" }));
    const rowsTip = [{ value: fmt(r.median), label: "median" }, { value: `${fmt(r.min)} – ${fmt(r.max)}`, label: "range" }];
    g.addEventListener("pointermove", e => showTip(e, r.label, rowsTip));
    g.addEventListener("pointerleave", hideTip);
    focusTip(g, r.label, rowsTip);
    s.append(g);
  });
  s.append(svgText((left + W - right) / 2, H - 1, xLabel, { "text-anchor": "middle", "font-size": 11, style: "fill:var(--text-secondary)" }));
  container.replaceChildren(s);
}

// Multi-series line chart with a snapping crosshair; one tooltip lists every series.
function lineChart(container, { xs, series, xFmt, yFmt, xLabel, yLabel, yMin }) {
  const W = widthOf(container), H = 300, left = 52, right = 16, top = 12, bottom = 44;
  const all = series.flatMap(s => s.values);
  const lo = yMin ?? Math.min(...all), hi = Math.max(...all);
  const pad = (hi - lo) * 0.06 || 0.01;
  const y0 = yMin ?? lo - pad, y1 = hi + pad;
  const x = i => left + (xs[i] - xs[0]) / (xs[xs.length - 1] - xs[0]) * (W - left - right);
  const y = v => top + (1 - (v - y0) / (y1 - y0)) * (H - top - bottom);
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": yLabel });
  for (const t of ticks(y0, y1)) {
    s.append(svg("line", { x1: left, x2: W - right, y1: y(t), y2: y(t), style: "stroke:var(--grid)" }));
    s.append(svgText(left - 8, y(t) + 4, yFmt(t), { "text-anchor": "end", "font-size": 11, style: "fill:var(--text-muted)" }));
  }
  s.append(svg("line", { x1: left, x2: W - right, y1: H - bottom, y2: H - bottom, style: "stroke:var(--axis)" }));
  xs.forEach((v, i) => s.append(svgText(x(i), H - bottom + 16, xFmt(v), { "text-anchor": "middle", "font-size": 11, style: "fill:var(--text-muted)" })));
  s.append(svgText((left + W - right) / 2, H - 6, xLabel, { "text-anchor": "middle", "font-size": 11, style: "fill:var(--text-secondary)" }));
  s.append(svgText(12, top + (H - top - bottom) / 2, yLabel, { "text-anchor": "middle", "font-size": 11, transform: `rotate(-90 12 ${top + (H - top - bottom) / 2})`, style: "fill:var(--text-secondary)" }));
  for (const ser of series) {
    const d = ser.values.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join("");
    s.append(svg("path", { d, fill: "none", "stroke-width": ser.dashed ? 1.5 : 2, "stroke-linejoin": "round", "stroke-linecap": "round",
      "stroke-dasharray": ser.dashed ? "5 4" : "", style: `stroke:${ser.color}` }));
    if (!ser.dashed) ser.values.forEach((v, i) => s.append(svg("circle", { cx: x(i), cy: y(v), r: 4, "stroke-width": 2, style: `fill:${ser.color};stroke:var(--surface-1)` })));
  }
  const cross = svg("line", { y1: top, y2: H - bottom, visibility: "hidden", style: "stroke:var(--text-muted)" });
  s.append(cross);
  const hit = svg("rect", { x: left, y: top, width: W - left - right, height: H - top - bottom, fill: "transparent", tabindex: "0" });
  const at = i => {
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
    return series.map(ser => ({ color: ser.color, value: yFmt(ser.values[i]), label: ser.name }));
  };
  hit.addEventListener("pointermove", e => {
    const b = s.getBoundingClientRect(), px = (e.clientX - b.left) / b.width * W;
    let best = 0;
    xs.forEach((_, i) => { if (Math.abs(x(i) - px) < Math.abs(x(best) - px)) best = i; });
    showTip(e, `${xLabel}: ${xFmt(xs[best])}`, at(best));
  });
  hit.addEventListener("pointerleave", () => { hideTip(); cross.setAttribute("visibility", "hidden"); });
  hit.addEventListener("focus", () => { const b = s.getBoundingClientRect(); showTip({ clientX: b.right - 40, clientY: b.top }, `${xLabel}: ${xFmt(xs[xs.length - 1])}`, at(xs.length - 1)); });
  hit.addEventListener("blur", () => { hideTip(); cross.setAttribute("visibility", "hidden"); });
  s.append(hit);
  container.replaceChildren(s);
}

// Horizontal bars from zero, value at the tip.
function barsH(container, rows, { fmt, xLabel }) {
  const W = widthOf(container), left = labelCol(W, 190), right = narrow(W) ? 56 : 80, rowH = 40, top = 6, H = top + rows.length * rowH + 30;
  const hi = Math.max(...rows.map(r => r.value)) * 1.02;
  const x = v => left + v / hi * (W - left - right);
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": xLabel });
  for (const t of ticks(0, hi)) {
    s.append(svg("line", { x1: x(t), x2: x(t), y1: top, y2: H - 26, style: "stroke:var(--grid)" }));
    s.append(svgText(x(t), H - 12, fmt(t, true), { "text-anchor": "middle", "font-size": 11, style: "fill:var(--text-muted)" }));
  }
  rows.forEach((r, i) => {
    const y = top + i * rowH + rowH / 2, h = 20, w = Math.max(x(r.value) - left, 1), rad = Math.min(4, w);
    const g = svg("g");
    g.append(svg("rect", { x: 0, y: y - rowH / 2, width: W, height: rowH, fill: "transparent" }));
    g.append(svgText(left - 10, y + 4, r.label, { "text-anchor": "end", "font-size": labelSize(W), style: "fill:var(--text-primary)" }));
    const d = `M${left},${y - h / 2}H${left + w - rad}Q${left + w},${y - h / 2} ${left + w},${y - h / 2 + rad}V${y + h / 2 - rad}Q${left + w},${y + h / 2} ${left + w - rad},${y + h / 2}H${left}Z`;
    g.append(svg("path", { d, style: `fill:${r.color}` }));
    g.append(svgText(left + w + 8, y + 4, fmt(r.value), { "font-size": 11.5, style: "fill:var(--text-secondary)" }));
    g.addEventListener("pointermove", e => showTip(e, r.label, r.tip));
    g.addEventListener("pointerleave", hideTip);
    focusTip(g, r.label, r.tip);
    s.append(g);
  });
  container.replaceChildren(s);
}

// Tornado: for each assumption, a low bar and a high bar drawn from the base value.
function tornado(container, rows, base, { fmt, xLabel }) {
  const W = widthOf(container), left = labelCol(W, 220), right = 20, rowH = 30, top = 8, H = top + rows.length * rowH + 34;
  const vals = rows.flatMap(r => [r.low, r.high]).concat(base);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo) * 0.06 || 1; lo -= pad; hi += pad;
  const x = v => left + (v - lo) / (hi - lo) * (W - left - right);
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": xLabel });
  for (const t of ticks(lo, hi)) {
    s.append(svg("line", { x1: x(t), x2: x(t), y1: top, y2: H - 30, style: "stroke:var(--grid)" }));
    s.append(svgText(x(t), H - 16, fmt(t), { "text-anchor": "middle", "font-size": 10.5, style: "fill:var(--text-muted)" }));
  }
  rows.forEach((r, i) => {
    const y = top + i * rowH + rowH / 2;
    const g = svg("g");
    g.append(svg("rect", { x: 0, y: y - rowH / 2, width: W, height: rowH, fill: "transparent" }));
    g.append(svgText(left - 10, y + 4, r.label, { "text-anchor": "end", "font-size": narrow(W) ? 10 : 11.5, style: "fill:var(--text-primary)" }));
    [[r.low, "var(--series-1)", -5.5], [r.high, "var(--series-2)", 5.5]].forEach(([v, c, dy]) => {
      const a = Math.min(x(base), x(v)), w = Math.max(Math.abs(x(v) - x(base)), 1);
      g.append(svg("rect", { x: a, y: y + dy - 4.5, width: w, height: 9, rx: 2, style: `fill:${c}` }));
    });
    const tipRows = [
      { color: "var(--series-1)", value: fmt(r.low), label: `low (${r.lowSetting})` },
      { color: "var(--series-2)", value: fmt(r.high), label: `high (${r.highSetting})` },
      { value: fmt(base), label: "base" },
    ];
    g.addEventListener("pointermove", e => showTip(e, r.label, tipRows));
    g.addEventListener("pointerleave", hideTip);
    focusTip(g, r.label, tipRows);
    s.append(g);
  });
  s.append(svg("line", { x1: x(base), x2: x(base), y1: top, y2: H - 30, "stroke-width": 1.5, style: "stroke:var(--text-primary)" }));
  s.append(svgText((left + W - right) / 2, H - 1, xLabel, { "text-anchor": "middle", "font-size": 11, style: "fill:var(--text-secondary)" }));
  container.replaceChildren(s);
}

// ---------- sections ----------
function renderEnforcement(d) {
  const accts = d.enforcement.accounts;
  const cap = document.getElementById("enf-caption");
  cap.replaceChildren(document.createTextNode(`${d.enforcement.outcomes.filter(o => o.matches).length} of ${d.enforcement.outcomes.length} outcomes as expected, run ${d.date}. Accounts: `));
  Object.entries(accts).forEach(([role, addr], i) => {
    if (i) cap.append(document.createTextNode(", "));
    cap.append(el("a", { href: `https://testnet.xrpl.org/accounts/${addr}`, text: role, target: "_blank", rel: "noopener" }));
  });
  cap.append(document.createTextNode(" (testnet is reset from time to time, so links may expire)."));
  const t = document.getElementById("enf-table");
  const head = el("tr");
  ["#", "Route", "Observed", "Ledger stops it?", "Enforced by", "Note", "Transaction"].forEach(h => head.append(el("th", { text: h })));
  const body = el("tbody");
  for (const o of d.enforcement.outcomes) {
    const by = o.enforced_by;
    const chip = by.startsWith("L1") ? el("span", { class: "chip good", text: "✓ Ledger" })
      : by.startsWith("nobody") ? el("span", { class: "chip bad", text: "✕ Not stopped" })
      : by.startsWith("field") ? el("span", { class: "chip neutral", text: "– Off-ledger" })
      : el("span", { class: "chip neutral", text: "– Allowed" });
    body.append(el("tr", {},
      el("td", { text: o.id }), el("td", { text: o.route.replace(/->/g, "→") }),
      el("td", {}, el("code", { text: o.observed })), el("td", {}, chip),
      el("td", { text: by }), el("td", { text: o.note || "" }),
      el("td", {}, o.tx_hash
        ? el("a", { href: `https://testnet.xrpl.org/transactions/${o.tx_hash}`, target: "_blank", rel: "noopener",
                    text: `ledger ${o.ledger_index}`, title: o.tx_hash })
        : document.createTextNode("–"))));
  }
  t.replaceChildren(el("thead", {}, head), body);
}

function renderAllocation(d) {
  const a = d.allocation;
  document.getElementById("gap-caption").textContent = `Expected gain as % of optimum; dot = median, line = min–max over ${a.instances} instances.`;
  onResize(() => dotRange(document.getElementById("gap-chart"), a.gap.map(r => ({ ...r, label: r.method })), { xLabel: "% of exact optimum", fmt: v => `${v.toFixed(1)}%` }));
  setTable("gap", ["Method", "Median %", "Min %", "Max %"], a.gap.map(r => [r.method, r.median.toFixed(1), r.min.toFixed(1), r.max.toFixed(1)]), [1, 2, 3]);
  const f = a.frontier;
  const series = [
    { name: "Exact (MILP)", color: SERIES[0], values: f.map(p => p.milp / 1000) },
    { name: "Risk-aware greedy, λ searched", color: SERIES[2], values: f.map(p => p.greedy_risk / 1000) },
    { name: "Risk-aware greedy, λ fixed", color: SERIES[3], values: f.map(p => p.greedy_fixed / 1000) },
    { name: "Budget-only greedy", color: SERIES[1], values: f.map(p => p.greedy / 1000) },
  ];
  onResize(() => lineChart(document.getElementById("frontier-chart"), {
    xs: f.map(p => 100 * p.loss_cap_share), series, yMin: 0,
    xFmt: v => `${v.toFixed(0)}%`, yFmt: v => v.toFixed(0),
    xLabel: "Expected-loss cap, % of budget", yLabel: "Expected gain (thousand units)",
  }));
  legend("frontier-legend", series.map(s => ({ color: s.color, label: s.name })));
  setTable("frontier", ["Loss cap % of budget", "Exact", "λ searched", "λ fixed", "Budget-only greedy"],
    f.map(p => [(100 * p.loss_cap_share).toFixed(0), p.milp.toFixed(0), p.greedy_risk.toFixed(0), p.greedy_fixed.toFixed(0), p.greedy.toFixed(0)]), [0, 1, 2, 3, 4]);
}

const POLICY = { equal: "Equal amounts", no_history: "Risk-aware, no history", ledger: "Risk-aware, ledger history", known_type: "Known type (benchmark)" };
const RETURN = { low_return: "Low, RCT-motivated", trial_plots: "Trial plots", naive_agronomic: "Naive agronomic" };
const CUSTODY = { custodial: "Custodial", self_custody: "Farmer-held keys" };

function tile(label, value, delta) {
  return el("div", { class: "tile" }, el("div", { class: "label", text: label }), el("div", { class: "value", text: value }),
    ...(delta ? [el("div", { class: "delta", text: delta })] : []));
}

function renderSimulation(d) {
  const sim = d.simulation, state = { ret: "trial_plots", custody: "custodial" };
  const sel = document.getElementById("sim-return");
  for (const [k, v] of Object.entries(sim.returns)) sel.append(el("option", { value: k, text: `${RETURN[k]} (${v} GH₵ per GH₵)` }));
  sel.value = state.ret;
  const draw = () => {
    const sc = sim.scenarios[`${state.ret}/${state.custody}`], p = sc.policies, pr = sc.paired;
    document.getElementById("sim-tiles").replaceChildren(
      tile("Ledger history vs no history", pct(pr.ledger_vs_no_history.pct), `±${pr.ledger_vs_no_history.ci_pct.toFixed(1)} (95%, paired)`),
      tile("Risk-aware vs equal amounts", pct(pr.no_history_vs_equal.pct), `±${pr.no_history_vs_equal.ci_pct.toFixed(1)} (95%, paired)`),
      tile("Default rate, ledger policy", share(p.ledger.default_rate), "share of loans"),
      tile("Fund after 4 seasons", `${p.ledger.final_fund.toFixed(2)}×`, "of initial capital, ledger policy"));
    document.getElementById("sim-caption").textContent = `${RETURN[state.ret]} returns, ${CUSTODY[state.custody].toLowerCase()}; mean of ${sim.replications.toLocaleString()} replications, million GH₵ at 2024 prices.`;
    const rows = Object.keys(POLICY).map((k, i) => ({
      label: POLICY[k], value: p[k].gain, color: k === "known_type" ? "var(--text-muted)" : SERIES[0],
      tip: [{ value: millions(p[k].gain), label: "total harvest gain" }, { value: `±${(p[k].gain_ci / 1e6).toFixed(3)}M`, label: "95% interval" },
        { value: share(p[k].default_rate), label: "default rate" }, { value: `${p[k].final_fund.toFixed(2)}×`, label: "fund left" }],
    }));
    barsH(document.getElementById("sim-chart"), rows, { fmt: (v, axis) => axis ? (v / 1e6).toFixed(1) : `${(v / 1e6).toFixed(2)}M`, xLabel: "Harvest gain" });
    setTable("sim", ["Policy", "Gain (M GH₵)", "Default rate", "Fund left"],
      Object.keys(POLICY).map(k => [POLICY[k], (p[k].gain / 1e6).toFixed(2), share(p[k].default_rate), p[k].final_fund.toFixed(2)]), [1, 2, 3]);
  };
  sel.addEventListener("change", () => { state.ret = sel.value; draw(); });
  segmented("sim-custody", Object.entries(CUSTODY).map(([value, label]) => ({ value, label })), state.custody, v => { state.custody = v; draw(); });
  onResize(draw);
}

function renderRisk(d) {
  const r = d.risk, names = { land: "Land only", history: "+ loan/default history", ledger: "+ on-ledger diversion", all_div: "+ all diversion (not observable)" };
  const xs = Array.from({ length: r.seasons - 1 }, (_, i) => i + 2);
  const draw = custody => {
    const a = r.auc[`trial_plots/${custody}`];
    const series = Object.keys(names).map((k, i) => ({ name: names[k], color: SERIES[i], values: a[k] }));
    series.push({ name: "Known type (benchmark)", color: "var(--text-muted)", values: a.known_type, dashed: true });
    lineChart(document.getElementById("risk-chart"), { xs, series, xFmt: v => `${v}`, yFmt: v => v.toFixed(2), xLabel: "Test season", yLabel: "AUC, out of time" });
    legend("risk-legend", series.map(s => ({ color: s.color, label: s.name, kind: s.dashed ? "dash" : "line" })));
    document.getElementById("risk-caption").textContent = `Trial-plot returns, ${CUSTODY[custody].toLowerCase()}; trained on all earlier seasons; mean of ${r.replications} replications.`;
    setTable("risk", ["Test season", ...series.map(s => s.name)], xs.map((s, i) => [String(s), ...series.map(x => x.values[i].toFixed(3))]), series.map((_, i) => i + 1));
  };
  let current = "self_custody";
  segmented("risk-custody", Object.entries(CUSTODY).map(([value, label]) => ({ value, label })), current, v => { current = v; draw(v); });
  onResize(() => draw(current));
  const o = r.observability;
  document.getElementById("obs-caption").textContent =
    `In the full simulation (self-custody), raising the on-ledger share of diversion from 0% to 100% moves the ledger policy's gain over no history only from ${pct(o["0.0"].ledger_vs_no_history_pct)} to ${pct(o["1.0"].ledger_vs_no_history_pct)}.`;
}

const METRICS = {
  ledger_gain: { label: "Ledger history vs no history", fmt: v => pct(v), note: "% more harvest gain, custodial" },
  targeting_gain: { label: "Risk-aware vs equal amounts", fmt: v => pct(v), note: "% more harvest gain, custodial" },
  custody_cost: { label: "Self-custody vs custodial", fmt: v => pct(v), note: "% change in harvest gain" },
  fund_left: { label: "Fund left after 4 seasons", fmt: v => `${v.toFixed(2)}×`, note: "of initial capital" },
};

function renderSensitivity(d) {
  const s = d.sensitivity, state = { param: "default_target", level: "high", metric: "ledger_gain" };
  const pSel = document.getElementById("sens-param");
  for (const [k, label] of Object.entries(s.labels)) pSel.append(el("option", { value: k, text: label }));
  pSel.value = state.param;
  const mSel = document.getElementById("sens-metric");
  for (const [k, m] of Object.entries(METRICS)) mSel.append(el("option", { value: k, text: m.label }));
  const drawTiles = () => {
    const [lo, hi] = s.ranges[state.param];
    const vals = state.level === "base" ? s.base : s.points[state.param][state.level];
    document.getElementById("sens-tiles").replaceChildren(...Object.entries(METRICS).map(([k, m]) => {
      const diff = vals[k] - s.base[k];
      const delta = state.level === "base" ? m.note : `${k === "fund_left" ? (diff >= 0 ? "+" : "−") + Math.abs(diff).toFixed(2) : (diff >= 0 ? "+" : "−") + Math.abs(diff).toFixed(1) + " pts"} vs base`;
      return tile(m.label, m.fmt(vals[k]), delta);
    }));
    segmented("sens-level", [{ value: "low", label: `Low (${lo})` }, { value: "base", label: "Base" }, { value: "high", label: `High (${hi})` }], state.level,
      v => { state.level = v; drawTiles(); });
  };
  const drawTornado = () => {
    const m = METRICS[state.metric];
    const rows = Object.keys(s.labels).map(k => ({
      label: s.labels[k], low: s.points[k].low[state.metric], high: s.points[k].high[state.metric],
      lowSetting: s.ranges[k][0], highSetting: s.ranges[k][1],
    })).sort((a, b) => Math.abs(b.high - b.low) - Math.abs(a.high - a.low));
    tornado(document.getElementById("tornado-chart"), rows, s.base[state.metric], { fmt: m.fmt, xLabel: m.label });
    document.getElementById("sens-caption").textContent = `${m.label}, ${m.note}. Each assumption at its low and high value, everything else at base (dark line); ${s.replications} replications per point, trial-plot returns. Sorted by swing.`;
    legend("tornado-legend", [{ color: "var(--series-1)", label: "Assumption at low value", kind: "box" }, { color: "var(--series-2)", label: "Assumption at high value", kind: "box" }]);
    setTable("tornado", ["Assumption", "Low setting", "Result", "High setting", "Result"],
      rows.map(r => [r.label, String(r.lowSetting), m.fmt(r.low), String(r.highSetting), m.fmt(r.high)]), [1, 2, 3, 4]);
  };
  pSel.addEventListener("change", () => { state.param = pSel.value; drawTiles(); });
  mSel.addEventListener("change", () => { state.metric = mSel.value; drawTornado(); });
  drawTiles();
  onResize(drawTornado);
}

// ---------- theme ----------
(function theme() {
  const root = document.documentElement, btn = document.getElementById("theme");
  try { const saved = localStorage.getItem("theme"); if (saved) root.dataset.theme = saved; } catch (_) { /* storage unavailable */ }
  btn.addEventListener("click", () => {
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("theme", root.dataset.theme); } catch (_) { /* storage unavailable */ }
  });
})();

fetch("data.json").then(r => r.json()).then(d => {
  document.getElementById("data-date").textContent = `results of ${d.date}`;
  renderEnforcement(d);
  renderAllocation(d);
  renderSimulation(d);
  renderRisk(d);
  renderSensitivity(d);
}).catch(err => {
  document.querySelector("main").prepend(el("p", { class: "notice", text: `Could not load data.json (${err.message}). Serve this folder over HTTP, e.g. python3 -m http.server.` }));
});
