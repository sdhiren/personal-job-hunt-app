/* Dashboard page: profile summary, stats, pipeline chart, top matches, recent activity. */
import { esc, ago, money, REGION, STATUS_LABEL, api, svg, barChart } from "../core.js";
import { state, renderNav } from "../router.js";
import { bindJobActions } from "../jobactions.js";

// ------------------------------------------------------------------ DASHBOARD
export async function renderDashboard(el) {
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
