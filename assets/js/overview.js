/* Overview page */
(async () => {
  const cfg = await App.init("index.html");
  const { usd, usdSigned, pct, pctSigned, sign, esc, num } = App;
  const [s, alerts, pos, exp, c1h, c1d, note, rules] = await Promise.all([
    App.data("summary.json"), App.data("alerts.json", { alerts: [], rules: [] }), App.data("positions.json", { positions: [] }),
    App.data("exposures.json", { sector: [] }), App.data("candles_1h.json", { candles: [], benchmark: [] }),
    App.data("candles_1d.json", { candles: [], benchmark: [] }), App.getText("content/pm_note.md"),
    App.getJSON("config/rules.json", { limits: {} }),
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
    kpi("Return since inception", pctSigned(s.total_return), `${num(s.trading_days)} trading days, ${num(s.days_left)} days to go`, sign(s.total_return)),
    kpi(`Against ${esc(b.name || "benchmark")}`, s.excess_return == null ? "–" : pctSigned(s.excess_return), b.return == null ? "benchmark not loaded yet" : `benchmark ${pctSigned(b.return)}`, sign(s.excess_return)),
    kpi("Volatility, annualised", pct(s.volatility, 1), s.volatility_basis || "needs price history"),
    kpi("Sharpe ratio", s.sharpe == null ? "–" : num(s.sharpe, 2), s.sharpe == null ? "shown after 10 trading days" : "annualised, since inception"),
    kpi("Maximum drawdown", pct(s.max_drawdown, 2), "worst fall from a peak"),
    kpi("Cash", pct(s.cash_weight, 1), usd(s.cash)),
    kpi("Positions", num(s.n_positions), `${usd(s.invested)} invested`),
    kpi("Rules respected", `${s.rules_ok} of ${s.rules_total}`, s.rules_ok === s.rules_total ? "all limits respected" : "see alerts below"),
  ].join("");

  /* ---- PM note, alerts ---- */
  document.getElementById("pm-note").innerHTML = App.md(note) || '<p class="muted">No note yet.</p>';
  const breaches = alerts.alerts.filter((a) => a.severity === "breach").length;
  const warns = alerts.alerts.filter((a) => a.severity === "warning").length;
  document.getElementById("rules-score").innerHTML = alerts.alerts.length
    ? `${breaches} ${breaches === 1 ? "breach" : "breaches"}, ${warns} ${warns === 1 ? "warning" : "warnings"}<small>${alerts.rules_ok} of ${alerts.rules_total} rules respected${alerts.rules_are_placeholder ? " (placeholder limits)" : ""}</small>`
    : `All clear<small>${alerts.rules_ok} of ${alerts.rules_total} rules respected${alerts.rules_are_placeholder ? " (placeholder limits)" : ""}</small>`;
  const label = { breach: "Breach", warning: "Warning", info: "Note" };
  document.getElementById("alerts").innerHTML = alerts.alerts.length
    ? alerts.alerts.map((a) => `<li class="alert"><span class="tag tag-${a.severity}">${label[a.severity]}</span><strong>${esc(a.title)}</strong><p>${esc(a.message)}</p></li>`).join("")
    : `<li class="alert"><span class="tag tag-ok">OK</span><strong>No rule is breached</strong><p>Every limit on the Philosophy page is respected and no position has drifted beyond its threshold.</p></li>`;

  /* ---- holdings and sectors ---- */
  const top = pos.positions.slice(0, 10).map((p) => ({ name: p.name, sub: p.ticker, weight: p.weight }));
  const topEl = document.getElementById("top-holdings");
  if (top.length) App.bars(topEl, top, { ranked: true });
  else topEl.outerHTML = '<p class="chart-empty">The fund is fully in cash. Holdings appear here after the first trade.</p>';
  const lim = rules.limits.max_sector_weight;
  const secMax = Math.max(lim || 0, ...exp.sector.map((x) => x.weight));
  App.bars(document.getElementById("sectors"), exp.sector, { max: secMax, limit: lim });
  if (lim) document.getElementById("sector-limit-note").innerHTML = `<i aria-hidden="true"></i> Sector limit of ${pct(lim, 0)}`;

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
  let tf = "1h", showBench = true;
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
    chart.timeScale().fitContent();
    const last = d.c[d.c.length - 1], lb = d.b[d.b.length - 1];
    showRow(last, lb && lb.value);
  }
  chart.subscribeCrosshairMove((p) => {
    const d = sets[tf];
    if (!p.time) { const last = d.c[d.c.length - 1], lb = d.b[d.b.length - 1]; showRow(last, lb && lb.value); return; }
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
  load();
})();
