/* Private area: sign in with Supabase, unlock once with an access key, then read the private database.
   The address and key below are public by design; the data is protected on the server, row by row. */
(async () => {
  const cfg = await App.init("private.html");
  const { esc, usd, num, pctSigned, sign } = App;
  const $ = (id) => document.getElementById(id);
  const states = ["loading", "signedout", "nokey", "member"];
  const show = (name) => states.forEach((s) => { $("state-" + s).hidden = s !== name; });
  const pa = cfg.private_area;
  if (!pa || !window.supabase) { $("state-loading").innerHTML = '<p class="muted">The private area is not available right now.</p>'; return; }
  const sb = supabase.createClient(pa.supabase_url, pa.supabase_publishable_key);

  /* ---- sign in / create account ---- */
  let mode = "in";
  document.querySelectorAll("[data-auth]").forEach((b) => b.addEventListener("click", () => {
    mode = b.dataset.auth;
    document.querySelectorAll("[data-auth]").forEach((x) => x.setAttribute("aria-pressed", x === b));
    $("auth-submit").textContent = mode === "in" ? "Sign in" : "Create account";
    $("password").autocomplete = mode === "in" ? "current-password" : "new-password";
    $("auth-hint").textContent = mode === "in" ? "Use the email and password you registered with."
      : "Choose a password of at least 8 characters. After creating the account you will be asked for your access key.";
    $("auth-msg").textContent = "";
  }));
  $("auth-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = $("email").value.trim(), password = $("password").value, msg = $("auth-msg");
    if (!email || password.length < 8) { msg.className = "form-msg bad"; msg.textContent = "Enter your email and a password of at least 8 characters."; return; }
    $("auth-submit").disabled = true; msg.className = "form-msg"; msg.textContent = mode === "in" ? "Signing in." : "Creating your account.";
    const res = mode === "in" ? await sb.auth.signInWithPassword({ email, password })
      : await sb.auth.signUp({ email, password, options: { emailRedirectTo: location.origin + location.pathname } });
    $("auth-submit").disabled = false;
    if (res.error) { msg.className = "form-msg bad"; msg.textContent = res.error.message; return; }
    if (mode === "up" && !res.data.session) { msg.className = "form-msg good"; msg.textContent = "Account created. Open the confirmation link we sent to your email, then sign in here."; return; }
    msg.textContent = "";
  });
  document.querySelectorAll("[data-signout]").forEach((b) => b.addEventListener("click", () => sb.auth.signOut()));

  /* ---- access key, entered once ---- */
  $("key-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = $("key-msg");
    msg.className = "form-msg"; msg.textContent = "Checking the key.";
    const { data, error } = await sb.rpc("redeem_access_key", { code: $("key").value });
    if (error) { msg.className = "form-msg bad"; msg.textContent = error.message; return; }
    if (data && data.ok) { $("key").value = ""; route(); return; }
    msg.className = "form-msg bad";
    msg.textContent = data && data.reason === "too_many_attempts" ? "Too many attempts. Try again in an hour."
      : "That key is not valid or has already been used. Check it and try again.";
  });

  /* ---- the private data ---- */
  const cell = (c) => (c && typeof c === "object") ? `<td class="${c.signal && c.signal !== "normal" ? "cell-" + esc(c.signal) : ""}">${esc(c.v)}</td>` : `<td>${esc(c)}</td>`;
  async function loadData() {
    const [an, sn, tr, wl] = await Promise.all([
      sb.from("analyses").select("*").order("created_at", { ascending: false }).limit(50),
      sb.from("portfolio_snapshots").select("*").order("snapshot_date", { ascending: false }).limit(120),
      sb.from("trades").select("*").order("executed_at", { ascending: false }).limit(500),
      sb.from("watchlist").select("*").order("ticker"),
    ]);
    $("analyses").innerHTML = (an.data || []).length ? an.data.map((a) => `
      <article class="note"><h3>${esc(a.title)}</h3>
        <p class="note-meta">${App.date(a.created_at)}${a.requested_by ? ", requested by " + esc(a.requested_by) : ""}</p>
        ${a.summary ? `<p style="max-width:70ch"><b style="font-weight:500">${esc(a.summary)}</b></p>` : ""}
        ${a.body_md ? `<div class="prose">${App.md(a.body_md)}</div>` : ""}
        ${a.data && a.data.columns ? `<div class="table-scroll" style="margin-top:16px"><table class="data"><thead><tr>${a.data.columns.map((c, i) => `<th class="${i ? "" : "l"}">${esc(c)}</th>`).join("")}</tr></thead>
          <tbody>${(a.data.rows || []).map((r) => `<tr>${r.map((c, i) => i ? cell(c) : `<td class="l">${esc(typeof c === "object" ? c.v : c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : ""}
      </article>`).join("") : '<p class="chart-empty">No analyses yet. Ask Claude for one and it appears here.</p>';
    document.querySelector("#snapshots tbody").innerHTML = (sn.data || []).map((r) => `<tr><td class="l">${App.date(r.snapshot_date)}</td>
      <td>${usd(r.nav)}</td><td>${usd(r.cash)}</td><td>${usd(r.invested)}</td><td>${num(r.n_positions)}</td>
      <td class="${sign(r.daily_return)}">${r.daily_return == null ? "–" : pctSigned(r.daily_return)}</td><td>${usd(r.benchmark_value)}</td></tr>`).join("");
    const side = { buy: "Buy", sell: "Sell", short: "Short", cover: "Cover" };
    $("ptrades-empty").hidden = (tr.data || []).length > 0;
    document.querySelector("#ptrades").closest(".table-scroll").hidden = !(tr.data || []).length;
    document.querySelector("#ptrades tbody").innerHTML = (tr.data || []).map((t) => `<tr><td class="l">${App.dateTime(t.executed_at)}</td><td class="l ticker">${esc(t.ticker)}</td>
      <td class="l"><span class="pill pill-${t.side === "buy" || t.side === "cover" ? "buy" : "sell"}">${side[t.side]}</span></td><td>${num(t.shares)}</td><td>${usd(t.price, 2)}</td><td>${usd(t.amount)}</td>
      <td class="l wrap-cell">${esc(t.rationale || "")}</td><td class="l">${esc(t.approved_by || "")}</td></tr>`).join("");
    $("watch-empty").hidden = (wl.data || []).length > 0;
    document.querySelector("#watch").closest(".table-scroll").hidden = !(wl.data || []).length;
    document.querySelector("#watch tbody").innerHTML = (wl.data || []).map((w) => `<tr><td class="l ticker">${esc(w.ticker)}</td><td class="l">${esc(w.name || "")}</td>
      <td class="l wrap-cell">${esc(w.note || "")}</td><td class="l">${App.date(w.added_at)}</td></tr>`).join("");
  }

  /* ---- which screen to show ---- */
  async function route() {
    const { data: { session } } = await sb.auth.getSession();
    if (!session) { show("signedout"); return; }
    const email = session.user.email;
    const { data: ok, error } = await sb.rpc("has_access");
    if (error || !ok) { $("who-nokey").textContent = email; show("nokey"); return; }
    $("who").textContent = email;
    show("member");
    loadData();
  }
  sb.auth.onAuthStateChange((event) => { if (["SIGNED_IN", "SIGNED_OUT"].includes(event)) setTimeout(route, 0); });
  route();
})();
