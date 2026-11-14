/* Research page: company theses and macro notes written by the team in content/ */
(async () => {
  await App.init("research.html");
  const { usd, pctSigned, sign, esc } = App;
  const [idx, pos, cal, reb] = await Promise.all([
    App.getJSON("data/content_index.json", { fundamental: [], macro: [] }), App.data("positions.json", { positions: [] }),
    App.getJSON("content/macro/calendar.json", { events: [] }), App.data("rebalance_suggestions.json", { table: [] }),
  ]);
  const price = {};
  (reb.table || []).forEach((r) => { if (r.price) price[r.ticker] = r.price; });
  pos.positions.forEach((p) => { price[p.ticker] = p.price; });
  const held = new Set(pos.positions.map((p) => p.ticker));

  /* company research */
  const files = await Promise.all((idx.fundamental || []).map((f) => App.getText("content/fundamental/" + f)));
  const notes = files.map(App.frontMatter).filter((n) => n.meta.ticker)
    .sort((a, b) => String(b.meta.updated || "").localeCompare(String(a.meta.updated || "")));
  document.getElementById("fundamental").innerHTML = notes.length ? notes.map(({ meta, body }) => {
    const t = meta.ticker.toUpperCase(), px = price[t], tp = parseFloat(meta.target_price);
    const up = px && tp ? tp / px - 1 : null;
    return `<article class="entry">
      <div class="entry-side">
        <h3>${esc(meta.title || t)}</h3>
        <p class="ticker-line">${esc(t)}${held.has(t) ? ", in the portfolio" : ", not held"}</p>
        <dl class="facts">
          <dt>Rating</dt><dd>${esc(meta.rating || "–")}</dd>
          <dt>Target price</dt><dd>${tp ? usd(tp, 2) : "–"}</dd>
          <dt>Latest price</dt><dd>${px ? usd(px, 2) : "–"}</dd>
          <dt>Upside to target</dt><dd class="${sign(up)}">${up == null ? "–" : pctSigned(up, 1)}</dd>
          <dt>Horizon</dt><dd class="plain">${esc(meta.horizon || "–")}</dd>
          <dt>Catalysts</dt><dd class="plain">${esc(meta.catalysts || "–")}</dd>
          <dt>Updated</dt><dd class="plain">${meta.updated ? App.date(meta.updated) : "–"}${meta.author ? " by " + esc(meta.author) : ""}</dd>
        </dl>
      </div>
      <div class="prose">${App.md(body)}</div>
    </article>`;
  }).join("") : '<p class="chart-empty">No company research yet. Add a file to content/fundamental.</p>';

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
  document.querySelector("#calendar tbody").innerHTML = (cal.events || []).sort((a, b) => a.date.localeCompare(b.date)).map((e) => `
    <tr class="${e.date < today ? "muted" : ""}"><td class="l">${App.date(e.date)}</td><td class="l wrap-cell" style="min-width:14ch"><b style="font-weight:500">${esc(e.event)}</b></td>
    <td class="l wrap-cell">${esc(e.relevance || "")}</td></tr>`).join("");
})();
