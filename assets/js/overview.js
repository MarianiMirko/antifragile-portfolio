/* Overview page */
(async () => {
  const cfg = await App.init("index.html");
  const { usd, usdSigned, pct, pctSigned, sign, esc, num } = App;
  const [s, alerts, pos, exp, c1h, c1d, note, rules, why, board] = await Promise.all([
    App.data("summary.json"), App.data("alerts.json", { alerts: [], rules: [] }), App.data("positions.json", { positions: [] }),
    App.data("exposures.json", { sector: [] }), App.data("candles_1h.json", { candles: [], benchmark: [] }),
    App.data("candles_1d.json", { candles: [], benchmark: [] }), App.getText("content/pm_note.md"),
    App.getJSON("config/rules.json", { limits: {} }),
    App.getJSON("content/trade_rationale.json", { rationales: [] }), App.data("leaderboard.json"),
  ]);
  if (!s) { document.getElementById("nav-value").textContent = "No data yet"; return; }

  /* ---- hero: count up to the fund value, once ---- */
  const navEl = document.getElementById("nav-value");
  const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const from = s.initial_capital, to = s.nav, t0 = performance.now(), dur = 1400;
  const draw = (v) => { navEl.textContent = num(Math.round(v)); };
  if (still || Math.abs(to - from) < 1) draw(to);
  else {
    const tick = (t) => {
      const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 4);
      draw(from + (to - from) * e);
      if (k < 1) requestAnimationFrame(tick);
    };
    draw(from); requestAnimationFrame(tick);
  }
  navEl.setAttribute("aria-label", usd(to));

  document.getElementById("hero-changes").innerHTML = `
    <span><b class="${sign(s.day_change)}">${usdSigned(s.day_change)} (${pctSigned(s.day_change_pct)})</b> <span class="lbl">on the last trading day</span></span>
    <span><b class="${sign(s.total_change)}">${usdSigned(s.total_change)} (${pctSigned(s.total_return)})</b> <span class="lbl">since ${App.date(s.start_date)}</span></span>`;
  App.statusLine(document.getElementById("updated"), s);

  const b = s.benchmark || {};
  const kpi = (label, value, sub = "", cls = "") => `<div class="kpi"><dt>${label}</dt><dd class="${cls}">${value}${sub ? `<small>${sub}</small>` : ""}</dd></div>`;
  document.getElementById("kpis").innerHTML = [
    kpi("Return since inception", pctSigned(s.total_return), `over ${num(s.trading_days)} trading days`, sign(s.total_return)),
    kpi(`Against ${esc(b.name || "benchmark")}`, s.excess_return == null ? "–" : pctSigned(s.excess_return), b.return == null ? "benchmark not loaded yet" : `benchmark ${pctSigned(b.return)}`, sign(s.excess_return)),
    kpi("Volatility, annualised", pct(s.volatility, 1), s.volatility_basis || "needs price history"),
    kpi("Sharpe ratio", s.sharpe == null ? "–" : num(s.sharpe, 2), s.sharpe == null ? "shown after 10 trading days" : "annualised, since inception"),
    kpi("Maximum drawdown", pct(s.max_drawdown, 2), "worst fall from a peak"),
    kpi("Cash", pct(s.cash_weight, 1), usd(s.cash)),
    kpi("Positions", num(s.n_positions), `${usd(s.invested)} invested`),
    kpi("Days to go", num(s.days_left), `the game ends on ${App.date(s.end_date)}`),
  ].join("");

  /* ---- PM note, alerts ---- */
  document.getElementById("pm-note").innerHTML = App.md(note) || '<p class="muted">No note yet.</p>';
  const breaches = alerts.alerts.filter((a) => a.severity === "breach").length;
  const warns = alerts.alerts.filter((a) => a.severity === "warning").length;
  document.getElementById("rules-score").innerHTML = alerts.alerts.length
    ? `${breaches} ${breaches === 1 ? "breach" : "breaches"}, ${warns} ${warns === 1 ? "warning" : "warnings"}`
    : "Nothing needs attention";
  const label = { breach: "Breach", warning: "Warning", info: "Note" };
  document.getElementById("alerts").innerHTML = alerts.alerts.length
    ? alerts.alerts.map((a) => `<li class="alert"><span class="tag tag-${a.severity}">${label[a.severity]}</span><strong>${esc(a.title)}</strong><p>${esc(a.message)}</p></li>`).join("")
    : `<li class="alert"><span class="tag tag-ok">OK</span><strong>No alerts</strong><p>No limit is exceeded, no stop-loss is hit and no position has drifted beyond its threshold.</p></li>`;

  /* ---- holdings and sectors ---- */
  const top = pos.positions.slice(0, 10).map((p) => ({ name: p.name, sub: p.ticker, weight: p.weight }));
  const topEl = document.getElementById("top-holdings");
  if (top.length) App.bars(topEl, top, { ranked: true });
  else topEl.outerHTML = '<p class="chart-empty">The fund is fully in cash. Holdings appear here after the first trade.</p>';
  const lim = rules.limits.max_sector_weight;
  const secMax = Math.max(lim || 0, ...exp.sector.map((x) => x.weight));
  App.bars(document.getElementById("sectors"), exp.sector, { max: secMax, limit: lim });
  if (lim) document.getElementById("sector-limit-note").innerHTML = `<i aria-hidden="true"></i> Sector limit of ${pct(lim, 0)}`;

  /* ---- game ranking: other participants are shown without names ---- */
  if (board && board.field && board.field.length) {
    const cap = s.initial_capital, field = board.field.map((v) => v / cap - 1);
    const ours = board.our_net_worth / cap - 1, usIdx = board.field.findIndex((v) => Math.abs(v - board.our_net_worth) < 0.005);
    const max = Math.max(...field.map(Math.abs), 0.001), median = [...field].sort((a, b) => a - b)[Math.floor(field.length / 2)];
    const ord = (n) => n + (["th", "st", "nd", "rd"][(n % 100 > 10 && n % 100 < 14) ? 0 : n % 10] || "th");
    document.getElementById("rank-block").hidden = false;
    document.getElementById("rank-intro").textContent = `Return of each of the ${board.players} participants since the start, as read from MarketWatch on ${App.date(board.as_of)}. Other participants are shown without names.`;
    const stat = (l, v, sub = "") => `<div class="stat"><dt>${l}</dt><dd>${v}${sub ? `<small>${sub}</small>` : ""}</dd></div>`;
    document.getElementById("rank-stats").innerHTML = [
      stat("Our rank", board.our_rank ? `${ord(board.our_rank)} of ${board.players}` : "Not ranked yet", board.our_rank ? "" : "MarketWatch ranks a player after the first trade"),
      stat("Our return", pctSigned(ours)), stat("Leader", pctSigned(field[0]), `${usdSigned(board.field[0] - board.our_net_worth)} against us`),
      stat("Median participant", pctSigned(median)),
    ].join("");
    document.getElementById("rank-list").innerHTML = field.map((r, i) => {
      const w = Math.abs(r) / max * 50, us = i === usIdx;
      return `<li class="rank-row${us ? " us" : ""}"><span class="rank-n">${us ? "Us" : i + 1}</span>
        <span class="rank-track" aria-hidden="true"><span class="rank-fill" style="width:${Math.max(w, 0.4)}%;${r >= 0 ? "left:50%" : `right:50%`}"></span></span>
        <span class="rank-v ${sign(r)}">${pctSigned(r)}</span></li>`;
    }).join("");
  }

  /* ---- candlestick chart ---- */
  const el = document.getElementById("nav-chart");
  const readout = document.getElementById("chart-readout");
  document.getElementById("bench-label").textContent = `Benchmark: ${b.name || b.ticker || ""}, rebased to ${usd(s.initial_capital)}`;
  if (!window.LightweightCharts || !c1h.candles.length) { el.innerHTML = '<p class="chart-empty">The chart appears after the first price update.</p>'; return; }
  const C = App.COLORS;
  const money = (v) => "$" + (v / 1e6).toFixed(2) + "M";
  const chart = LightweightCharts.createChart(el, {
    autoSize: true,
    layout: { background: { color: "#FFFFFF" }, textColor: C.muted, fontFamily: '"IBM Plex Sans", system-ui, sans-serif', fontSize: 12 },
    grid: { vertLines: { visible: false }, horzLines: { color: C.grid } },
    rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.08, bottom: 0.08 } },
    timeScale: { borderVisible: false, timeVisible: true, secondsVisible: false, rightOffset: 2 },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal, vertLine: { color: C.muted, labelBackgroundColor: C.ink }, horzLine: { color: C.muted, labelBackgroundColor: C.ink } },
    localization: { priceFormatter: money },
    handleScale: { mouseWheel: false },
  });
  const styles = {
    colour: { upColor: C.up, downColor: C.down, borderUpColor: C.up, borderDownColor: C.down, wickUpColor: C.up, wickDownColor: C.down },
    mono: { upColor: "#FFFFFF", downColor: C.ink, borderUpColor: C.ink, borderDownColor: C.ink, wickUpColor: C.ink, wickDownColor: C.ink },
  };
  const candles = chart.addCandlestickSeries({ ...styles.colour, priceLineVisible: false });
  const bench = chart.addLineSeries({ color: C.bench, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerRadius: 4 });
  chart.priceScale("right").applyOptions({ autoScale: true });

  const shift = (rows) => rows.map((r) => ({ ...r, time: r.time + App.tzOffsetSec(r.time) }));
  const sets = { "1h": { c: shift(c1h.candles), b: shift(c1h.benchmark) }, "1d": { c: c1d.candles, b: c1d.benchmark } };
  let tf = "1h", showBench = true, showTrades = true;

  /* our trades as markers on the candles; hovering a marked candle lists them with the reason */
  const tradeBox = document.getElementById("trade-readout");
  const txs = [...(pos.transactions || [])].reverse();
  const isBuy = (t) => t.side === "buy" || t.side === "cover";
  const nyDay = (iso) => new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date(iso));
  const rkey = (d, t, sd) => `${String(d).slice(0, 10)}|${t}|${sd}`.toUpperCase();
  const reasons = new Map((why.rationales || []).map((r) => [rkey(r.date, r.ticker, r.side), r.rationale]));
  const raw = { "1h": c1h.candles, "1d": c1d.candles };
  const tradeMap = { "1h": new Map(), "1d": new Map() };
  function buildMarkers(key) {
    const groups = new Map();
    txs.forEach((t) => {
      const ts = Date.parse(t.date) / 1000;
      let idx = -1;
      if (key === "1h") { for (let i = 0; i < raw[key].length && raw[key][i].time <= ts; i++) idx = i; }
      else idx = raw[key].findIndex((c) => c.time === nyDay(t.date));
      if (idx >= 0) { if (!groups.has(idx)) groups.set(idx, []); groups.get(idx).push(t); }
    });
    tradeMap[key].clear();
    return [...groups.entries()].sort((a, b) => a[0] - b[0]).map(([idx, list]) => {
      const time = sets[key].c[idx].time, up = list.filter(isBuy).length >= list.length / 2;
      tradeMap[key].set(time, list);
      return { time, position: up ? "belowBar" : "aboveBar", shape: up ? "arrowUp" : "arrowDown", color: C.navy,
               text: list.length === 1 ? list[0].ticker : `${list.length} trades` };
    });
  }
  function showTradesFor(time) {
    const list = showTrades && time != null ? tradeMap[tf].get(time) : null;
    if (!list) { tradeBox.innerHTML = txs.length && showTrades ? '<span class="muted">Arrows mark our trades. Point at one to see what we did and why.</span>' : ""; return; }
    tradeBox.innerHTML = list.slice(0, 6).map((t) => {
      const why_ = reasons.get(rkey(nyDay(t.date), t.ticker, t.side));
      return `<p><span class="pill pill-${isBuy(t) ? "buy" : "sell"}">${isBuy(t) ? "Buy" : "Sell"}</span> <b>${num(t.shares)} ${esc(t.ticker)}</b> at ${usd(t.price, 2)}${why_ ? `. ${esc(why_)}` : ""}</p>`;
    }).join("") + (list.length > 6 ? `<p class="muted">and ${list.length - 6} more on the Portfolio page</p>` : "");
  }
  const fmtTime = (t) => typeof t === "string" ? App.date(t)
    : new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(t * 1000));
  function showRow(c, bv) {
    if (!c) { readout.textContent = ""; return; }
    const ch = c.close - c.open;
    readout.innerHTML = `<span>${fmtTime(c.time)}</span><span>Open <b>${usd(c.open)}</b></span><span>High <b>${usd(c.high)}</b></span>
      <span>Low <b>${usd(c.low)}</b></span><span>Close <b>${usd(c.close)}</b></span>
      <span class="${sign(ch)}">${usdSigned(ch)} (${pctSigned(ch / c.open)})</span>
      ${showBench && bv != null ? `<span>Benchmark <b>${usd(bv)}</b></span>` : ""}`;
  }
  function load() {
    const d = sets[tf];
    candles.setData(d.c);
    bench.setData(showBench ? d.b : []);
    chart.timeScale().applyOptions({ timeVisible: tf === "1h" });
    candles.setMarkers(showTrades ? buildMarkers(tf) : []);
    chart.timeScale().fitContent();
    const last = d.c[d.c.length - 1], lb = d.b[d.b.length - 1];
    showRow(last, lb && lb.value);
    showTradesFor(null);
  }
  chart.subscribeCrosshairMove((p) => {
    const d = sets[tf];
    if (!p.time) { const last = d.c[d.c.length - 1], lb = d.b[d.b.length - 1]; showRow(last, lb && lb.value); showTradesFor(null); return; }
    showTradesFor(p.time);
    const c = p.seriesData.get(candles), bv = p.seriesData.get(bench);
    showRow(c, bv && bv.value);
  });
  document.querySelectorAll("[data-tf]").forEach((btn) => btn.addEventListener("click", () => {
    tf = btn.dataset.tf;
    document.querySelectorAll("[data-tf]").forEach((x) => x.setAttribute("aria-pressed", x === btn));
    load();
  }));
  document.querySelectorAll("[data-style]").forEach((btn) => btn.addEventListener("click", () => {
    document.querySelectorAll("[data-style]").forEach((x) => x.setAttribute("aria-pressed", x === btn));
    candles.applyOptions(styles[btn.dataset.style]);
  }));
  const toggle = document.getElementById("bench-toggle");
  if (!sets["1h"].b.length) { toggle.checked = false; toggle.disabled = true; showBench = false; }
  toggle.addEventListener("change", () => { showBench = toggle.checked; load(); });
  const tt = document.getElementById("trades-toggle");
  if (!txs.length) { tt.checked = false; tt.disabled = true; showTrades = false; }
  tt.addEventListener("change", () => { showTrades = tt.checked; load(); });
  load();
})();
