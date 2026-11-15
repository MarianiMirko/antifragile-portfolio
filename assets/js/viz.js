/* Richer charts built with Apache ECharts: portfolio map, contribution waterfall,
   risk/return bubbles and the calendar of daily returns. */
const Viz = (() => {
  const C = App.COLORS;
  const FONT = '"IBM Plex Sans", system-ui, sans-serif';
  const MID = [233, 236, 240], UP = [23, 121, 78], DOWN = [181, 52, 42];
  const charts = [];
  let bound = false;

  function make(el) {
    const chart = echarts.init(el, null, { renderer: "canvas" });
    charts.push(chart);
    if (!bound) { bound = true; window.addEventListener("resize", () => charts.forEach((c) => c.resize())); }
    return chart;
  }
  const mix = (a, b, t) => a.map((x, i) => Math.round(x + (b[i] - x) * t));
  /* diverging scale: red below zero, grey at zero, green above */
  function tone(v, cap) {
    const t = Math.max(-1, Math.min(1, v / cap));
    return { fill: `rgb(${mix(MID, t >= 0 ? UP : DOWN, Math.abs(t)).join(",")})`, text: Math.abs(t) > 0.45 ? "#FFFFFF" : C.ink };
  }
  const tip = { backgroundColor: C.ink, borderWidth: 0, padding: [8, 12], textStyle: { color: "#fff", fontFamily: FONT, fontSize: 12.5 }, extraCssText: "border-radius:4px;box-shadow:none;" };
  const axisText = { color: C.muted, fontFamily: FONT, fontSize: 12 };

  /* ---- portfolio map: one tile per position, sized by value, coloured by return ---- */
  function treemap(el, positions, cash, mode) {
    const chart = echarts.getInstanceByDom(el) || make(el);
    const cap = mode === "day" ? 0.03 : 0.20;
    const val = (p) => (mode === "day" ? p.day_pct : p.unrealized_pct);
    const sectors = {};
    positions.forEach((p) => (sectors[p.sector] = sectors[p.sector] || []).push(p));
    const data = Object.entries(sectors).map(([name, list]) => ({
      name, itemStyle: { color: "#DCE2EA", borderColor: "#DCE2EA" },
      children: list.map((p) => { const t = tone(val(p), cap); return { name: p.ticker, value: p.value, p, r: val(p), itemStyle: { color: t.fill }, label: { color: t.text } }; }),
    }));
    if (cash > 0) data.push({ name: "Cash", itemStyle: { color: "#DCE2EA", borderColor: "#DCE2EA" }, children: [{ name: "Cash", value: cash, r: null, itemStyle: { color: "#F3F5F8" }, label: { color: C.muted } }] });
    chart.setOption({
      animationDuration: 400,
      tooltip: { ...tip, formatter: (i) => {
        const d = i.data;
        if (!d.p) return d.r === null ? `<b>Cash</b><br>${App.usd(d.value)}` : `<b>${App.esc(d.name)}</b><br>${App.usd(i.value)}`;
        return `<b>${App.esc(d.p.name)}</b> (${d.p.ticker})<br>${App.usd(d.p.value)}, ${App.pct(d.p.weight, 1)} of the fund<br>Today ${App.pctSigned(d.p.day_pct)}<br>Since purchase ${App.pctSigned(d.p.unrealized_pct, 1)}`;
      } },
      series: [{
        type: "treemap", roam: false, nodeClick: false, breadcrumb: { show: false },
        left: 0, right: 0, top: 0, bottom: 0, squareRatio: 1.1,
        label: { show: true, fontFamily: FONT, formatter: (i) => i.data.r == null ? `{t|${i.name}}` : `{t|${i.name}}\n{v|${App.pctSigned(i.data.r, 1)}}`,
                 rich: { t: { fontFamily: FONT, fontSize: 15, fontWeight: 600, lineHeight: 20 }, v: { fontFamily: FONT, fontSize: 12.5, lineHeight: 17 } } },
        upperLabel: { show: true, height: 24, formatter: "{b}", color: C.ink, fontFamily: FONT, fontSize: 12, fontWeight: 500, padding: [0, 0, 0, 4] },
        itemStyle: { borderColor: "#fff", borderWidth: 1, gapWidth: 2 },
        levels: [
          { itemStyle: { borderWidth: 0, gapWidth: 6, borderColor: "#fff" }, upperLabel: { show: false } },
          { itemStyle: { borderWidth: 3, gapWidth: 2 } },
          { itemStyle: { borderWidth: 0, gapWidth: 2 }, emphasis: { itemStyle: { borderColor: C.ink, borderWidth: 2 } } },
        ],
        data,
      }],
    }, true);
  }

  /* ---- waterfall: from the starting capital to today's value, one step per position ---- */
  function waterfall(el, capital, steps, nav) {
    const chart = make(el);
    const sorted = [...steps].sort((a, b) => b.value - a.value);
    const cats = ["Starting capital", ...sorted.map((s) => s.name), "Fund value today"];
    const base = [], up = [], down = [], total = [];
    let run = capital;
    total.push(capital); base.push(0); up.push("-"); down.push("-");
    sorted.forEach((s) => {
      const lo = Math.min(run, run + s.value);
      base.push(lo); up.push(s.value >= 0 ? s.value : "-"); down.push(s.value < 0 ? -s.value : "-"); total.push("-");
      run += s.value;
    });
    total.push(nav); base.push(0); up.push("-"); down.push("-");
    const all = [capital, nav]; let r = capital; sorted.forEach((s) => { r += s.value; all.push(r); });
    const span = Math.max(...all) - Math.min(...all) || capital * 0.01;
    const step = span > 400000 ? 100000 : span > 80000 ? 20000 : 5000;
    const min = Math.floor((Math.min(...all) - span * 0.2) / step) * step;
    const max = Math.ceil((Math.max(...all) + span * 0.05) / step) * step;
    const bar = (name, data, color) => ({ name, type: "bar", stack: "w", data, barWidth: "62%", itemStyle: { color, borderRadius: 2 },
      label: { show: name !== "Total", position: "right", fontFamily: FONT, fontSize: 12, color: C.ink, formatter: (i) => (name === "Lost" ? "−$" : "+$") + App.num(Math.abs(i.value)) } });
    el.style.height = Math.max(300, cats.length * 30 + 60) + "px"; chart.resize();
    chart.setOption({
      grid: { left: 8, right: 96, top: 8, bottom: 28, containLabel: true },
      tooltip: { ...tip, trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: "rgba(17,38,74,0.05)" } }, formatter: (items) => {
        const i = items[0].dataIndex, name = cats[i];
        if (i === 0) return `<b>${name}</b><br>${App.usd(capital)}`;
        if (i === cats.length - 1) return `<b>${name}</b><br>${App.usd(nav)}`;
        const s = sorted[i - 1];
        return `<b>${App.esc(s.full || name)}</b><br>${App.usdSigned(s.value)} (${App.pctSigned(s.value / capital)} of starting capital)${s.closed ? "<br>position closed" : ""}`;
      } },
      xAxis: { type: "value", min, max, splitNumber: el.clientWidth < 620 ? 3 : 6, axisLabel: { ...axisText, hideOverlap: true, formatter: (v) => "$" + (v / 1e6).toFixed(2) + "M" }, splitLine: { lineStyle: { color: C.grid } } },
      yAxis: { type: "category", inverse: true, data: cats, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { ...axisText, color: C.ink, fontWeight: 500 } },
      series: [
        { type: "bar", stack: "w", data: base, itemStyle: { color: "transparent" }, emphasis: { disabled: true }, silent: true, tooltip: { show: false } },
        bar("Total", total, C.navy), bar("Gained", up, C.up), bar("Lost", down, C.down),
      ],
    });
  }

  /* ---- risk against return: one bubble per position, sized by weight ---- */
  function bubbles(el, rows) {
    const chart = make(el);
    const maxW = Math.max(...rows.map((r) => r.weight));
    chart.setOption({
      grid: { left: 8, right: 28, top: 44, bottom: 36, containLabel: true },
      tooltip: { ...tip, formatter: (i) => { const r = i.data.r; return `<b>${App.esc(r.name)}</b> (${r.ticker})<br>Volatility ${App.pct(r.vol, 1)}<br>Return since purchase ${App.pctSigned(r.ret, 1)}<br>Weight ${App.pct(r.weight, 1)}`; } },
      xAxis: { type: "value", name: "Volatility, annualised", nameLocation: "middle", nameGap: 30, nameTextStyle: axisText, scale: true,
               axisLabel: { ...axisText, formatter: "{value}%" }, splitLine: { lineStyle: { color: C.grid } }, axisLine: { show: false } },
      yAxis: { type: "value", name: "Return since purchase", nameTextStyle: { ...axisText, align: "left" }, scale: true,
               axisLabel: { ...axisText, formatter: "{value}%" }, splitLine: { lineStyle: { color: C.grid } } },
      series: [{
        type: "scatter",
        data: rows.map((r) => ({ value: [r.vol * 100, r.ret * 100], r, symbolSize: 16 + 44 * Math.sqrt(r.weight / maxW),
                                 itemStyle: { color: r.ret >= 0 ? "rgba(31,95,184,0.78)" : "rgba(196,116,26,0.82)", borderColor: "#fff", borderWidth: 2 } })),
        label: { show: true, formatter: (i) => i.data.r.ticker, position: "top", distance: 4, color: C.ink, fontFamily: FONT, fontSize: 12, fontWeight: 600 },
        labelLayout: { hideOverlap: true },
        markLine: { silent: true, symbol: "none", lineStyle: { color: C.muted, type: "solid", width: 1 }, label: { show: false }, data: [{ yAxis: 0 }] },
      }],
    });
  }

  /* ---- calendar: one cell per day, coloured by the fund's daily return ---- */
  function calendar(el, days, start, end) {
    const chart = make(el);
    const months = (new Date(end).getFullYear() - new Date(start).getFullYear()) * 12 + new Date(end).getMonth() - new Date(start).getMonth() + 1;
    const cap = Math.max(1, Math.ceil(Math.max(...days.map((d) => Math.abs(d[1] * 100)))));
    const narrow = el.clientWidth < 620;
    el.style.height = (narrow ? Math.ceil(months * 31 / 7 + 1) * 20 + 90 : 290) + "px"; chart.resize();
    chart.setOption({
      tooltip: { ...tip, formatter: (i) => `<b>${App.date(i.value[0])}</b><br>${App.pctSigned(i.value[1] / 100)}` },
      visualMap: { min: -cap, max: cap, calculable: false, orient: "horizontal", left: 0, bottom: 0, itemWidth: 10, itemHeight: 150,
                   text: [`+${cap}%`, `−${cap}%`], textStyle: axisText, inRange: { color: [`rgb(${DOWN})`, `rgb(${MID})`, `rgb(${UP})`] } },
      calendar: {
        orient: narrow ? "vertical" : "horizontal", range: [start.slice(0, 7), end.slice(0, 7)],
        left: narrow ? 44 : 36, right: narrow ? 8 : 12, top: 30, bottom: 48, cellSize: narrow ? ["auto", 20] : ["auto", "auto"],
        splitLine: { lineStyle: { color: "#fff", width: 3 } }, itemStyle: { color: "#F3F5F8", borderColor: "#fff", borderWidth: 2 },
        dayLabel: { firstDay: 1, nameMap: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], ...axisText },
        monthLabel: { nameMap: "EN", ...axisText, color: C.ink, fontWeight: 500 }, yearLabel: { show: false },
      },
      series: [{ type: "heatmap", coordinateSystem: "calendar", data: days.map((d) => [d[0], +(d[1] * 100).toFixed(3)]),
                 label: { show: !narrow, fontFamily: FONT, fontSize: 10.5, color: C.ink, formatter: (i) => (Math.abs(i.value[1]) < 0.05 ? "0.0" : (i.value[1] > 0 ? "+" : "−") + Math.abs(i.value[1]).toFixed(1)) },
                 emphasis: { itemStyle: { borderColor: C.ink, borderWidth: 1 } } }],
    });
  }

  /* ECharts is by far the largest file of the site, so it loads in the background. A chart asked for
     before it has arrived is drawn as soon as it does. */
  const waiting = [];
  const whenLoaded = (draw) => (...args) => { if (window.echarts) draw(...args); else waiting.push(() => draw(...args)); };
  window.addEventListener("echarts-loaded", () => waiting.splice(0).forEach((run) => run()));
  return { treemap: whenLoaded(treemap), waterfall: whenLoaded(waterfall), bubbles: whenLoaded(bubbles), calendar: whenLoaded(calendar) };
})();
