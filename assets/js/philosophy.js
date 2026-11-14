/* Philosophy page: text from content/philosophy.md, limits from config/rules.json, status from the last update */
(async () => {
  await App.init("philosophy.html");
  const { esc } = App;
  const [text, rules, alerts] = await Promise.all([
    App.getText("content/philosophy.md"), App.getJSON("config/rules.json", {}), App.data("alerts.json", { rules: [] }),
  ]);
  document.getElementById("philosophy").innerHTML = App.md(text);
  const label = { ok: "Respected", breach: "Breached", warning: "Attention" };
  document.querySelector("#rules-table tbody").innerHTML = (alerts.rules || []).map((r) => `<tr>
    <td class="l"><b style="font-weight:500">${esc(r.rule)}</b></td><td class="l">${esc(r.limit)}</td><td class="l">${esc(r.current)}</td>
    <td class="l"><span class="tag tag-${r.status}">${label[r.status]}</span></td></tr>`).join("");
  document.getElementById("rules-score").innerHTML = alerts.rules_total ? `${alerts.rules_ok} of ${alerts.rules_total} respected` : "";
  document.getElementById("rules-placeholder").hidden = !rules.is_placeholder;
  document.getElementById("buy").innerHTML = (rules.buy_criteria || []).map((c) => `<li>${esc(c)}</li>`).join("");
  document.getElementById("sell").innerHTML = (rules.sell_criteria || []).map((c) => `<li>${esc(c)}</li>`).join("");
  if (location.hash === "#rules") document.getElementById("rules").scrollIntoView();
})();
