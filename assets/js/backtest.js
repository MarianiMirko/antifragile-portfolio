/* Backtest page: one entry per markdown file in content/backtest */
(async () => {
  await App.init("backtest.html");
  App.chartDefaults();
  const { esc } = App, C = App.COLORS;
  const RESERVED = new Set(["title", "author", "updated", "period", "equity_csv"]);
  const idx = await App.getJSON("data/content_index.json", { backtest: [] });
  const files = await Promise.all((idx.backtest || []).map((f) => App.getText("content/backtest/" + f)));
  const items = files.map(App.frontMatter);
  const root = document.getElementById("backtests");
  if (!items.length) { root.innerHTML = '<p class="chart-empty">No backtests yet. Add a file to content/backtest.</p>'; return; }
  root.innerHTML = items.map(({ meta, body }, i) => {
    const metrics = Object.entries(meta).filter(([k]) => !RESERVED.has(k));
    return `<article class="note" style="padding-bottom:48px">
      <h2>${esc(meta.title || "Backtest")}</h2>
      <p class="note-meta">${[meta.period, meta.author && "by " + meta.author, meta.updated && "updated " + App.date(meta.updated)].filter(Boolean).map(esc).join(", ")}</p>
      <dl class="stats auto" style="margin-bottom:28px;--n:${Math.min(5, Math.max(2, metrics.length))}">${metrics.map(([k, v]) => `<div class="stat"><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl>
      <div class="cols-2"><div class="prose">${App.md(body)}</div>
      <div>${meta.equity_csv ? `<div class="chart-box" style="height:340px"><canvas id="bt-${i}" role="img" aria-label="Equity curve of the strategy and its benchmark"></canvas></div>` : ""}</div></div>
    </article>`;
  }).join("");
  items.forEach(async ({ meta }, i) => {
    if (!meta.equity_csv) return;
    const csv = await App.getText("content/backtest/" + meta.equity_csv);
    const lines = csv.trim().split(/\r?\n/).map((l) => l.split(","));
    const head = lines.shift().map((h) => h.trim());
    const colours = [C.fund, C.bench];
    new Chart(document.getElementById("bt-" + i), {
      type: "line",
      data: {
        labels: lines.map((l) => l[0]),
        datasets: head.slice(1, 3).map((h, j) => ({ label: h.charAt(0).toUpperCase() + h.slice(1), data: lines.map((l) => +l[j + 1]), borderColor: colours[j], backgroundColor: colours[j], tension: 0, borderDash: j ? [5, 4] : [] })),
      },
      options: {
        plugins: { legend: { position: "top", align: "start" }, tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${c.parsed.y.toFixed(1)}` } } },
        scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 7, maxRotation: 0, callback(v) { return String(this.getLabelForValue(v)).slice(0, 4); } } }, y: { title: { display: true, text: "Growth of 100" } } },
      },
    });
  });
})();
