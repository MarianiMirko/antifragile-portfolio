/* Team page */
(async () => {
  const cfg = await App.init("team.html");
  const { esc } = App;
  const t = await App.getJSON("content/team.json", { team: [] });
  document.getElementById("team-intro").textContent =
    `${t.team.length} students run ${cfg.fund_name} as the portfolio management team of an asset manager. Each of us owns one part of the process.`;
  document.getElementById("team").innerHTML = t.team.map((m) => `
    <article class="member"><div class="avatar" aria-hidden="true">${esc(m.initials || m.name[0])}</div>
      <div><h3>${esc(m.name)}</h3><p class="role">${esc(m.role)}</p><p>${esc(m.bio || "")}</p></div></article>`).join("");
})();
