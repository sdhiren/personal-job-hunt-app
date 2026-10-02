/* Settings page: Claude connection, Claude features and job sources. */
import { $, $$, esc, api, toast, withBusy, svg } from "../core.js";
import { refreshClaudePill } from "../topbar.js";

// ------------------------------------------------------------------ SETTINGS
export async function renderSettings(el) {
  const [cs, s] = await Promise.all([api("/api/claude"), api("/api/settings")]);
  const acc = cs.account || {};
  const opt = (k, title, ic, body) => `<div class="opt ${cs.mode === k ? "on" : ""}" data-mode="${k}"><h3>${svg(ic, 16)} ${title}${cs.mode === k ? `<span class="pill green" style="margin-left:auto">in use</span>` : ""}</h3>${body}</div>`;
  el.innerHTML = `
  <section class="card pad">
    <div class="section-title"><span class="ic">${svg("spark")}</span><h2>Connect Claude</h2></div>
    <p class="ink2" style="margin-top:-6px">Claude reads your resume, searches the web for jobs, scores each job against your profile, and drafts answers on application forms. Choose how the app talks to Claude:</p>
    <div class="choice">
      ${opt("account", "Claude account", "user", `<div class="small muted">Uses your Claude Pro / Max subscription through Claude Code on this computer. No extra cost; counts toward your plan's usage limits.</div>`)}
      ${opt("api_key", "API key", "key", `<div class="small muted">Uses an Anthropic API key from console.anthropic.com. Billed per token; no plan limits.</div>`)}
      ${opt("off", "Don't use Claude", "x", `<div class="small muted">Keyword matching only. No resume parsing, web search or AI scoring.</div>`)}
    </div>

    <div class="grid g2" style="margin-top:16px">
      <div class="card pad" style="box-shadow:none">
        <h3 style="margin-bottom:10px">Claude account</h3>
        <div class="kv">
          <span class="k">Claude Code</span><span>${acc.installed ? `<span class="pill green" style="display:inline-flex">installed</span>` : `<span class="pill bad">not found</span> <a href="https://claude.com/claude-code" target="_blank">install</a>`}</span>
          <span class="k">Signed in</span><span>${acc.loggedIn ? `<span class="dot ok"></span> ${esc(acc.email || "")}` : `<span class="dot off"></span> not signed in`}</span>
          ${acc.subscriptionType ? `<span class="k">Plan</span><span><span class="pill green">${esc(acc.subscriptionType)}</span></span>` : ""}
          <span class="k">Model</span><span><input type="text" id="climodel" placeholder="plan default" value="${esc(s.cli_model || "")}" style="max-width:180px"> <span class="small muted">e.g. sonnet, opus</span></span>
        </div>
        <div class="row" style="margin-top:12px">
          ${acc.loggedIn ? "" : `<button class="btn primary" id="login">${svg("user", 15)}Sign in with Claude</button>`}
          <button class="btn" id="refresh">Refresh</button>
          ${acc.loggedIn && cs.mode !== "account" ? `<button class="btn soft" id="useacc">Use this</button>` : ""}
        </div>
        <div class="small muted" style="margin-top:8px">Sign-in happens in Claude Code's own browser login; this app never sees your password or tokens.</div>
      </div>
      <div class="card pad" style="box-shadow:none">
        <h3 style="margin-bottom:10px">API key</h3>
        ${cs.api_key_saved ? `<div class="kv" style="margin-bottom:10px"><span class="k">Saved key</span><span><code>${esc(cs.api_key_hint)}</code></span><span class="k">Model</span><span>${esc(cs.api_model)}</span></div>` : ""}
        <div class="stack">
          <input type="password" id="apikey" placeholder="${cs.api_key_saved ? "Replace key (sk-ant-…)" : "sk-ant-…"}" autocomplete="off">
          <select id="apimodel">${["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"].map(m => `<option ${cs.api_model === m ? "selected" : ""}>${m}</option>`).join("")}</select>
        </div>
        <div class="row" style="margin-top:12px">
          <button class="btn primary" id="savekey" data-busy="Checking key…">${svg("key", 15)}Test &amp; save</button>
          ${cs.api_key_saved ? `<button class="btn ghost danger" id="forget">Remove key</button>` : ""}
        </div>
        <div class="small muted" style="margin-top:8px">Stored only in <code>data/settings.json</code> on this computer (readable only by you).</div>
      </div>
    </div>
    <div class="row" style="margin-top:14px"><button class="btn" id="test" data-busy="Asking Claude…" ${cs.ready ? "" : "disabled"}>Test connection</button><span class="small muted">${cs.ready ? "Ready." : "Not connected yet."}</span></div>
  </section>

  <div class="grid g2" style="margin-top:16px">
    <section class="card pad">
      <div class="section-title"><span class="ic">${svg("spark")}</span><h2>What Claude does</h2></div>
      <div class="stack">
        ${[["use_claude_discovery", "Search the web for more jobs", "Finds postings beyond the built-in company boards"], ["use_claude_scoring", "Score my top matches", "Reads each job against your resume (up to 40 per search, jobs Claude found first)"], ["use_claude_answers", "Draft answers on application forms", "Cover letters and free-text questions, from your resume only"]].map(([k, t, d]) =>
          `<label class="switch"><input type="checkbox" data-set="${k}" ${s[k] ? "checked" : ""}><span class="track"></span><span>${t}<div class="small muted" style="font-weight:400">${d}</div></span></label>`).join("")}
        <label class="f" style="max-width:240px">Jobs to find per region <input type="number" min="3" max="40" data-setnum="discovery_per_region" value="${s.discovery_per_region}"></label>
      </div>
    </section>
    <section class="card pad">
      <div class="section-title"><span class="ic">${svg("db")}</span><h2>Job sources</h2></div>
      <div class="stack">
        ${[["companies", "Company career boards", "~70 companies on Greenhouse, Lever and Ashby"], ["arbeitnow", "Arbeitnow", "Europe-focused job board"], ["remotive", "Remotive", "Remote jobs worldwide"], ["adzuna", "Adzuna", "India, UK, EU, Canada, Australia — needs a free key"]].map(([k, t, d]) =>
          `<label class="switch"><input type="checkbox" data-src="${k}" ${s.sources[k] ? "checked" : ""}><span class="track"></span><span>${t}<div class="small muted" style="font-weight:400">${d}</div></span></label>`).join("")}
        <div class="form"><label class="f">Adzuna app ID<input type="text" data-setstr="adzuna_app_id" value="${esc(s.adzuna_app_id)}"></label><label class="f">Adzuna app key<input type="password" data-setstr="adzuna_app_key" value="${esc(s.adzuna_app_key)}"></label></div>
        <div class="small muted">LinkedIn, Naukri and Indeed aren't searched — their terms forbid automation. Apply there yourself and record it with “I applied myself”.</div>
      </div>
    </section>
  </div>`;

  const setMode = async m => { await api("/api/claude/mode", { method: "POST", body: { mode: m } }); toast("Claude connection updated", "ok"); refreshClaudePill(); renderSettings(el); };
  $$("[data-mode]", el).forEach(o => o.onclick = () => setMode(o.dataset.mode));
  $("#refresh").onclick = () => { refreshClaudePill(); renderSettings(el); };
  $("#useacc") && ($("#useacc").onclick = () => setMode("account"));
  $("#login") && ($("#login").onclick = async () => { try { const r = await api("/api/claude/login", { method: "POST" }); toast(r.message, "ok"); } catch (e) { toast(e.message, "err"); } });
  $("#climodel").onchange = async e => { await api("/api/settings", { method: "PUT", body: { cli_model: e.target.value.trim() } }); toast("Saved", "ok"); };
  $("#savekey").onclick = e => withBusy(e.currentTarget, async () => {
    const key = $("#apikey").value.trim();
    if (!key) throw new Error("Paste an API key first");
    const r = await api("/api/claude/api-key", { method: "POST", body: { api_key: key, model: $("#apimodel").value } });
    toast(r.message, "ok"); refreshClaudePill(); renderSettings(el);
  });
  $("#forget") && ($("#forget").onclick = async () => { await api("/api/claude/api-key", { method: "DELETE" }); toast("Key removed"); refreshClaudePill(); renderSettings(el); });
  $("#test").onclick = e => withBusy(e.currentTarget, async () => { const r = await api("/api/claude/test", { method: "POST" }); toast(r.message, "ok"); });
  const put = async body => { await api("/api/settings", { method: "PUT", body }); toast("Saved", "ok"); };
  $$("[data-set]", el).forEach(c => c.onchange = () => put({ [c.dataset.set]: c.checked }));
  $$("[data-setnum]", el).forEach(c => c.onchange = () => put({ [c.dataset.setnum]: Number(c.value) }));
  $$("[data-setstr]", el).forEach(c => c.onchange = () => put({ [c.dataset.setstr]: c.value.trim() }));
  $$("[data-src]", el).forEach(c => c.onchange = () => put({ sources: { [c.dataset.src]: c.checked } }));
}
