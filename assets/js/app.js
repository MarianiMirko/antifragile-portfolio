/* Shared code for every page: config, header/footer, data loading, formatting. */
const App = (() => {
  const PAGES = [
    ["index.html", "Overview"], ["portfolio.html", "Portfolio"], ["risk.html", "Risk"],
    ["research.html", "Research"], ["backtest.html", "Backtest"],
    ["philosophy.html", "Philosophy"], ["team.html", "Team"], ["private.html", "Private"],
  ];
  const COLORS = {
    ink: "#0B1524", navy: "#11264A", muted: "#5B6778", rule: "#D8DEE6", grid: "#EDF0F4",
    up: "#17794E", down: "#B5342A", fund: "#1F5FB8", bench: "#C4741A",
  };
  const state = { cfg: null, base: "data/" };

  async function getJSON(path, fallback = null) {
    try {
      const r = await fetch(path, { cache: "no-cache" });
      if (!r.ok) throw new Error(r.status);
      return await r.json();
    } catch (e) { return fallback; }
  }
  async function getText(path, fallback = "") {
    try {
      const r = await fetch(path, { cache: "no-cache" });
      if (!r.ok) throw new Error(r.status);
      return await r.text();
    } catch (e) { return fallback; }
  }
  const data = (name, fallback = null) => getJSON(state.base + name, fallback);

  /* ---------- formatting ---------- */
  const nf = (d) => new Intl.NumberFormat("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  const num = (v, d = 0) => (v == null || isNaN(v) ? "–" : nf(d).format(v));
  const usd = (v, d = 0) => (v == null || isNaN(v) ? "–" : (v < 0 ? "−$" : "$") + nf(d).format(Math.abs(v)));
  const usdSigned = (v, d = 0) => (v == null || isNaN(v) ? "–" : (v < 0 ? "−$" : "+$") + nf(d).format(Math.abs(v)));
  const pct = (v, d = 2) => (v == null || isNaN(v) ? "–" : (v < 0 ? "−" : "") + nf(d).format(Math.abs(v * 100)) + "%");
  const pctSigned = (v, d = 2) => (v == null || isNaN(v) ? "–" : (v < 0 ? "−" : "+") + nf(d).format(Math.abs(v * 100)) + "%");
  const sign = (v) => (v == null || isNaN(v) || Math.abs(v) < 1e-12 ? "flat" : v > 0 ? "up" : "down");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function tz() { return (state.cfg && state.cfg.display_timezone) || "Europe/Amsterdam"; }
  function dateTime(iso) {
    if (!iso) return "–";
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: tz(), day: "numeric", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit", hour12: false, timeZoneName: "short",
    }).formatToParts(new Date(iso));
    const g = (t) => (parts.find((p) => p.type === t) || {}).value;
    return `${g("day")} ${g("month")} ${g("year")}, ${g("hour")}:${g("minute")} ${g("timeZoneName")}`;
  }
  function date(iso) {
    if (!iso) return "–";
    const d = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(iso + "T12:00:00Z") : new Date(iso);
    return new Intl.DateTimeFormat("en-GB", { timeZone: tz(), day: "numeric", month: "short", year: "numeric" }).format(d);
  }
  /* seconds to add to a UTC timestamp so a chart that only knows UTC shows local (CET) clock time */
  function tzOffsetSec(tsSec) {
    const p = new Intl.DateTimeFormat("en-US", {
      timeZone: tz(), hourCycle: "h23", year: "numeric", month: "numeric", day: "numeric",
      hour: "numeric", minute: "numeric", second: "numeric",
    }).formatToParts(new Date(tsSec * 1000));
    const g = (t) => +p.find((x) => x.type === t).value;
    return Date.UTC(g("year"), g("month") - 1, g("day"), g("hour"), g("minute"), g("second")) / 1000 - tsSec;
  }

  /* ---------- markdown with a simple "key: value" header ---------- */
  function frontMatter(text) {
    const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/.exec(text.trim());
    if (!m) return { meta: {}, body: text };
    const meta = {};
    m[1].split(/\r?\n/).forEach((line) => {
      const i = line.indexOf(":");
      if (i > 0) meta[line.slice(0, i).trim()] = line.slice(i + 1).trim();
    });
    return { meta, body: m[2] };
  }
  const md = (text) => (window.marked ? marked.parse(text || "") : `<p>${esc(text)}</p>`);

  /* ---------- page chrome ---------- */
  function chrome(current) {
    const c = state.cfg;
    document.title = `${document.title} | ${c.fund_name}`;
    const links = PAGES.map(([href, label]) =>
      `<a href="${href}"${href === current ? ' aria-current="page"' : ""}>${label}</a>`).join("");
    const header = document.createElement("header");
    header.className = "site-header";
    header.innerHTML = `
      <div class="wrap header-inner">
        <a class="brand" href="index.html" aria-label="${esc(c.fund_name)}, home">
          <span class="brand-mark" aria-hidden="true">${esc(c.fund_initials || "")}</span>
          <span class="brand-name">${esc(c.fund_name)}</span>
        </a>
        <nav class="site-nav" aria-label="Main">${links}</nav>
      </div>`;
    document.body.prepend(header);
    if (c.demo_mode && current !== "private.html") {
      const b = document.createElement("div");
      b.className = "demo-banner";
      b.innerHTML = `<div class="wrap"><strong>Demo data.</strong> The portfolio, prices and notes shown here are invented to show how the site works. They are not the fund's real holdings.</div>`;
      header.after(b);
    }
    const footer = document.createElement("footer");
    footer.className = "site-footer";
    footer.innerHTML = `
      <div class="wrap footer-inner">
        <div>
          <div class="brand"><span class="brand-mark" aria-hidden="true">${esc(c.fund_initials || "")}</span>
          <span class="brand-name">${esc(c.fund_name)}</span></div>
          <p>${esc(c.tagline || "")}</p>
        </div>
        <p class="footer-note">A simulated portfolio run on the MarketWatch Virtual Stock Exchange for a university course.
        No real money is invested and nothing on this site is investment advice.</p>
      </div>`;
    document.body.append(footer);
  }

  async function init(current) {
    state.cfg = await getJSON("config/fund.json");
    if (!state.cfg) {
      document.body.innerHTML = '<p style="padding:2rem">Could not load config/fund.json. Open the site through a web server, not as a local file.</p>';
      throw new Error("no config");
    }
    state.base = state.cfg.demo_mode ? "data/demo/" : "data/";
    chrome(current);
    return state.cfg;
  }

  /* ---------- small building blocks ---------- */
  function bars(el, rows, opts = {}) {
    /* rows: [{name, weight, note?}] -> ranked horizontal bars */
    const max = opts.max || Math.max(...rows.map((r) => Math.abs(r.weight)), 0.0001);
    el.innerHTML = rows.map((r, i) => `
      <li class="bar-row${r.is_cash ? " is-cash" : ""}">
        ${opts.ranked ? `<span class="bar-rank">${i + 1}</span>` : ""}
        <span class="bar-name">${esc(r.name)}${r.sub ? `<small>${esc(r.sub)}</small>` : ""}</span>
        <span class="bar-track" aria-hidden="true"><span class="bar-fill" style="width:${Math.max(0.5, Math.abs(r.weight) / max * 100)}%"></span>
          ${opts.limit ? `<span class="bar-limit" style="left:${Math.min(100, opts.limit / max * 100)}%"></span>` : ""}</span>
        <span class="bar-value">${pct(r.weight, 1)}</span>
      </li>`).join("");
  }

  function sortable(table) {
    const ths = table.querySelectorAll("thead th[data-sort]");
    ths.forEach((th, idx) => {
      const btn = document.createElement("button");
      btn.type = "button"; btn.className = "sort-btn"; btn.innerHTML = th.innerHTML;
      th.innerHTML = ""; th.append(btn);
      btn.addEventListener("click", () => {
        const col = [...th.parentNode.children].indexOf(th);
        const dir = th.getAttribute("aria-sort") === "descending" ? "ascending" : "descending";
        ths.forEach((x) => x.removeAttribute("aria-sort"));
        th.setAttribute("aria-sort", dir);
        const body = table.tBodies[0];
        const rows = [...body.rows];
        const val = (r) => { const c = r.cells[col]; const v = c.dataset.v; return v !== undefined && v !== "" && !isNaN(v) ? +v : (v ?? c.textContent).toLowerCase(); };
        rows.sort((a, b) => { const x = val(a), y = val(b); return (x > y ? 1 : x < y ? -1 : 0) * (dir === "ascending" ? 1 : -1); });
        rows.forEach((r) => body.append(r));
      });
    });
  }

  function statusLine(el, s) {
    const stale = s.status !== "ok";
    el.innerHTML = `<span class="dot ${stale ? "dot-warn" : "dot-ok"}" aria-hidden="true"></span>
      Last updated ${dateTime(s.as_of)}${stale ? ". Prices could not be refreshed, so these are the last values from MarketWatch." : ""}`;
  }

  function chartDefaults() {
    if (!window.Chart) return;
    Chart.defaults.font.family = '"IBM Plex Sans", system-ui, sans-serif';
    Chart.defaults.font.size = 12;
    Chart.defaults.color = COLORS.muted;
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.boxHeight = 7;
    Chart.defaults.plugins.tooltip.backgroundColor = COLORS.ink;
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.plugins.tooltip.cornerRadius = 4;
    Chart.defaults.maintainAspectRatio = false;
    Chart.defaults.scale.grid.color = COLORS.grid;
    Chart.defaults.scale.border = { display: false };
    Chart.defaults.elements.line.borderWidth = 2;
    Chart.defaults.elements.point.radius = 0;
    Chart.defaults.elements.point.hoverRadius = 4;
    Chart.defaults.interaction = { mode: "index", intersect: false };
  }

  return { init, getJSON, getText, data, num, usd, usdSigned, pct, pctSigned, sign, esc, dateTime, date,
           tzOffsetSec, frontMatter, md, bars, sortable, statusLine, chartDefaults, COLORS,
           get cfg() { return state.cfg; } };
})();
