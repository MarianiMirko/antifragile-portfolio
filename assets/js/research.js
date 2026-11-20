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
    html += `<div class="briefs">${withMetrics.filter((n) => !n.meta.benchmark).map(({ meta, body }) => {
      const t = String(meta.ticker).toUpperCase(), px = price[t];
      return `<div class="brief"><h4>${esc(meta.title || t)} <span class="muted">${esc(t)}</span></h4>
        <p class="brief-meta">${esc(meta.role || "")}${px ? " · " + usd(px, 2) : ""}</p>
        <table class="mini"><thead><tr><th class="l"></th><th>${esc(t)}</th>${bm ? `<th>${esc(bm.name)}</th>` : ""}</tr></thead>
          <tbody>${METRICS.map(([k, l]) => `<tr><td class="l">${l}</td><td>${esc(meta[k] || "–")}</td>${bm ? `<td class="muted">${esc(bm[k] || "–")}</td>` : ""}</tr>`).join("")}</tbody></table>
        <div class="prose">${App.md(body)}</div></div>`;
    }).join("")}</div>`;
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
  document.getElementById("macro").innerHTML = mnotes.length ? mnotes.map(({ meta, body }) => `
    <article class="note"><h3>${esc(meta.title || "Note")}</h3>
      <p class="note-meta">${meta.date ? App.date(meta.date) : ""}${meta.author ? " by " + esc(meta.author) : ""}</p>
      <div class="prose">${App.md(body)}</div></article>`).join("") : '<p class="chart-empty">No macro notes yet. Add a file to content/macro.</p>';

  /* calendar: upcoming only, one row per day; earnings of held stocks inside the game added automatically */
  const today = new Date().toISOString().slice(0, 10), end = App.cfg.end_date || "9999-12-31";
  const byDay = {};
  const add = (date, text, why) => { (byDay[date] = byDay[date] || { items: [], earnings: [] }).items.push({ text, why }); };
  (cal.events || []).forEach((e) => add(e.date, e.event, e.relevance));
  (auto.events || []).filter((e) => /earnings/i.test(e.event) && held.has(e.ticker) && e.date <= end)
    .forEach((e) => { const d = (byDay[e.date] = byDay[e.date] || { items: [], earnings: [] });
      if (!d.items.some((i) => i.text.toUpperCase().includes(e.ticker))) d.earnings.push(e.ticker); });
  const days = Object.keys(byDay).filter((d) => d >= today).sort();
  const short = (d) => new Date(d + "T12:00:00Z").toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
  document.querySelector("#calendar tbody").innerHTML = days.map((d) => {
    const { items, earnings } = byDay[d];
    const lines = items.map((i) => `<div><b style="font-weight:500">${esc(i.text)}</b>${i.why ? `<span class="cal-why">${esc(i.why)}</span>` : ""}</div>`);
    if (earnings.length) lines.push(`<div><b style="font-weight:500">Earnings: ${earnings.map(esc).join(", ")}</b></div>`);
    return `<tr><td class="l cal-date">${short(d)}</td><td class="l wrap-cell">${lines.join("")}</td></tr>`;
  }).join("") || '<tr><td class="l muted" colspan="2">No upcoming events.</td></tr>';
})();
