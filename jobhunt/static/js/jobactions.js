/* Actions shared by several pages: open a job in the side drawer, queue applications. */
import { $, $$, esc, fmtDate, REGION, STATUS_LABEL, STATUS_TONE, api, toast, withBusy, svg } from "./core.js";
import { state, rerender } from "./router.js";
import { pollApply } from "./topbar.js";

export function bindJobActions(el) {
  $$("[data-open]", el).forEach(n => n.addEventListener("click", e => { if (!e.target.closest("button,input,a")) openJob(n.dataset.open); }));
  $$("[data-apply]", el).forEach(b => b.addEventListener("click", e => { e.stopPropagation(); queueApply([b.dataset.apply]); }));
}

export async function queueApply(ids) {
  try {
    const r = await api("/api/apply", { method: "POST", body: { job_ids: ids } });
    const where = r.browser_view ? `the browser opens at ${r.browser_view}` : "a browser window will open";
    toast(`${r.added} application${r.added === 1 ? "" : "s"} queued — ${where}. Review each form and click Submit.`, "ok");
    pollApply();
    state.selected.clear();
    rerender();
  } catch (e) { toast(e.message, "err"); }
}

// ------------------------------------------------------------------ drawer (job detail)
export function closeDrawer() { $("#drawer-root").innerHTML = ""; }
document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrawer(); });

export async function openJob(id) {
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
