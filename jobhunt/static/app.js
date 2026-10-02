/* jobhunt — single-page local app (no build step, no external deps) */
"use strict";

// ------------------------------------------------------------------ helpers
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtDate = s => s ? new Date(s).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "";
const ago = s => {
  if (!s) return "";
  const d = (Date.now() - new Date(s).getTime()) / 1000;
  if (d < 90) return "just now";
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  if (d < 86400) return `${Math.round(d / 3600)}h ago`;
  return `${Math.round(d / 86400)}d ago`;
};
const money = (v, cur) => {
  if (!v) return "";
  const n = Number(String(v).replace(/[, ]/g, ""));
  const txt = Number.isFinite(n) && n > 999 ? n.toLocaleString(cur === "INR" ? "en-IN" : undefined) : v;
  return `${txt} ${cur || ""}`.trim();
};
const REGION = { india: "India", europe: "Europe", canada: "Canada", australia: "Australia", remote_global: "Remote (global)", other: "Other" };
const STATUS_LABEL = {
  queued: "Queued", in_progress: "Filling form", needs_manual: "To finish", applied: "Applied", failed: "Failed",
  skipped: "Not interested", screening: "Screening", interviewing: "Interviewing", offer: "Offer",
  rejected: "Rejected", withdrawn: "Withdrawn",
};
const STATUS_TONE = { applied: "green", screening: "info", interviewing: "info", offer: "green", rejected: "bad", failed: "bad", needs_manual: "warn", queued: "warn", in_progress: "warn" };

async function api(path, opts = {}) {
  const o = { ...opts };
  if (o.body && !(o.body instanceof FormData)) { o.body = JSON.stringify(o.body); o.headers = { "Content-Type": "application/json" }; }
  const r = await fetch(path, o);
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new Error((data && data.detail) || r.statusText);
  return data;
}
function toast(msg, kind = "") {
  const t = document.createElement("div");
  t.className = `toast ${kind}`; t.textContent = msg;
  $("#toasts").append(t);
  setTimeout(() => t.remove(), kind === "err" ? 7000 : 3800);
}
async function withBusy(btn, fn) {
  const html = btn.innerHTML; btn.disabled = true; btn.innerHTML = `<span class="spin"></span> ${btn.dataset.busy || "Working…"}`;
  try { return await fn(); } catch (e) { toast(e.message, "err"); } finally { btn.disabled = false; btn.innerHTML = html; }
}
const icon = {
  home: '<path d="M3 11 12 4l9 7"/><path d="M5 10v10h14V10"/>',
  jobs: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  apps: '<rect x="3" y="4" width="5" height="16" rx="1.5"/><rect x="10" y="4" width="5" height="11" rx="1.5"/><rect x="17" y="4" width="4" height="7" rx="1.5"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4 4.5-6 8-6s7 2 8 6"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>',
  file: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>',
  money: '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="3"/>',
  pin: '<path d="M12 21s7-6 7-11a7 7 0 0 0-14 0c0 5 7 11 7 11z"/><circle cx="12" cy="10" r="2.5"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
  send: '<path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4z"/>',
  ext: '<path d="M14 4h6v6"/><path d="M20 4 10 14"/><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/>',
  check: '<path d="m5 12 5 5 9-10"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9M17 6l3 3M15 8l2 2"/>',
  db: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
};
const svg = (n, w = 18) => `<svg viewBox="0 0 24 24" width="${w}" height="${w}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${icon[n]}</svg>`;

// ------------------------------------------------------------------ router
const ROUTES = {
  dashboard: { title: "Dashboard", icon: "home", render: renderDashboard },
  jobs: { title: "Jobs", icon: "jobs", render: renderJobs },
  applications: { title: "Applications", icon: "apps", render: renderApplications },
  profile: { title: "My profile", icon: "user", render: renderProfile },
  settings: { title: "Settings", icon: "gear", render: renderSettings },
};
const state = { jobsFilter: { decision: "apply", region: "", q: "", wfh: false }, selected: new Set(), counts: {} };

