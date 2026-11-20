/* Research page: company theses and macro notes written by the team in content/ */
(async () => {
  await App.init("research.html");
  const { usd, pctSigned, sign, esc } = App;
  const [idx, pos, cal, reb, auto] = await Promise.all([
    App.getJSON("data/content_index.json", { fundamental: [], macro: [] }), App.data("positions.json", { positions: [] }),
    App.getJSON("content/macro/calendar.json", { events: [] }), App.data("rebalance_suggestions.json", { table: [] }),
    App.data("events.json", { events: [] }),
  ]);
  await App.libs;
  const price = {};
  (reb.table || []).forEach((r) => { if (r.price) price[r.ticker] = r.price; });
  pos.positions.forEach((p) => { price[p.ticker] = p.price; });
  const held = new Set(pos.positions.map((p) => p.ticker));

  /* company research */
  const files = await Promise.all((idx.fundamental || []).map((f) => App.getText("content/fundamental/" + f)));
  const notes = files.map(App.frontMatter).filter((n) => n.meta.ticker)
    .sort((a, b) => String(b.meta.updated || "").localeCompare(String(a.meta.updated || "")) || (parseFloat(a.meta.order) || 99) - (parseFloat(b.meta.order) || 99));
  const METRICS = [["pe", "Fwd P/E"], ["ev_ebitda", "EV/EBITDA"], ["peg", "PEG"], ["fcf_yield", "FCF yield"],
    ["ev_sales", "EV/Sales"], ["op_margin", "Op. margin"], ["roic", "ROIC"], ["debt_ebitda", "Debt/EBITDA"]];
  const withMetrics = notes.filter((n) => n.meta.pe);
  const classic = notes.filter((n) => !n.meta.pe);
  const box = document.getElementById("fundamental");
  let html = "";
  if (withMetrics.length) {
    const bm = await App.getJSON("content/fundamental/benchmark.json", null);
    const rows = withMetrics.filter((n) => !n.meta.benchmark);
    if (bm) rows.push({ meta: { ...bm, ticker: bm.name, benchmark: true } });
    const by = withMetrics.find((n) => !n.meta.benchmark)?.meta || {};
    html += `<div class="table-scroll"><table class="data fund-table">
      <thead><tr><th class="l">Company</th><th class="l">Role</th><th>Price</th>${METRICS.map(([, l]) => `<th>${l}</th>`).join("")}</tr></thead>
      <tbody>${rows.map(({ meta }) => {
        const t = String(meta.ticker).toUpperCase(), px = price[t];
        return `<tr${meta.benchmark ? ' class="bench-row"' : ""}><td class="l"><b style="font-weight:500">${esc(meta.benchmark ? meta.ticker : t)}</b>${meta.benchmark ? "" : ` <span class="muted">${esc(meta.title || "")}</span>`}</td>
          <td class="l muted">${esc(meta.role || "")}</td><td>${px && !meta.benchmark ? usd(px, 2) : ""}</td>
          ${METRICS.map(([k]) => `<td>${esc(meta[k] || "–")}</td>`).join("")}</tr>`;
      }).join("")}</tbody></table></div>
      <p class="note-meta" style="margin-top:8px">${by.updated ? "Updated " + App.date(by.updated) : ""}${by.author ? " by " + esc(by.author) : ""}. Price: latest close.</p>
      <div class="briefs">${withMetrics.filter((n) => !n.meta.benchmark && n.body.trim()).map(({ meta, body }) => `
        <div class="brief"><h4>${esc(meta.title || meta.ticker)} <span class="muted">${esc(String(meta.ticker).toUpperCase())}</span></h4>
          <div class="prose">${App.md(body)}</div></div>`).join("")}</div>`;
  }
  html += classic.map(({ meta, body }) => {
    const t = meta.ticker.toUpperCase(), px = price[t], tp = parseFloat(meta.target_price);
    const up = px && tp ? tp / px - 1 : null;
    return `<article class="entry">
      <div class="entry-side">
        <h3>${esc(meta.title || t)}</h3>
        <p class="ticker-line">${esc(t)}${held.has(t) ? ", in the portfolio" : ", not held"}</p>
        <dl class="facts">${[
          ["Rating", meta.rating && esc(meta.rating)],
          ["Target price", tp ? usd(tp, 2) : "", 1],
          ["Latest price", px ? usd(px, 2) : "–", 1],
          ["Upside to target", up == null ? "" : `<span class="${sign(up)}">${pctSigned(up, 1)}</span>`, 1],
          ["Horizon", meta.horizon && esc(meta.horizon)],
          ["Catalysts", meta.catalysts && esc(meta.catalysts)],
          ["Updated", meta.updated ? App.date(meta.updated) + (meta.author ? " by " + esc(meta.author) : "") : ""],
        ].filter(([, v]) => v).map(([k, v, num]) => `<dt>${k}</dt><dd${num ? "" : ' class="plain"'}>${v}</dd>`).join("")}
        </dl>
      </div>
      <div class="prose">${App.md(body)}</div>
    </article>`;
  }).join("");
  box.innerHTML = html || '<p class="chart-empty">No company research yet. Add a file to content/fundamental.</p>';

  /* macro notes */
  const mfiles = await Promise.all((idx.macro || []).map((f) => App.getText("content/macro/" + f)));
  const mnotes = mfiles.map(App.frontMatter).sort((a, b) => String(b.meta.date || "").localeCompare(String(a.meta.date || "")));
  if (mnotes.length && mnotes[0].meta.regime) {
    const r = document.getElementById("regime");
    r.hidden = false;
    r.innerHTML = `<span class="muted">Current regime</span><b>${esc(mnotes[0].meta.regime)}</b><span class="muted">as of ${App.date(mnotes[0].meta.date)}</span>`;
  }
  document.getElementById("macro").innerHTML = mnotes.length ? mnotes.map(({ meta, body }) => `
    <article class="note"><h3>${esc(meta.title || "Note")}</h3>
      <p class="note-meta">${meta.date ? App.date(meta.date) : ""}${meta.author ? " by " + esc(meta.author) : ""}</p>
      <div class="prose">${App.md(body)}</div></article>`).join("") : '<p class="chart-empty">No macro notes yet. Add a file to content/macro.</p>';

  const today = new Date().toISOString().slice(0, 10);
  const autoRows = (auto.events || []).map((e) => ({ date: e.date, event: `${e.ticker} ${e.event.toLowerCase()}`, relevance: "Added automatically for a company we hold or target" }));
  cal.events = [...(cal.events || []), ...autoRows.filter((a) => !(cal.events || []).some((m) => m.date === a.date && m.event.toUpperCase().includes(a.event.split(" ")[0])))];
  document.querySelector("#calendar tbody").innerHTML = (cal.events || []).sort((a, b) => a.date.localeCompare(b.date)).map((e) => `
    <tr class="${e.date < today ? "muted" : ""}"><td class="l">${App.date(e.date)}</td><td class="l wrap-cell" style="min-width:14ch"><b style="font-weight:500">${esc(e.event)}</b></td>
    <td class="l wrap-cell">${esc(e.relevance || "")}</td></tr>`).join("");
})();
