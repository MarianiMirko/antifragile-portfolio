/* Portfolio page */
(async () => {
  await App.init("portfolio.html");
  const { usd, usdSigned, pct, pctSigned, sign, esc, num } = App;
  const [s, pos, exp, reb, why] = await Promise.all([
    App.data("summary.json"), App.data("positions.json", { positions: [], closed: [], transactions: [] }),
    App.data("exposures.json", { sector: [], country: [], asset_class: [] }),
    App.data("rebalance_suggestions.json", { table: [], suggestions: [] }),
    App.getJSON("content/trade_rationale.json", { rationales: [] }),
  ]);
  if (!s) return;
  App.statusLine(document.getElementById("updated"), s);

  const stat = (label, value, sub = "", cls = "") => `<div class="stat"><dt>${label}</dt><dd class="${cls}">${value}${sub ? `<small>${sub}</small>` : ""}</dd></div>`;
  document.getElementById("totals").innerHTML = [
    stat("Fund value", usd(pos.nav), `started with ${usd(s.initial_capital)}`),
    stat("Invested", usd(pos.invested), `${pct(1 - pos.cash_weight, 1)} of the fund`),
    stat("Cash", usd(pos.cash), `${pct(pos.cash_weight, 1)} of the fund`),
    stat("Unrealised P&amp;L", usdSigned(pos.unrealized_total), "on open positions", sign(pos.unrealized_total)),
    stat("Realised P&amp;L", usdSigned(pos.realized_total), "on closed trades", sign(pos.realized_total)),
  ].join("");

  /* positions */
  const tb = document.querySelector("#positions tbody");
  if (!pos.positions.length) {
    document.querySelector("#positions").closest(".table-scroll").hidden = true;
    document.getElementById("positions-empty").hidden = false;
  } else {
    tb.innerHTML = pos.positions.map((p) => `<tr>
      <td class="l ticker" data-v="${esc(p.ticker)}">${esc(p.ticker)}<small>${esc(p.name)}</small></td>
      <td class="l" data-v="${esc(p.sector)}">${esc(p.sector)}<small>${esc(p.country)}</small></td>
      <td data-v="${p.shares}">${num(p.shares)}</td>
      <td data-v="${p.avg_cost}">${usd(p.avg_cost, 2)}</td>
      <td data-v="${p.price}">${usd(p.price, 2)}</td>
      <td data-v="${p.value}">${usd(p.value)}</td>
      <td data-v="${p.weight}">${pct(p.weight, 1)}</td>
      <td data-v="${p.unrealized}" class="${sign(p.unrealized)}">${usdSigned(p.unrealized)}<small>${pctSigned(p.unrealized_pct, 1)}</small></td>
      <td data-v="${p.day_pnl}" class="${sign(p.day_pnl)}">${usdSigned(p.day_pnl)}<small>${pctSigned(p.day_pct)}</small></td>
      <td data-v="${p.contribution}" class="${sign(p.contribution)}">${pctSigned(p.contribution)}</td></tr>`).join("");
    const day = pos.positions.reduce((a, p) => a + p.day_pnl, 0), contr = pos.positions.reduce((a, p) => a + p.contribution, 0);
    document.querySelector("#positions tfoot").innerHTML = `<tr><td class="l" colspan="5">Open positions</td>
      <td>${usd(pos.invested)}</td><td>${pct(1 - pos.cash_weight, 1)}</td>
      <td class="${sign(pos.unrealized_total)}">${usdSigned(pos.unrealized_total)}</td>
      <td class="${sign(day)}">${usdSigned(day)}</td><td class="${sign(contr)}">${pctSigned(contr)}</td></tr>
      <tr><td class="l" colspan="5" style="border-top:0;font-weight:400">Cash</td><td style="border-top:0;font-weight:400">${usd(pos.cash)}</td>
      <td style="border-top:0;font-weight:400">${pct(pos.cash_weight, 1)}</td><td colspan="3" style="border-top:0"></td></tr>`;
    App.sortable(document.getElementById("positions"));
  }

  /* portfolio map and contribution waterfall */
  if (pos.positions.length) {
    const mapEl = document.getElementById("map");
    Viz.treemap(mapEl, pos.positions, pos.cash, "total");
    document.querySelectorAll("[data-map]").forEach((btn) => btn.addEventListener("click", () => {
      document.querySelectorAll("[data-map]").forEach((x) => x.setAttribute("aria-pressed", x === btn));
      Viz.treemap(mapEl, pos.positions, pos.cash, btn.dataset.map);
    }));
    const steps = pos.positions.map((p) => ({ name: p.ticker, full: p.name, value: p.unrealized + p.realized }))
      .concat(pos.closed.map((c) => ({ name: c.ticker + " (closed)", full: c.name, value: c.realized, closed: true })));
    Viz.waterfall(document.getElementById("waterfall"), s.initial_capital, steps, pos.nav);
  } else {
    document.getElementById("map-block").hidden = true;
    document.getElementById("wf-block").hidden = true;
  }

  /* exposures */
  App.bars(document.getElementById("exp-sector"), exp.sector);
  App.bars(document.getElementById("exp-country"), exp.country);
  App.bars(document.getElementById("exp-asset"), exp.asset_class);

  /* targets and rebalancing */
  document.getElementById("tgt-intro").textContent = reb.table.length
    ? (reb.min_order_value
      ? `We propose a trade when bringing a position back to its target takes an order of at least ${usd(reb.min_order_value)}. Smaller orders are not placed: each one costs a commission and changes almost nothing. These are proposals: the portfolio manager approves every order before it is placed.`
      : `We propose a trade when a position is more than ${pct(reb.drift_threshold, 0)} of the fund away from its target. These are proposals: the portfolio manager approves every order before it is placed.`)
    : "No target weights are set yet. Add them to content/targets.json and this table fills in.";
  if (!reb.table.some((r) => r.target_weight != null)) document.getElementById("tgt-intro").textContent = "No target weights are set yet. Add them to content/targets.json and this table fills in.";
  document.getElementById("tgt-placeholder").hidden = !reb.targets_are_placeholder;
  if (!reb.table.some((r) => r.target_weight != null)) document.querySelector("#targets").closest(".table-scroll").hidden = true;
  document.querySelector("#targets tbody").innerHTML = reb.table.map((r) => {
    const d = r.drift;
    return `<tr><td class="l ticker">${esc(r.ticker)}<small>${esc(r.name || "")}</small></td>
      <td>${pct(r.weight, 1)}</td><td>${r.target_weight == null ? "not set" : pct(r.target_weight, 1)}</td>
      <td class="${d == null ? "" : r.flag ? (d > 0 ? "down" : "up") : "flat"}">${d == null ? "–" : (d < 0 ? "−" : "+") + Math.abs(d * 100).toFixed(1) + " pts"}</td>
      <td class="l">${r.flag ? `<span class="pill pill-${r.action}">${r.action === "buy" ? "Buy" : "Sell"}</span>` : r.blocked ? `<span class="down">${esc(r.blocked)}</span>` : '<span class="muted">within range</span>'}</td>
      <td>${r.flag ? num(r.shares) : ""}</td><td>${r.flag ? usd(r.est_value) : ""}</td></tr>`;
  }).join("");

  /* closed positions */
  if (pos.closed.length) {
    document.getElementById("realized-block").hidden = false;
    document.querySelector("#realized tbody").innerHTML = pos.closed.map((c) => `<tr>
      <td class="l ticker">${esc(c.ticker)}</td><td class="l">${esc(c.name)}</td>
      <td class="${sign(c.realized)}">${usdSigned(c.realized)}</td><td class="${sign(c.contribution)}">${pctSigned(c.contribution)}</td></tr>`).join("");
  }

  /* trade log with rationale, matched on date + ticker + side */
  const key = (d, t, side) => `${String(d).slice(0, 10)}|${t}|${side}`.toUpperCase();
  const reasons = new Map((why.rationales || []).map((r) => [key(r.date, r.ticker, r.side), r]));
  const nyDay = (iso) => new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date(iso));
  const side = { buy: "Buy", sell: "Sell", short: "Short", cover: "Cover" };
  if (!pos.transactions.length) {
    document.querySelector("#trades").closest(".table-scroll").hidden = true;
    document.getElementById("trades-empty").hidden = false;
  } else {
    document.querySelector("#trades tbody").innerHTML = pos.transactions.map((t) => {
      const r = reasons.get(key(nyDay(t.date), t.ticker, t.side));
      return `<tr><td class="l">${App.dateTime(t.date)}</td><td class="l ticker">${esc(t.ticker)}</td>
        <td class="l"><span class="pill pill-${t.side === "buy" || t.side === "cover" ? "buy" : "sell"}">${side[t.side]}</span></td>
        <td>${num(t.shares)}</td><td>${usd(t.price, 2)}</td><td>${usd(t.amount)}</td>
        <td class="l wrap-cell">${r ? esc(r.rationale) : '<span class="muted">Rationale not written yet</span>'}</td>
        <td class="l">${r ? esc(r.approved_by || "") : ""}</td></tr>`;
    }).join("");
  }
})();
