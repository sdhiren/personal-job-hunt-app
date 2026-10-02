/* Top bar: Claude connection pill, the job-search progress panel and the apply-queue indicator. */
import { $, esc, api, toast, svg } from "./core.js";
import { rerender } from "./router.js";

// ------------------------------------------------------------------ top bar: Claude pill, search task, apply queue
export async function refreshClaudePill() {
  try {
    const cs = await api("/api/claude");
    const label = cs.mode === "off" ? "Claude off" : cs.ready
      ? (cs.mode === "account" ? `Claude ${cs.account.subscriptionType || "account"}` : "Claude API") : "Connect Claude";
    $("#claudepill").innerHTML = `<span class="dot ${cs.ready ? "ok" : "off"}"></span><span>${esc(label)}</span>`;
    $("#claudepill").className = `pill ${cs.ready ? "green" : "warn"}`;
  } catch { /* server restarting */ }
}

let taskTimer = null;
export async function pollTask() {
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
      <div class="row" style="flex-wrap:nowrap"><b style="flex:1">Finding jobs${done ? (t.error ? " — failed" : " — done") : "…"}</b>
        ${done ? `<button class="btn ghost sm" id="tclose" aria-label="close">${svg("x", 14)}</button>` : `<span class="spin"></span>`}</div>
      <div class="progress ${!done && t.progress < 0.02 ? "indet" : ""}"><div style="width:${Math.round(t.progress * 100)}%"></div></div>
      ${t.error ? `<div style="color:var(--bad)" class="small">${esc(t.error)}</div>` : ""}
      ${t.result && t.result.claude_limit ? `<div class="limitnote" role="status"><b>Claude usage limit reached</b>
        <div>${esc(t.result.claude_limit.reason)}${t.result.claude_limit.resets ? ` · resets <b>${esc(t.result.claude_limit.resets)}</b>` : ""}</div>
        <div class="muted">Claude stopped for this search. Unscored jobs keep their keyword score and get Claude-scored on your next search after the reset.</div></div>` : ""}
      ${t.result && t.result.decisions ? `<div class="small"><b>${t.result.decisions.apply || 0}</b> matches · ${t.result.decisions.review || 0} to review${t.result.new != null ? ` · ${t.result.new} new jobs` : ""}${t.result.claude_scored ? ` · ${t.result.claude_scored} scored by Claude` : ""}</div>
        ${(t.result.errors || []).length ? `<details class="small muted"><summary>${t.result.errors.length} source warnings</summary>${t.result.errors.map(esc).join("<br>")}</details>` : ""}` : ""}
      <div class="tasklog">${t.log.slice().reverse().map(l => `<div><span class="muted">${l.t}</span> ${esc(l.msg)}</div>`).join("")}</div>
      ${done && !t.error ? `<a class="btn sm primary" href="#/jobs" style="margin-top:8px" id="tsee">See matches</a>` : ""}`;
    const dismiss = () => { panel.hidden = true; panel.dataset.dismissed = "1"; };
    $("#tclose") && ($("#tclose").onclick = dismiss);
    $("#tsee") && ($("#tsee").onclick = dismiss);
    if (done && !panel.dataset.finished) {
      panel.dataset.finished = "1"; rerender();
    }
  }
  taskTimer = setTimeout(pollTask, t.running ? 1500 : 6000);
}
export async function startSearch() {
  try {
    await api("/api/search", { method: "POST", body: {} });
    pollTask();
  } catch (e) { toast(e.message, "err"); }
}
$("#findbtn").onclick = startSearch;

let applyTimer = null;
export async function pollApply() {
  clearTimeout(applyTimer);
  const a = await api("/api/apply");
  const ind = $("#applyind");
  if (a.current || a.pending.length) {
    ind.hidden = false;
    ind.className = "pill warn";
    ind.innerHTML = `<span class="spin"></span> ${a.current ? `Filling: ${esc(a.current.company)}` : "Starting browser…"}${a.pending.length ? ` · ${a.pending.length} queued` : ""}${a.browser_view ? ` · <a href="${esc(a.browser_view)}" target="jobhunt-browser">open browser</a>` : ""}`;
    applyTimer = setTimeout(pollApply, 2000);
  } else if (!ind.hidden) {
    ind.hidden = true; toast("Application queue finished — check the Applications board", "ok"); rerender();
  }
}
