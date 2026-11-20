/* Philosophy page: text from content/philosophy.md, limits from config/rules.json, status from the last update */
(async () => {
  await App.init("philosophy.html");
  const { esc } = App;
  const [text, rules, alerts] = await Promise.all([
    App.getText("content/philosophy.md"), App.getJSON("config/rules.json", {}), App.data("alerts.json", { rules: [] }),
  ]);
  await App.libs;
  /* one block per "## " section, laid out on two columns */
  const parts = text.split(/\n(?=## )/).map((t) => t.trim()).filter(Boolean);
  document.getElementById("philosophy").innerHTML = parts.map((t) => `<div class="prose ph-part">${App.md(t)}</div>`).join("");
  document.querySelector("#rules-table tbody").innerHTML = (alerts.rules || []).map((r) => `<tr>
    <td class="l"><b style="font-weight:500">${esc(r.rule)}</b></td><td class="l">${esc(r.limit)}</td><td class="l">${esc(r.current)}</td></tr>`).join("");
  document.getElementById("rules-placeholder").hidden = !rules.is_placeholder;
  document.getElementById("buy").innerHTML = (rules.buy_criteria || []).map((c) => `<li>${esc(c)}</li>`).join("");
  document.getElementById("sell").innerHTML = (rules.sell_criteria || []).map((c) => `<li>${esc(c)}</li>`).join("");
  if (location.hash === "#rules") document.getElementById("rules").scrollIntoView();
})();
