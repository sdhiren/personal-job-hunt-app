/* Applications page: the Kanban board. */
import { $$, esc, fmtDate, STATUS_LABEL, STATUS_TONE, api, svg } from "../core.js";
import { state, renderNav } from "../router.js";
import { queueApply, openJob } from "../jobactions.js";

// ------------------------------------------------------------------ APPLICATIONS (kanban)
export const COLUMNS = [
  { key: "todo", title: "To do", statuses: ["queued", "in_progress", "needs_manual", "failed"], drop: "needs_manual" },
  { key: "applied", title: "Applied", statuses: ["applied"], drop: "applied" },
  { key: "screening", title: "Screening", statuses: ["screening"], drop: "screening" },
  { key: "interviewing", title: "Interviewing", statuses: ["interviewing"], drop: "interviewing" },
  { key: "offer", title: "Offer", statuses: ["offer"], drop: "offer" },
  { key: "closed", title: "Closed", statuses: ["rejected", "withdrawn", "skipped"], drop: "rejected" },
];

export async function renderApplications(el) {
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
