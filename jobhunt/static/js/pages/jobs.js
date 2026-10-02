/* Jobs page: filters, the job list and bulk actions. */
import { $, $$, esc, REGION, STATUS_LABEL, STATUS_TONE, api, toast, svg } from "../core.js";
import { state } from "../router.js";
import { bindJobActions, queueApply } from "../jobactions.js";

// ------------------------------------------------------------------ JOBS
export async function renderJobs(el) {
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

export async function loadJobs() {
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

export function renderBulk() {
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