function route() {
  const name = (location.hash.replace(/^#\//, "").split("?")[0]) || "dashboard";
  const r = ROUTES[name] || ROUTES.dashboard;
  $("#title").textContent = r.title;
  renderNav();
  closeDrawer();
  window.scrollTo(0, 0);
  r.render($("#page"));
}
window.addEventListener("hashchange", route);
function renderNav() {
  const name = (location.hash.replace(/^#\//, "").split("?")[0]) || "dashboard";
  const cur = ROUTES[name] || ROUTES.dashboard;
  const badge = n => n ? `<span class="count">${n}</span>` : "";
  $("#nav").innerHTML = Object.entries(ROUTES).map(([k, v]) =>
    `<a href="#/${k}" class="${cur === v ? "on" : ""}">${svg(v.icon)}${v.title}${k === "jobs" ? badge(state.counts.matches) : ""}${k === "applications" ? badge(state.counts.todo) : ""}</a>`).join("");
}
const rerender = () => { const n = (location.hash.replace(/^#\//, "") || "dashboard"); (ROUTES[n] || ROUTES.dashboard).render($("#page")); };

// ------------------------------------------------------------------ tooltip for charts
document.addEventListener("mousemove", e => {
  const t = e.target.closest("[data-tip]"), tip = $("#tip");
  if (!t) { tip.hidden = true; return; }
  tip.textContent = t.dataset.tip; tip.hidden = false;
  tip.style.left = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8) + "px"; tip.style.top = (e.clientY + 14) + "px";
});

function barChart(rows, emptyText) {
  const max = Math.max(1, ...rows.map(r => r.value));
  if (!rows.some(r => r.value)) return `<div class="empty small">${emptyText}</div>`;
  return `<div class="bars" role="table">${rows.map(r => `
    <div class="bar" role="row" data-tip="${esc(r.label)}: ${r.value}${r.extra ? " · " + r.extra : ""}">
      <span class="lbl" role="cell">${esc(r.label)}</span>
      <span class="trk"><span class="fill" style="width:${(r.value / max) * 100}%"></span></span>
      <span class="num" role="cell">${r.value}</span>
    </div>`).join("")}</div>`;
}

// ------------------------------------------------------------------ DASHBOARD
async function renderDashboard(el) {
  el.innerHTML = `<div class="empty"><span class="spin"></span></div>`;
  const [p, s, top] = await Promise.all([api("/api/profile"), api("/api/stats"), api("/api/jobs?decision=apply&limit=6")]);
  state.counts = { matches: s.matches, todo: (s.by_status.needs_manual || 0) + (s.by_status.queued || 0) };
  const c = p.candidate || {};
  const name = [c.first_name, c.last_name].filter(Boolean).join(" ") || "Welcome";
  const initials = name.split(" ").map(x => x[0]).join("").slice(0, 2).toUpperCase();
  const skills = (p.matching?.skills || []).slice().sort((a, b) => b.weight - a.weight);
  const fact = (k, v) => v ? `<div class="fact"><div class="k">${k}</div><div class="v">${esc(v)}</div></div>` : "";
  const pipelineOrder = ["applied", "screening", "interviewing", "offer", "rejected", "needs_manual", "skipped", "withdrawn", "failed"];
  const pipeline = pipelineOrder.filter(k => ["applied", "screening", "interviewing", "offer", "rejected"].includes(k) || s.by_status[k])
    .map(k => ({ label: STATUS_LABEL[k], value: s.by_status[k] || 0 }));
  const regions = ["india", "remote_global", "europe", "canada", "australia"].map(k => ({ label: REGION[k], value: s.by_region[k] || 0 }));

  el.innerHTML = `
  ${!p.resume ? `<div class="card pad" style="margin-bottom:16px;border-color:var(--primary)"><div class="row"><b>Start here:</b> upload your resume and fill in your details so jobs can be matched to you.<span class="grow" style="flex:1"></span><a class="btn primary" href="#/profile">Set up profile</a></div></div>` : ""}
  <section class="card pad hero">
    <div class="avatar">${esc(initials || "?")}</div>
    <div>
      <h1>${esc(name)}</h1>
      <div class="ink2">${esc([c.current_title, c.current_company].filter(Boolean).join(" · "))}${c.years_experience ? ` · ${c.years_experience} yrs experience` : ""}</div>
      ${c.summary ? `<div class="muted" style="margin-top:4px">${esc(c.summary)}</div>` : ""}
      <div class="facts">
        ${fact("Location", [c.city, c.country].filter(Boolean).join(", "))}
        ${fact("Email", c.email)}${fact("Phone", c.phone)}
        ${fact("Expected pay", money(c.expected_ctc, c.currency))}
        ${fact("Current pay", money(c.current_ctc, c.currency))}
        ${fact("Notice period", c.notice_period)}
        ${fact("Looking in", (p.search?.regions || []).map(r => REGION[r]).join(", "))}
        ${fact("Visa sponsorship", c.requires_visa_sponsorship_abroad ? "Needed abroad" : "Not needed")}
      </div>
      ${(c.target_titles || []).length ? `<div class="chips" style="margin-top:12px">${c.target_titles.map(t => `<span class="pill green">${esc(t)}</span>`).join("")}</div>` : ""}
      ${skills.length ? `<div class="chips" style="margin-top:8px">${skills.slice(0, 14).map(k => `<span class="chip" title="weight ${k.weight}/4">${esc(k.name)}</span>`).join("")}${skills.length > 14 ? `<span class="chip">+${skills.length - 14}</span>` : ""}</div>` : ""}
    </div>
    <div class="stack" style="align-items:flex-end">
      <a class="btn" href="#/profile">${svg("user", 16)}Edit profile</a>
      ${p.resume ? `<a class="btn ghost sm" href="/api/resume/file" target="_blank">${svg("file", 14)}${esc(p.resume.name)}</a>` : ""}
    </div>
  </section>

  <div class="grid g4" style="margin-top:16px">
    <div class="card tile"><div class="k">Jobs scanned</div><div class="v">${s.jobs_total.toLocaleString()}</div><div class="s">${s.last_scrape ? "last search " + ago(s.last_scrape) : "no search yet"}</div></div>
    <a class="card tile" href="#/jobs" style="color:inherit;text-decoration:none"><div class="k">Matches for you</div><div class="v">${s.matches}</div><div class="s">${s.review} more need a look</div></a>
    <a class="card tile" href="#/applications" style="color:inherit;text-decoration:none"><div class="k">Applied</div><div class="v">${s.applied}</div><div class="s">${s.applied_today} today</div></a>
    <a class="card tile" href="#/applications" style="color:inherit;text-decoration:none"><div class="k">Interviews &amp; offers</div><div class="v">${s.interviews}</div><div class="s">${s.by_status.offer || 0} offers</div></a>
  </div>

  <div class="grid g2" style="margin-top:16px">
    <div class="card pad"><div class="card-h"><h2>Application pipeline</h2><a class="small" href="#/applications">Open board →</a></div>
      ${barChart(pipeline, "No applications yet — apply from the Jobs page.")}</div>
    <div class="card pad"><div class="card-h"><h2>Matches by region</h2><a class="small" href="#/jobs">All matches →</a></div>
      ${barChart(regions, "Run “Find jobs” to see matches.")}</div>
  </div>

  <div class="grid g2" style="margin-top:16px">
    <div class="card pad"><div class="card-h"><h2>Top matches</h2><a class="small" href="#/jobs">See all →</a></div>
      ${top.jobs.length ? `<div class="stack">${top.jobs.map(j => `
        <div class="row" style="flex-wrap:nowrap;cursor:pointer" data-open="${esc(j.id)}">
          <div class="score" style="--p:${j.score}">${j.score}</div>
          <div style="min-width:0;flex:1"><div style="font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(j.title)}</div>
          <div class="small muted">${esc(j.company)} · ${esc(REGION[j.region] || "")}${j.is_wfh ? " · WFH" : ""}</div></div>
          <button class="btn sm soft" data-apply="${esc(j.id)}">Apply</button>
        </div>`).join("")}</div>` : `<div class="empty small">No matches yet.</div>`}
    </div>
    <div class="card pad"><div class="card-h"><h2>Recent activity</h2></div>
      ${s.recent.length ? `<div class="timeline">${s.recent.map(e => `
        <div class="ev"><div><b>${esc(STATUS_LABEL[e.status] || e.status)}</b> — ${esc(e.company)}, <span class="ink2">${esc(e.title)}</span>
        <div class="small muted">${ago(e.ts)}${e.note ? " · " + esc(e.note) : ""}</div></div></div>`).join("")}</div>` : `<div class="empty small">Nothing yet.</div>`}
    </div>
  </div>`;
  bindJobActions(el);
  renderNav();
}

function bindJobActions(el) {
  $$("[data-open]", el).forEach(n => n.addEventListener("click", e => { if (!e.target.closest("button,input,a")) openJob(n.dataset.open); }));
  $$("[data-apply]", el).forEach(b => b.addEventListener("click", e => { e.stopPropagation(); queueApply([b.dataset.apply]); }));
}

async function queueApply(ids) {
  try {
    const r = await api("/api/apply", { method: "POST", body: { job_ids: ids } });
    toast(`${r.added} application${r.added === 1 ? "" : "s"} queued — a browser window will open. Review each form and click Submit.`, "ok");
    pollApply();
    state.selected.clear();
    rerender();
  } catch (e) { toast(e.message, "err"); }
}

// ------------------------------------------------------------------ JOBS
async function renderJobs(el) {
  const f = state.jobsFilter;
  el.innerHTML = `
    <div class="toolbar">
      <div class="tabs" id="dtabs">${[["apply", "Matches"], ["review", "Needs review"], ["reject", "Filtered out"], ["all", "All"]].map(([k, l]) => `<button data-d="${k}" class="${f.decision === k ? "on" : ""}">${l}</button>`).join("")}</div>
      <input type="search" id="q" placeholder="Search title, company, city…" value="${esc(f.q)}">
      <select id="region"><option value="">All regions</option>${Object.entries(REGION).filter(([k]) => k !== "other").map(([k, v]) => `<option value="${k}" ${f.region === k ? "selected" : ""}>${v}</option>`).join("")}</select>
      <label class="switch"><input type="checkbox" id="wfh" ${f.wfh ? "checked" : ""}><span class="track"></span>WFH only</label>
      <span style="flex:1"></span><span class="muted small" id="total"></span>
    </div>
    <div id="list" class="joblist"><div class="empty"><span class="spin"></span></div></div>
    <div id="bulk"></div>`;
  $$("#dtabs button").forEach(b => b.onclick = () => { f.decision = b.dataset.d; state.selected.clear(); renderJobs(el); });
  let tmr; $("#q").oninput = e => { clearTimeout(tmr); tmr = setTimeout(() => { f.q = e.target.value; loadJobs(); }, 250); };
  $("#region").onchange = e => { f.region = e.target.value; loadJobs(); };
  $("#wfh").onchange = e => { f.wfh = e.target.checked; loadJobs(); };
  loadJobs();
}

async function loadJobs() {
  const f = state.jobsFilter;
  const qs = new URLSearchParams({ decision: f.decision, region: f.region, q: f.q, wfh: f.wfh, limit: 200 });
  const r = await api("/api/jobs?" + qs);
  $("#total").textContent = `${r.total.toLocaleString()} job${r.total === 1 ? "" : "s"}${r.total > r.jobs.length ? ` · showing top ${r.jobs.length}` : ""}`;
  const list = $("#list");
  if (!r.jobs.length) {
    list.innerHTML = `<div class="card empty"><h3>No jobs here yet</h3><p>Click <b>Find jobs</b> to search, or loosen the filters.</p></div>`;
    renderBulk(); return;
  }
  list.innerHTML = r.jobs.map(j => {
    const visa = j.visa && j.visa !== "n/a" ? `<span class="pill ${j.visa === "yes" ? "green" : j.visa === "likely" ? "info" : j.visa === "no" ? "bad" : "warn"}">visa: ${esc(j.visa)}</span>` : "";
    return `<div class="card job ${state.selected.has(j.id) ? "sel" : ""}" data-open="${esc(j.id)}">
      <input type="checkbox" data-sel="${esc(j.id)}" ${state.selected.has(j.id) ? "checked" : ""} aria-label="select">
      <div class="score" style="--p:${j.score ?? 0}" title="${j.llm_score != null ? "Claude score" : "keyword score"}">${j.score ?? "–"}</div>
      <div style="min-width:0">
        <div class="t">${esc(j.title)}</div>
        <div class="ink2">${esc(j.company)} · ${esc((j.location || "").slice(0, 70))}</div>
        <div class="meta">
          <span class="pill">${esc(REGION[j.region] || j.region || "")}</span>
          ${j.is_wfh ? `<span class="pill green">WFH</span>` : ""}${visa}
          ${j.rating ? `<span class="pill" title="approximate Glassdoor rating">★ ${j.rating}</span>` : `<span class="pill warn">rating ?</span>`}
          ${j.llm_score != null ? `<span class="pill info">${svg("spark", 12)} Claude</span>` : ""}
          ${j.source === "claude" ? `<span class="pill info">found by Claude</span>` : ""}
          ${j.app_status ? `<span class="pill ${STATUS_TONE[j.app_status] || ""}">${esc(STATUS_LABEL[j.app_status] || j.app_status)}</span>` : ""}
          <span class="small muted">${esc((j.reasons[0] || "").slice(0, 80))}</span>
        </div>
      </div>
      <div class="row" style="flex-wrap:nowrap">
        <a class="btn sm ghost" href="${esc(j.url)}" target="_blank" title="Open posting">${svg("ext", 14)}</a>
        <button class="btn sm soft" data-apply="${esc(j.id)}">${svg("send", 14)}Apply</button>
      </div></div>`;
  }).join("");
  bindJobActions(list);
  $$("[data-sel]", list).forEach(cb => cb.addEventListener("change", () => {
    cb.checked ? state.selected.add(cb.dataset.sel) : state.selected.delete(cb.dataset.sel);
    cb.closest(".job").classList.toggle("sel", cb.checked); renderBulk();
  }));
  renderBulk();
}

function renderBulk() {
  const n = state.selected.size, b = $("#bulk");
  if (!b) return;
  b.innerHTML = n ? `<div class="bulkbar"><b>${n} selected</b><span style="flex:1"></span>
    <button class="btn sm" id="bclear">Clear</button>
    <button class="btn sm" id="bskip">Not interested</button>
    <button class="btn sm primary" id="bapply">${svg("send", 14)}Apply to ${n}</button></div>` : "";
  if (!n) return;
  $("#bclear").onclick = () => { state.selected.clear(); loadJobs(); };
  $("#bapply").onclick = () => queueApply([...state.selected]);
  $("#bskip").onclick = async () => { for (const id of state.selected) await api("/api/status", { method: "POST", body: { job_id: id, status: "skipped" } }); state.selected.clear(); toast("Hidden from your matches"); loadJobs(); };
}

// ------------------------------------------------------------------ drawer (job detail)
function closeDrawer() { $("#drawer-root").innerHTML = ""; }
document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrawer(); });

async function openJob(id) {
  const root = $("#drawer-root");
  root.innerHTML = `<div class="scrim"></div><aside class="drawer"><div class="db"><div class="empty"><span class="spin"></span></div></div></aside>`;
  $(".scrim", root).onclick = closeDrawer;
  const j = await api("/api/job?id=" + encodeURIComponent(id));
  const a = j.application, L = j.llm;
  root.querySelector(".drawer").innerHTML = `
    <div class="dh">
      <div class="score" style="--p:${j.score ?? 0}">${j.score ?? "–"}</div>
      <div style="flex:1;min-width:0"><h2>${esc(j.title)}</h2><div class="ink2">${esc(j.company)} · ${esc(j.location)}</div>
        <div class="meta row" style="margin-top:6px;gap:6px">
          <span class="pill">${esc(REGION[j.region] || "")}</span>${j.is_wfh ? `<span class="pill green">WFH</span>` : ""}
          ${j.visa && j.visa !== "n/a" ? `<span class="pill">visa: ${esc(j.visa)}</span>` : ""}
          <span class="pill">★ ${j.rating ?? "?"}</span><span class="pill">${esc(j.source)}</span>
          ${j.posted_at ? `<span class="small muted">posted ${fmtDate(j.posted_at)}</span>` : ""}
        </div></div>
      <button class="btn ghost sm" id="dclose" aria-label="close">${svg("x", 16)}</button>
    </div>
    <div class="db stack" style="gap:16px">
      <div><h3>Why this score</h3><ul class="reasons">${j.reasons.map(r => `<li>${esc(r)}</li>`).join("")}</ul>
        <div class="small muted" style="margin-top:4px">Keyword score ${j.kw_score ?? "–"}${j.llm_score != null ? ` · Claude score ${j.llm_score}` : ""}</div></div>
      ${L ? `<div class="grid g2"><div class="card pad" style="box-shadow:none"><h3 style="color:var(--primary-strong)">Strengths</h3><ul class="reasons">${(L.strengths || []).map(s => `<li>${esc(s)}</li>`).join("")}</ul></div>
        <div class="card pad" style="box-shadow:none"><h3 style="color:var(--warn)">Gaps</h3><ul class="reasons">${(L.gaps || []).map(s => `<li>${esc(s)}</li>`).join("") || "<li>None noted</li>"}</ul></div></div>` : ""}
      ${a ? `<div class="card pad" style="box-shadow:none;background:var(--primary-ghost)">
        <div class="card-h" style="margin-bottom:8px"><h3>Your application</h3><span class="pill ${STATUS_TONE[a.status] || ""}">${esc(STATUS_LABEL[a.status] || a.status)}</span></div>
        <div class="row" style="margin-bottom:8px"><select id="dstatus" style="width:auto">${Object.entries(STATUS_LABEL).map(([k, v]) => `<option value="${k}" ${k === a.status ? "selected" : ""}>${v}</option>`).join("")}</select>
          <input type="text" id="dnote" placeholder="Add a note (e.g. HR call on Tue)" style="flex:1;min-width:180px"><button class="btn sm primary" id="dsave">Update</button></div>
        ${a.screenshot ? `<a class="small" target="_blank" href="/api/screenshot?path=${encodeURIComponent(a.screenshot)}">View form screenshot</a>` : ""}
        <div class="timeline" style="margin-top:6px">${j.events.map(e => `<div class="ev"><div><b>${esc(STATUS_LABEL[e.status] || e.status)}</b> <span class="small muted">${fmtDate(e.ts)} ${new Date(e.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>${e.note ? `<div class="small ink2">${esc(e.note)}</div>` : ""}</div></div>`).join("")}</div>
      </div>` : ""}
      <div><h3 style="margin-bottom:6px">Job description</h3><div class="desc">${esc(j.description || "No description captured — open the posting.")}</div></div>
    </div>
    <div class="df">
      ${!a || ["queued", "needs_manual", "failed"].includes(a.status) ? `<button class="btn primary" id="dapply">${svg("send", 15)}Apply in browser</button>` : ""}
      ${a && a.status === "needs_manual" ? `<button class="btn" id="ddone">${svg("check", 15)}I submitted it</button>` : ""}
      ${!a ? `<button class="btn" id="dmark">${svg("check", 15)}I applied myself</button>` : ""}
      <a class="btn" href="${esc(j.url)}" target="_blank">${svg("ext", 15)}Open posting</a>
      ${j.llm_score == null ? `<button class="btn" id="dscore" data-busy="Claude is reading…">${svg("spark", 15)}Score with Claude</button>` : ""}
      <span style="flex:1"></span>
      ${!a ? `<button class="btn ghost danger" id="dskip">Not interested</button>` : ""}
    </div>`;
  const setS = async (status, note = "") => { await api("/api/status", { method: "POST", body: { job_id: id, status, note } }); toast(`Marked ${STATUS_LABEL[status]}`, "ok"); openJob(id); rerender(); };
  $("#dclose").onclick = closeDrawer;
  $("#dapply") && ($("#dapply").onclick = () => queueApply([id]));
  $("#ddone") && ($("#ddone").onclick = () => setS("applied", "confirmed by you"));
  $("#dmark") && ($("#dmark").onclick = () => setS("applied", "applied outside the app"));
  $("#dskip") && ($("#dskip").onclick = () => setS("skipped"));
  $("#dsave") && ($("#dsave").onclick = () => setS($("#dstatus").value, $("#dnote").value));
  $("#dscore") && ($("#dscore").onclick = e => withBusy(e.currentTarget, async () => { await api("/api/job/score", { method: "POST", body: { id } }); toast("Scored by Claude", "ok"); openJob(id); rerender(); }));
}

// ------------------------------------------------------------------ APPLICATIONS (kanban)
const COLUMNS = [
  { key: "todo", title: "To do", statuses: ["queued", "in_progress", "needs_manual", "failed"], drop: "needs_manual" },
  { key: "applied", title: "Applied", statuses: ["applied"], drop: "applied" },
  { key: "screening", title: "Screening", statuses: ["screening"], drop: "screening" },
  { key: "interviewing", title: "Interviewing", statuses: ["interviewing"], drop: "interviewing" },
  { key: "offer", title: "Offer", statuses: ["offer"], drop: "offer" },
  { key: "closed", title: "Closed", statuses: ["rejected", "withdrawn", "skipped"], drop: "rejected" },
];

async function renderApplications(el) {
  const apps = await api("/api/applications");
  state.counts.todo = apps.filter(a => ["needs_manual", "queued"].includes(a.status)).length;
  renderNav();
  el.innerHTML = `
    <div class="toolbar"><span class="ink2">Drag cards between columns to update their status. Click a card for details and notes.</span>
      <span style="flex:1"></span><a class="btn sm" href="/api/export.csv">${svg("db", 14)}Export CSV</a></div>
    ${apps.length ? `<div class="board">${COLUMNS.map(col => {
      const items = apps.filter(a => col.statuses.includes(a.status));
      return `<div class="col" data-drop="${col.drop}"><h3><span>${col.title}</span><span class="muted">${items.length}</span></h3>
        ${items.map(a => `<div class="kcard" draggable="true" data-job="${esc(a.job_id)}">
          <div class="c">${esc(a.company)}</div><div class="ti">${esc(a.title)}</div>
          <div class="row" style="gap:6px"><span class="pill ${STATUS_TONE[a.status] || ""}">${esc(STATUS_LABEL[a.status] || a.status)}</span>
          <span class="small muted">${esc(fmtDate(a.applied_at || a.updated_at))}</span></div>
          ${a.notes ? `<div class="small ink2" style="margin-top:6px">${esc(a.notes)}</div>` : ""}
          ${a.status === "needs_manual" ? `<div class="row" style="margin-top:8px;gap:6px"><button class="btn sm soft" data-done="${esc(a.job_id)}">I submitted it</button><button class="btn sm" data-reapply="${esc(a.job_id)}">Retry</button></div>` : ""}
          ${a.status === "failed" ? `<div class="small" style="color:var(--bad);margin-top:6px">${esc((a.error || "").slice(0, 90))}</div>` : ""}
        </div>`).join("")}</div>`;
    }).join("")}</div>`
    : `<div class="card empty"><h3>No applications yet</h3><p>Open <a href="#/jobs">Jobs</a>, pick roles you like and click <b>Apply</b>.<br>Applied somewhere else? Open the job and use “I applied myself”.</p></div>`}`;

  let dragId = null;
  $$(".kcard", el).forEach(c => {
    c.addEventListener("dragstart", () => { dragId = c.dataset.job; c.classList.add("dragging"); });
    c.addEventListener("dragend", () => c.classList.remove("dragging"));
    c.addEventListener("click", e => { if (!e.target.closest("button")) openJob(c.dataset.job); });
  });
  $$(".col", el).forEach(col => {
    col.addEventListener("dragover", e => { e.preventDefault(); col.classList.add("over"); });
    col.addEventListener("dragleave", () => col.classList.remove("over"));
    col.addEventListener("drop", async e => {
      e.preventDefault(); col.classList.remove("over");
      if (!dragId) return;
      await api("/api/status", { method: "POST", body: { job_id: dragId, status: col.dataset.drop, note: "moved on board" } });
      dragId = null; renderApplications(el);
    });
  });
  $$("[data-done]", el).forEach(b => b.onclick = async () => { await api("/api/status", { method: "POST", body: { job_id: b.dataset.done, status: "applied", note: "confirmed by you" } }); renderApplications(el); });
  $$("[data-reapply]", el).forEach(b => b.onclick = () => queueApply([b.dataset.reapply]));
}

// ------------------------------------------------------------------ PROFILE
const getPath = (o, p) => p.split(".").reduce((x, k) => x?.[k], o);
function setPath(o, p, v) { const ks = p.split("."); let x = o; ks.slice(0, -1).forEach(k => x = x[k] ??= {}); x[ks.at(-1)] = v; }

function chipInput(id, values, placeholder) {
  return `<div class="chipinput" id="${id}" data-values='${esc(JSON.stringify(values || []))}'>
    ${(values || []).map((v, i) => `<span class="chip">${esc(v)}<button type="button" data-rm="${i}" aria-label="remove">×</button></span>`).join("")}
    <input type="text" placeholder="${esc(placeholder)}"></div>`;
}
function bindChipInput(box) {
  const vals = () => JSON.parse(box.dataset.values);
  const set = v => { box.dataset.values = JSON.stringify(v); box.outerHTML = chipInput(box.id, v, $("input", box).placeholder); bindChipInput($("#" + box.id)); };
  $$("[data-rm]", box).forEach(b => b.onclick = () => { const v = vals(); v.splice(+b.dataset.rm, 1); set(v); });
  const inp = $("input", box);
  inp.onkeydown = e => {
    if ((e.key === "Enter" || e.key === ",") && inp.value.trim()) { e.preventDefault(); const v = vals(); v.push(inp.value.trim()); set(v); $("#" + box.id + " input").focus(); }
    if (e.key === "Backspace" && !inp.value) { const v = vals(); v.pop(); set(v); $("#" + box.id + " input").focus(); }
  };
}

function skillsEditor(skills) {
  return `<div class="chips" id="skills">${skills.map((s, i) => `
    <span class="chip" title="importance ${s.weight}/4 — click the dots">${esc(s.name)}
      <span class="weight" data-w="${i}">${[1, 2, 3, 4].map(n => `<i class="${n <= s.weight ? "on" : ""}"></i>`).join("")}</span>
      <button type="button" data-rmskill="${i}" aria-label="remove">×</button></span>`).join("")}
    <input type="text" id="addskill" placeholder="+ add skill" style="width:140px;padding:4px 8px;border-radius:99px"></div>`;
}

async function renderProfile(el) {
  const p = await api("/api/profile");
  let skills = (p.matching?.skills || []).map(s => ({ ...s }));
  const c = p.candidate || {};
  const inp = (path, label, type = "text", hint = "") => `<label class="f">${label}${hint ? ` <span class="hint">${hint}</span>` : ""}<input type="${type}" data-path="${path}" value="${esc(getPath(p, path) ?? "")}"></label>`;
  const regions = p.search?.regions || [];
  const rng = (path, label, min, max, step, hint) => `<label class="f">${label} <span class="hint">${hint}</span>
    <div class="row" style="flex-wrap:nowrap"><input type="range" min="${min}" max="${max}" step="${step}" data-path="${path}" data-type="number" value="${getPath(p, path)}"><b style="width:36px;text-align:right" data-out="${path}">${getPath(p, path)}</b></div></label>`;

  el.innerHTML = `
  <div class="grid g2" style="align-items:start">
    <div class="stack" style="gap:16px">
      <section class="card pad">
        <div class="section-title"><span class="ic">${svg("file")}</span><h2>Resume</h2></div>
        <div class="drop" id="drop"><input type="file" id="file" accept=".pdf,.docx,.txt,.md" hidden>
          ${p.resume ? `<div><b>${esc(p.resume.name)}</b> <span class="muted small">${Math.round(p.resume.size / 1024)} KB</span></div><div class="small muted">Drop a new file or click to replace</div>`
                     : `<div><b>Drop your resume here</b> or click to choose</div><div class="small muted">PDF, DOCX or TXT</div>`}
        </div>
        <div class="row" style="margin-top:12px">
          <button class="btn soft" id="parse" data-busy="Claude is reading your resume…" ${p.resume ? "" : "disabled"}>${svg("spark", 15)}Fill profile from resume</button>
          ${p.resume ? `<a class="btn ghost sm" href="/api/resume/file" target="_blank">${svg("ext", 14)}View</a>` : ""}
        </div>
        <div class="small muted" style="margin-top:6px">Claude reads the resume and suggests your details, target titles and skills. Nothing is saved until you click Save.</div>
      </section>

      <section class="card pad">
        <div class="section-title"><span class="ic">${svg("user")}</span><h2>About you</h2></div>
        <div class="form">
          ${inp("candidate.first_name", "First name")}${inp("candidate.last_name", "Last name")}
          ${inp("candidate.email", "Email", "email")}${inp("candidate.phone", "Phone", "tel")}
          ${inp("candidate.city", "City")}${inp("candidate.country", "Country")}
          ${inp("candidate.current_title", "Current title")}${inp("candidate.current_company", "Current company")}
          ${inp("candidate.years_experience", "Years of experience", "number")}${inp("candidate.linkedin", "LinkedIn URL", "url")}
          ${inp("candidate.github", "GitHub URL", "url")}${inp("candidate.website", "Website / portfolio", "url")}
          <label class="f full">Summary <span class="hint">one line, used when Claude searches for jobs</span><textarea data-path="candidate.summary" style="min-height:56px">${esc(c.summary || "")}</textarea></label>
        </div>
      </section>

      <section class="card pad">
        <div class="section-title"><span class="ic">${svg("money")}</span><h2>Compensation &amp; availability</h2></div>
        <div class="form">
          ${inp("candidate.current_ctc", "Current salary / CTC", "text", "e.g. 45 LPA")}${inp("candidate.expected_ctc", "Expected salary / CTC", "text", "e.g. 60 LPA")}
          <label class="f">Currency<select data-path="candidate.currency">${["INR", "EUR", "GBP", "CAD", "AUD", "USD"].map(x => `<option ${c.currency === x ? "selected" : ""}>${x}</option>`).join("")}</select></label>
          ${inp("candidate.notice_period", "Notice period", "text", "e.g. 60 days")}
        </div>
        <div class="stack" style="margin-top:14px">
          <label class="switch"><input type="checkbox" data-path="candidate.requires_visa_sponsorship_abroad" data-type="bool" ${c.requires_visa_sponsorship_abroad ? "checked" : ""}><span class="track"></span>I need visa sponsorship for jobs abroad</label>
          <label class="switch"><input type="checkbox" data-path="candidate.willing_to_relocate" data-type="bool" ${c.willing_to_relocate ? "checked" : ""}><span class="track"></span>I'm willing to relocate</label>
          <label class="switch"><input type="checkbox" data-path="candidate.authorized_to_work_in_india" data-type="bool" ${c.authorized_to_work_in_india ? "checked" : ""}><span class="track"></span>I'm authorised to work in India</label>
        </div>
      </section>
    </div>

    <div class="stack" style="gap:16px">
      <section class="card pad">
        <div class="section-title"><span class="ic">${svg("pin")}</span><h2>Where &amp; what</h2></div>
        <label class="f">Regions</label>
        <div class="row" style="margin:6px 0 14px">${["india", "europe", "canada", "australia"].map(r => `<label class="chip" style="cursor:pointer"><input type="checkbox" data-region="${r}" ${regions.includes(r) ? "checked" : ""}> ${REGION[r]}</label>`).join("")}</div>
        <label class="f">Preferred Indian cities <span class="hint">other Indian cities still count</span></label>
        <div style="margin:6px 0 14px">${chipInput("cities", p.search?.india_preferred_cities, "Add city, press Enter")}</div>
        <label class="f">Target job titles</label>
        <div style="margin-top:6px">${chipInput("titles", c.target_titles, "Add title, press Enter")}</div>
      </section>

      <section class="card pad">
        <div class="section-title"><span class="ic">${svg("spark")}</span><h2>Skills</h2><span class="muted small" style="margin-left:auto">dots = importance</span></div>
        <div id="skillsbox">${skillsEditor(skills)}</div>
        <div class="small muted" style="margin-top:8px">Jobs that mention your heavier skills score higher.</div>
      </section>

      <section class="card pad">
        <div class="section-title"><span class="ic">${svg("check")}</span><h2>Matching rules</h2></div>
        <div class="stack" style="gap:14px">
          ${rng("matching.min_score", "Minimum match score", 30, 90, 1, "to show as a match")}
          ${rng("matching.strong_match_score", "Strong match score", 50, 95, 1, "needed for India roles that aren't WFH")}
          ${rng("company.min_rating", "Minimum company rating", 3, 4.5, 0.1, "Glassdoor-style")}
          ${rng("company.flexible_min_rating", "…but allow down to", 2.8, 4.5, 0.1, "for strong matches")}
          ${rng("search.max_age_days", "Ignore postings older than (days)", 7, 120, 1, "")}
        </div>
      </section>

      <section class="card pad">
        <div class="section-title"><span class="ic">${svg("send")}</span><h2>Applying</h2></div>
        <div class="choice" style="grid-template-columns:1fr 1fr">
          ${[["review", "Review first", "Forms are filled; you check and click Submit. Recommended."], ["auto", "Auto-submit", "Submits when every required field is filled and no CAPTCHA appears."]].map(([k, t, d]) =>
            `<label class="opt ${p.apply?.mode === k ? "on" : ""}"><h3><input type="radio" name="amode" value="${k}" ${p.apply?.mode === k ? "checked" : ""}> ${t}</h3><div class="small muted">${d}</div></label>`).join("")}
        </div>
        <div class="form" style="margin-top:12px">${inp("apply.max_per_day", "Max applications per day", "number")}</div>
      </section>
    </div>
  </div>
  <div class="savebar"><span class="muted small" id="dirty"></span><button class="btn" id="reset">Discard</button><button class="btn primary" id="save" data-busy="Saving…">${svg("check", 15)}Save profile</button></div>`;

  const markDirty = () => $("#dirty").textContent = "Unsaved changes";
  el.addEventListener("input", markDirty);
  $$("input[type=range]", el).forEach(r => r.addEventListener("input", () => $(`[data-out="${r.dataset.path}"]`).textContent = r.value));
  $$("input[name=amode]", el).forEach(r => r.onchange = () => { $$(".opt", el).forEach(o => o.classList.toggle("on", $("input", o).checked)); markDirty(); });
  bindChipInput($("#cities")); bindChipInput($("#titles"));

  const bindSkills = () => {
    $$("[data-w]").forEach(w => w.onclick = () => { const s = skills[+w.dataset.w]; s.weight = s.weight % 4 + 1; redrawSkills(); markDirty(); });
    $$("[data-rmskill]").forEach(b => b.onclick = () => { skills.splice(+b.dataset.rmskill, 1); redrawSkills(); markDirty(); });
    $("#addskill").onkeydown = e => { if (e.key === "Enter" && e.target.value.trim()) { e.preventDefault(); skills.push({ name: e.target.value.trim(), weight: 2 }); redrawSkills(); markDirty(); $("#addskill").focus(); } };
  };
  const redrawSkills = () => { $("#skillsbox").innerHTML = skillsEditor(skills); bindSkills(); };
  bindSkills();

  // resume upload
  const drop = $("#drop"), file = $("#file");
  drop.onclick = () => file.click();
  drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = e => { e.preventDefault(); drop.classList.remove("over"); if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); };
  file.onchange = () => file.files[0] && upload(file.files[0]);
  async function upload(f) {
    const fd = new FormData(); fd.append("file", f);
    drop.innerHTML = `<span class="spin"></span> Uploading…`;
    try { await api("/api/resume", { method: "POST", body: fd }); toast("Resume uploaded", "ok"); renderProfile(el); }
    catch (e) { toast(e.message, "err"); renderProfile(el); }
  }

  $("#parse").onclick = e => withBusy(e.currentTarget, async () => {
    const d = await api("/api/resume/parse", { method: "POST" });
    for (const k of ["first_name", "last_name", "email", "phone", "city", "country", "linkedin", "github", "current_company", "current_title", "years_experience", "summary"]) {
      const f = $(`[data-path="candidate.${k}"]`);
      if (f && d[k] !== undefined && d[k] !== "" && String(f.value) !== String(d[k])) { f.value = d[k]; f.classList.add("changed"); }
    }
    if (d.target_titles?.length) { const t = $("#titles"); t.dataset.values = JSON.stringify(d.target_titles); t.outerHTML = chipInput("titles", d.target_titles, "Add title, press Enter"); bindChipInput($("#titles")); }
    if (d.skills?.length) { skills = d.skills; redrawSkills(); }
    markDirty();
    toast("Profile filled from your resume — review the highlighted fields, then Save", "ok");
  });

  $("#reset").onclick = () => renderProfile(el);
  $("#save").onclick = e => withBusy(e.currentTarget, async () => {
    const out = {};
    $$("[data-path]", el).forEach(f => {
      let v = f.type === "checkbox" ? f.checked : f.value;
      if (f.dataset.type === "number" || f.type === "number") v = v === "" ? 0 : Number(v);
      setPath(out, f.dataset.path, v);
    });
    setPath(out, "search.regions", $$("[data-region]", el).filter(x => x.checked).map(x => x.dataset.region));
    setPath(out, "search.india_preferred_cities", JSON.parse($("#cities").dataset.values).map(x => x.toLowerCase()));
    setPath(out, "candidate.target_titles", JSON.parse($("#titles").dataset.values));
    setPath(out, "matching.skills", skills.map(s => ({ name: s.name, weight: s.weight, ...(s.pattern ? { pattern: s.pattern } : { aliases: s.aliases || [] }) })));
    setPath(out, "apply.mode", ($("input[name=amode]:checked", el) || {}).value || "review");
    await api("/api/profile", { method: "PUT", body: out });
    toast("Profile saved — re-matching your jobs", "ok");
    pollTask();
    renderProfile(el);
  });
}

// ------------------------------------------------------------------ SETTINGS
async function renderSettings(el) {
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
        ${[["use_claude_discovery", "Search the web for more jobs", "Finds postings beyond the built-in company boards"], ["use_claude_scoring", "Score my top matches", "Reads each job against your resume (up to 40 per search, plus every job Claude finds)"], ["use_claude_answers", "Draft answers on application forms", "Cover letters and free-text questions, from your resume only"]].map(([k, t, d]) =>
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

// ------------------------------------------------------------------ top bar: Claude pill, search task, apply queue
async function refreshClaudePill() {
  try {
    const cs = await api("/api/claude");
    const label = cs.mode === "off" ? "Claude off" : cs.ready
      ? (cs.mode === "account" ? `Claude ${cs.account.subscriptionType || "account"}` : "Claude API") : "Connect Claude";
    $("#claudepill").innerHTML = `<span class="dot ${cs.ready ? "ok" : "off"}"></span><span>${esc(label)}</span>`;
    $("#claudepill").className = `pill ${cs.ready ? "green" : "warn"}`;
  } catch { /* server restarting */ }
}

let taskTimer = null;
async function pollTask() {
  clearTimeout(taskTimer);
  let t;
  try { t = await api("/api/search"); } catch { taskTimer = setTimeout(pollTask, 5000); return; }
  const panel = $("#taskpanel"), btn = $("#findbtn");
  if (t.started && panel.dataset.started !== String(t.started)) {   // a new run (from here or the CLI)
    panel.dataset.started = String(t.started); delete panel.dataset.dismissed; delete panel.dataset.finished;
    if (!t.running && Date.now() / 1000 - t.started > 120) panel.dataset.dismissed = "1";  // old news on page load
  }
  btn.disabled = !!t.running;
  if (!t.started || panel.dataset.dismissed) { panel.hidden = true; }
  else {
    const done = !t.running;
    panel.hidden = false;
    panel.innerHTML = `
      <div class="row" style="flex-wrap:nowrap"><b style="flex:1">${t.kind === "rematch" ? "Re-matching jobs" : "Finding jobs"}${done ? (t.error ? " — failed" : " — done") : "…"}</b>
        ${done ? `<button class="btn ghost sm" id="tclose" aria-label="close">${svg("x", 14)}</button>` : `<span class="spin"></span>`}</div>
      <div class="progress ${!done && t.progress < 0.02 ? "indet" : ""}"><div style="width:${Math.round(t.progress * 100)}%"></div></div>
      ${t.error ? `<div style="color:var(--bad)" class="small">${esc(t.error)}</div>` : ""}
      ${t.result && t.result.decisions ? `<div class="small"><b>${t.result.decisions.apply || 0}</b> matches · ${t.result.decisions.review || 0} to review${t.result.new != null ? ` · ${t.result.new} new jobs` : ""}${t.result.claude_scored ? ` · ${t.result.claude_scored} scored by Claude` : ""}</div>
        ${(t.result.errors || []).length ? `<details class="small muted"><summary>${t.result.errors.length} source warnings</summary>${t.result.errors.map(esc).join("<br>")}</details>` : ""}` : ""}
      <div class="tasklog">${t.log.slice().reverse().map(l => `<div><span class="muted">${l.t}</span> ${esc(l.msg)}</div>`).join("")}</div>
      ${done && !t.error && t.kind !== "rematch" ? `<a class="btn sm primary" href="#/jobs" style="margin-top:8px" id="tsee">See matches</a>` : ""}`;
    const dismiss = () => { panel.hidden = true; panel.dataset.dismissed = "1"; };
    $("#tclose") && ($("#tclose").onclick = dismiss);
    $("#tsee") && ($("#tsee").onclick = dismiss);
    if (done && !panel.dataset.finished) {
      panel.dataset.finished = "1"; rerender();
      if (t.kind === "rematch") setTimeout(dismiss, 4000);
    }
  }
  taskTimer = setTimeout(pollTask, t.running ? 1500 : 6000);
}
$("#findbtn").onclick = async () => {
  try {
    await api("/api/search", { method: "POST", body: {} });
    pollTask();
  } catch (e) { toast(e.message, "err"); }
};

let applyTimer = null;
async function pollApply() {
  clearTimeout(applyTimer);
  const a = await api("/api/apply");
  const ind = $("#applyind");
  if (a.current || a.pending.length) {
    ind.hidden = false;
    ind.className = "pill warn";
    ind.innerHTML = `<span class="spin"></span> ${a.current ? `Filling: ${esc(a.current.company)}` : "Starting browser…"}${a.pending.length ? ` · ${a.pending.length} queued` : ""}`;
    applyTimer = setTimeout(pollApply, 2000);
  } else if (!ind.hidden) {
    ind.hidden = true; toast("Application queue finished — check the Applications board", "ok"); rerender();
  }
}

// ------------------------------------------------------------------ boot
route();
refreshClaudePill();
pollTask();
pollApply();
