/* Risk page */
(async () => {
  await App.init("risk.html");
  App.chartDefaults();
  const { usd, pct, esc, num } = App, C = App.COLORS;
  const [s, risk, models, ind, notes, rules, pos, c1d, proj] = await Promise.all([
    App.data("summary.json"), App.data("risk.json"), App.data("models.json", { models: [] }),
    App.getJSON("content/risk/indicators.json", { indicators: [] }), App.getText("content/risk/notes.md"),
    App.getJSON("config/rules.json", { limits: {} }),
    App.data("positions.json", { positions: [] }), App.data("candles_1d.json", { candles: [], benchmark: [] }),
    App.data("projection.json", { available: false }),
  ]);
  if (!s || !risk) return;
  App.statusLine(document.getElementById("updated"), s);
  const ex = risk.ex_ante || {}, re = risk.realised || {}, nav = risk.nav, lim = rules.limits || {};
  const stat = (label, value, sub = "") => `<div class="stat"><dt>${label}</dt><dd>${value}${sub ? `<small>${sub}</small>` : ""}</dd></div>`;
  const loss = (v) => (v == null ? "–" : pct(v, 2));
  const inUsd = (v) => (v == null ? "" : `${usd(v * nav)} on today's fund value`);
  const need = `shown after ${re.min_days} trading days`;
  document.getElementById("risk-stats").innerHTML = [
    stat("Volatility since inception", re.vol == null ? "–" : pct(re.vol, 1), re.vol == null ? need : `annualised, ${re.n_days} trading days`),
    stat("Volatility, last 20 days", re.vol_20d == null ? "–" : pct(re.vol_20d, 1), re.vol_20d == null ? "shown after 20 trading days" : "annualised"),
    stat("Volatility at current weights", ex.available ? pct(ex.vol, 1) : "–", ex.available ? `one year of history, ${ex.lookback_days} days` : "needs price history"),
    stat("Beta to benchmark", ex.beta == null ? "–" : num(ex.beta, 2), re.beta == null ? "at current weights" : `at current weights; realised ${num(re.beta, 2)}`),
    stat("One-day VaR 95%, historical", loss(ex.var_95_hist), ex.available ? inUsd(ex.var_95_hist) + (lim.max_var_95_1d ? `; limit ${pct(lim.max_var_95_1d, 1)}` : "") : ""),
    stat("One-day VaR 95%, parametric", loss(ex.var_95_param), ex.available ? inUsd(ex.var_95_param) : ""),
    stat("Expected shortfall 95%", loss(ex.es_95_hist), ex.available ? `historical; parametric ${pct(ex.es_95_param, 2)}` : ""),
    stat("Maximum drawdown", pct(re.max_drawdown, 2), "worst fall from a peak since inception"),
  ].join("");
  document.getElementById("risk-basis").textContent = ex.available
    ? "VaR, expected shortfall, beta and the charts below \"at current weights\" apply today's portfolio to the past year of daily returns."
    : "Risk at current weights appears once the fund holds positions and prices have been downloaded.";

  /* where we could finish: history plus a fan of simulated outcomes */
  if (!proj.available) document.getElementById("proj-block").hidden = true;
  else {
    const usdM = (v) => "$" + (v / 1e6).toFixed(2) + "M";
    document.getElementById("proj-intro").textContent = `${App.num(proj.paths)} simulated paths from today's value to ${App.date(s.end_date)}, ${proj.dates.length} trading days away.`;
    document.getElementById("proj-stats").innerHTML = [
      stat("Chance of beating the benchmark", proj.prob_above_benchmark == null ? "–" : pct(proj.prob_above_benchmark, 0), "at the end of the game"),
      stat(`Chance of finishing above ${usdM(s.initial_capital)}`, pct(proj.prob_above_capital, 0), "the starting capital"),
      stat("Median finish", usd(proj.median_end), "half of the paths end above this"),
      stat("Likely range", `${usdM(proj.p5_end)} to ${usdM(proj.p95_end)}`, "9 paths in 10 end inside it"),
    ].join("");
    const hist = c1d.candles.slice(-20), hb = c1d.benchmark.slice(-20);
    const labels = [...hist.map((c) => c.time), ...proj.dates], n0 = hist.length, pad = Array(n0 - 1).fill(null);
    const fan = (arr, start) => [...pad, start, ...arr];
    const band = (label, data, fill, bg) => ({ label, data, borderWidth: 0, pointRadius: 0, pointHoverRadius: 0, fill, backgroundColor: bg, band: true });
    const ds = [
      { label: "Fund value", data: [...hist.map((c) => c.close), ...proj.dates.map(() => null)], borderColor: C.fund, backgroundColor: C.fund },
      { label: "Median path", data: fan(proj.fund.p50, proj.start_value), borderColor: C.fund, backgroundColor: C.fund, borderDash: [5, 4] },
      band("95th percentile", fan(proj.fund.p95, proj.start_value), "+1", "rgba(31,95,184,0.10)"), band("5th percentile", fan(proj.fund.p5, proj.start_value), false),
      band("75th percentile", fan(proj.fund.p75, proj.start_value), "+1", "rgba(31,95,184,0.16)"), band("25th percentile", fan(proj.fund.p25, proj.start_value), false),
    ];
    if (proj.benchmark && hb.length) {
      ds.push({ label: "Benchmark", data: [...hb.map((c) => c.value), ...proj.dates.map(() => null)].slice(-labels.length), borderColor: C.bench, backgroundColor: C.bench });
      ds.push({ label: "Benchmark median path", data: fan(proj.benchmark.p50, proj.benchmark_start_value), borderColor: C.bench, backgroundColor: C.bench, borderDash: [5, 4] });
    }
    new Chart(document.getElementById("proj-chart"), {
      type: "line", data: { labels, datasets: ds },
      options: {
        plugins: {
          legend: { position: "top", align: "start", labels: { filter: (i, d) => !d.datasets[i.datasetIndex].band } },
          tooltip: { filter: (i) => i.parsed.y != null, callbacks: { title: (i) => App.date(i[0].label), label: (i) => ` ${i.dataset.label}: ${usd(i.parsed.y)}` } },
        },
        scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8, maxRotation: 0, callback(v) { return App.date(this.getLabelForValue(v)).replace(/ \d{4}$/, ""); } } },
                  y: { ticks: { callback: (v) => usdM(v) } } },
      },
    });
  }

  /* stress test: slider on the market move, then past episodes */
  const sp = (risk.positions || []).map((p) => ({ ...p, beta: p.beta == null ? 1 : p.beta }));
  if (!sp.length) document.getElementById("stress-block").hidden = true;
  else {
    const range = document.getElementById("stress-range");
    const draw = () => {
      const m = +range.value / 100, rows = sp.map((p) => ({ name: p.ticker, impact: p.weight * p.beta * m })), tot = rows.reduce((a, r) => a + r.impact, 0);
      document.getElementById("stress-move").textContent = App.pctSigned(m, 0);
      const el = document.getElementById("stress-result");
      el.className = "stress-result " + App.sign(tot);
      el.textContent = `${App.usdSigned(tot * nav)} (${App.pctSigned(tot)})`;
      document.getElementById("stress-sub").textContent = `Estimated change in the fund value. Cash, ${pct(1 - sp.reduce((a, p) => a + p.weight, 0), 1)} of the fund, does not move.`;
      rows.sort((a, b) => Math.abs(b.impact) - Math.abs(a.impact));
      const max = Math.max(...rows.map((r) => Math.abs(r.impact)), 1e-9);
      document.getElementById("stress-bars").innerHTML = rows.slice(0, 8).map((r) => `<li class="bar-row" style="grid-template-columns:4em minmax(40px,1fr) 7em"><span class="bar-name">${esc(r.name)}</span>
        <span class="bar-track" aria-hidden="true"><span class="bar-fill" style="width:${Math.abs(r.impact) / max * 100}%;background:${r.impact < 0 ? C.down : C.up}"></span></span>
        <span class="bar-value">${App.usdSigned(r.impact * nav)}</span></li>`).join("");
    };
    range.addEventListener("input", draw); draw();
    const sc = risk.scenarios || [];
    document.querySelector("#scenarios tbody").innerHTML = sc.map((x) => `<tr><td class="l"><b style="font-weight:500">${esc(x.name)}</b></td>
      <td class="l">${App.date(x.start)} to ${App.date(x.end)}</td><td class="${App.sign(x.benchmark_return)}">${App.pctSigned(x.benchmark_return, 1)}</td>
      <td class="${App.sign(x.fund_return)}">${App.pctSigned(x.fund_return, 1)}</td><td class="${App.sign(x.fund_usd)}">${App.usdSigned(x.fund_usd)}</td>
      <td class="l">${x.positions.slice(0, 3).map((p) => `${esc(p.ticker)} ${App.pctSigned(p.return, 0)}`).join(", ")}</td></tr>`).join("");
    const est = sc.some((x) => x.estimated_positions);
    document.getElementById("scenario-note").textContent = est
      ? "Where a holding has no price history for an episode, its move is estimated as its beta times the market move."
      : "Each holding's actual price move over the episode, applied to today's weights.";
  }

  /* drawdown */
  const dd = re.drawdown || [];
  const tfmt = new Intl.DateTimeFormat("en-GB", { timeZone: App.cfg.display_timezone, day: "numeric", month: "short" });
  const tfull = new Intl.DateTimeFormat("en-GB", { timeZone: App.cfg.display_timezone, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  new Chart(document.getElementById("dd-chart"), {
    type: "line",
    data: { labels: dd.map((d) => d[0] * 1000), datasets: [{ label: "Drawdown", data: dd.map((d) => d[1] * 100), borderColor: C.fund, backgroundColor: "rgba(31,95,184,0.10)", fill: "origin", tension: 0 }] },
    options: {
      plugins: { legend: { display: false }, tooltip: { callbacks: { title: (i) => tfull.format(new Date(+i[0].label)), label: (i) => ` ${i.parsed.y.toFixed(2)}% below the peak` } } },
      scales: {
        x: { grid: { display: false }, ticks: { maxTicksLimit: 6, maxRotation: 0, callback(v) { return tfmt.format(new Date(+this.getLabelForValue(v))); } } },
        y: { max: 0, ticks: { callback: (v) => v + "%" } },
      },
    },
  });

  /* rolling volatility */
  const rv = re.rolling_vol_20d || [];
  if (rv.length < 2) {
    document.getElementById("vol-wrap").innerHTML = '<p class="chart-empty">The line starts once the fund has 21 trading days of history.</p>';
  } else {
    new Chart(document.getElementById("vol-chart"), {
      type: "line",
      data: { labels: rv.map((d) => App.date(d[0]).replace(/ \d{4}$/, "")), datasets: [{ label: "20-day volatility", data: rv.map((d) => d[1] * 100), borderColor: C.fund, pointRadius: 3, pointBackgroundColor: C.fund, tension: 0 }] },
      options: {
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (i) => ` ${i.parsed.y.toFixed(1)}% annualised` } } },
        scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 6, maxRotation: 0 } }, y: { ticks: { callback: (v) => v + "%" } } },
      },
    });
  }

  /* calendar of daily returns and risk/return bubbles */
  if (window.echarts) {
    const days = c1d.candles.map((c, i) => [c.time, c.close / (i ? c1d.candles[i - 1].close : s.initial_capital) - 1]);
    if (days.length) Viz.calendar(document.getElementById("calendar"), days, s.start_date, s.end_date);
    const byT = Object.fromEntries(pos.positions.map((p) => [p.ticker, p]));
    const rows = (risk.positions || []).filter((r) => byT[r.ticker]).map((r) => ({ ticker: r.ticker, name: byT[r.ticker].name, vol: r.vol, ret: byT[r.ticker].unrealized_pct, weight: Math.abs(r.weight) }));
    if (rows.length) Viz.bubbles(document.getElementById("bubbles"), rows);
    else document.getElementById("rr-block").hidden = true;
  }

  /* weight vs share of risk */
  const pr = [...(risk.positions || [])].sort((a, b) => b.risk_contribution - a.risk_contribution);
  if (!pr.length) {
    document.getElementById("rc-wrap").innerHTML = '<p class="chart-empty">Nothing to show while the fund is fully in cash.</p>';
    document.getElementById("rc-wrap").style.height = "auto";
    document.getElementById("rc-table").closest(".table-scroll").hidden = true;
  } else {
    document.getElementById("rc-wrap").style.height = Math.max(260, pr.length * 34 + 70) + "px";
    new Chart(document.getElementById("rc-chart"), {
      type: "bar",
      data: {
        labels: pr.map((p) => p.ticker),
        datasets: [
          { label: "Share of weight", data: pr.map((p) => p.weight * 100), backgroundColor: C.fund, borderRadius: { topRight: 4, bottomRight: 4 }, borderSkipped: "start", barPercentage: 0.82, categoryPercentage: 0.72, borderColor: "#fff", borderWidth: { top: 1, bottom: 1 } },
          { label: "Share of risk", data: pr.map((p) => p.risk_contribution * 100), backgroundColor: C.bench, borderRadius: { topRight: 4, bottomRight: 4 }, borderSkipped: "start", barPercentage: 0.82, categoryPercentage: 0.72, borderColor: "#fff", borderWidth: { top: 1, bottom: 1 } },
        ],
      },
      options: {
        indexAxis: "y",
        plugins: { legend: { position: "top", align: "start" }, tooltip: { callbacks: { label: (i) => ` ${i.dataset.label}: ${i.parsed.x.toFixed(1)}%` } } },
        scales: { x: { ticks: { callback: (v) => v + "%" } }, y: { grid: { display: false }, ticks: { color: C.ink, font: { weight: 600 } } } },
      },
    });
    document.querySelector("#rc-table tbody").innerHTML = pr.map((p) => `<tr>
      <td class="l ticker" data-v="${esc(p.ticker)}">${esc(p.ticker)}</td><td data-v="${p.weight}">${pct(p.weight, 1)}</td>
      <td data-v="${p.risk_contribution}">${pct(p.risk_contribution, 1)}</td><td data-v="${p.vol}">${pct(p.vol, 1)}</td>
      <td data-v="${p.beta ?? ""}">${p.beta == null ? "–" : num(p.beta, 2)}</td></tr>`).join("");
    App.sortable(document.getElementById("rc-table"));
  }

  /* correlation heat map: blue (negative) - grey (zero) - red (positive) */
  const corr = risk.correlation;
  const mix = (a, b, t) => a.map((x, i) => Math.round(x + (b[i] - x) * t));
  const colour = (v) => { const mid = [240, 239, 236], pos = [181, 52, 42], neg = [36, 89, 168]; return `rgb(${mix(mid, v >= 0 ? pos : neg, Math.min(1, Math.abs(v))).join(",")})`; };
  document.getElementById("corr").innerHTML = corr ? `<table class="heat"><thead><tr><th></th>${corr.tickers.map((t) => `<th scope="col">${esc(t)}</th>`).join("")}</tr></thead><tbody>${
    corr.matrix.map((row, i) => `<tr><th scope="row">${esc(corr.tickers[i])}</th>${row.map((v, j) =>
      `<td style="background:${i === j ? "#E3E7EC" : colour(v)}" class="${i !== j && Math.abs(v) > 0.55 ? "strong" : ""}" title="${esc(corr.tickers[i])} and ${esc(corr.tickers[j])}: ${v.toFixed(2)}">${i === j ? "" : v.toFixed(2)}</td>`).join("")}</tr>`).join("")
  }</tbody></table>` : '<p class="chart-empty">Nothing to show while the fund is fully in cash.</p>';

  /* team models */
  const sigLabel = { normal: "Normal", caution: "Caution", alert: "Alert" };
  const cell = (c) => (c && typeof c === "object") ? `<td class="${c.signal && c.signal !== "normal" ? "cell-" + c.signal : ""}">${esc(c.v)}</td>` : `<td>${esc(c)}</td>`;
  const modelTable = (t) => `<div class="table-scroll"><table class="data"><thead><tr>${t.columns.map((c, i) => `<th class="${i ? "" : "l"}">${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${t.rows.map((r) => `<tr>${r.map((c, i) => i ? cell(c) : `<td class="l ticker">${esc(c && typeof c === "object" ? c.v : c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  document.getElementById("models").innerHTML = models.models.length ? models.models.map((m) => `
    <article class="model">
      <h3>${esc(m.title)}</h3>
      ${m.author ? `<p class="note-meta">${esc(m.author)}</p>` : ""}
      ${m.description ? `<p class="muted" style="max-width:70ch">${esc(m.description)}</p>` : ""}
      ${m.error ? `<p class="error-box">This model failed on the last run: ${esc(m.error)}</p>` : ""}
      ${(m.metrics || []).length ? `<div class="model-metrics">${m.metrics.map((x) => `<div class="model-metric"><div class="n">${esc(x.name)}</div>
        <div class="v">${esc(x.value)} ${x.signal ? `<span class="tag tag-${esc(x.signal)}">${sigLabel[x.signal] || esc(x.signal)}</span>` : ""}</div>${x.comment ? `<p>${esc(x.comment)}</p>` : ""}</div>`).join("")}</div>` : ""}
      ${m.table ? modelTable(m.table) : ""}
      ${(m.tables || []).map((x) => `<details class="model-more"><summary>${esc(x.title)}</summary>
        ${x.note ? `<p class="muted">${esc(x.note)}</p>` : ""}${modelTable(x.table)}</details>`).join("")}
      ${(m.links || []).map((x) => `<p class="model-link"><a href="${esc(x.href)}">${esc(x.label)}</a></p>`).join("")}
    </article>`).join("") : '<p class="chart-empty">No model has been added yet. Put a Python file in the models folder and it will run with every update.</p>';

  /* analyst's indicators and note */
  document.querySelector("#indicators tbody").innerHTML = (ind.indicators || []).map((x) => `<tr>
    <td class="l">${esc(x.name)}</td><td class="l"><b style="font-weight:500">${esc(x.value)}</b></td>
    <td class="l"><span class="tag tag-${esc(x.signal || "normal")}">${sigLabel[x.signal] || "Normal"}</span></td>
    <td class="l wrap-cell">${esc(x.comment || "")}</td></tr>`).join("");
  document.getElementById("indicators-meta").textContent = ind.updated ? `Updated ${App.date(ind.updated)}${ind.author ? " by " + ind.author : ""}` : "";
  document.getElementById("risk-notes").innerHTML = App.md(notes);
})();
