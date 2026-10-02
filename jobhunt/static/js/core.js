/* Shared helpers: DOM shortcuts, API calls, toasts, icons, labels, the confirm dialog and bar charts. */

// ------------------------------------------------------------------ helpers
export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];
export const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const fmtDate = s => s ? new Date(s).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "";
export const ago = s => {
  if (!s) return "";
  const d = (Date.now() - new Date(s).getTime()) / 1000;
  if (d < 90) return "just now";
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  if (d < 86400) return `${Math.round(d / 3600)}h ago`;
  return `${Math.round(d / 86400)}d ago`;
};
export const money = (v, cur) => {
  if (!v) return "";
  const n = Number(String(v).replace(/[, ]/g, ""));
  const txt = Number.isFinite(n) && n > 999 ? n.toLocaleString(cur === "INR" ? "en-IN" : undefined) : v;
  return `${txt} ${cur || ""}`.trim();
};
export const REGION = { india: "India", europe: "Europe", canada: "Canada", australia: "Australia", remote_global: "Remote (global)", other: "Other" };
export const STATUS_LABEL = {
  queued: "Queued", in_progress: "Filling form", needs_manual: "To finish", applied: "Applied", failed: "Failed",
  skipped: "Not interested", screening: "Screening", interviewing: "Interviewing", offer: "Offer",
  rejected: "Rejected", withdrawn: "Withdrawn",
};
export const STATUS_TONE = { applied: "green", screening: "info", interviewing: "info", offer: "green", rejected: "bad", failed: "bad", needs_manual: "warn", queued: "warn", in_progress: "warn" };

export async function api(path, opts = {}) {
  const o = { ...opts };
  if (o.body && !(o.body instanceof FormData)) { o.body = JSON.stringify(o.body); o.headers = { "Content-Type": "application/json" }; }
  let r;
  try { r = await fetch(path, o); } catch { throw new Error("Can't reach the jobhunt app. Is it still running?"); }
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new Error((data && data.detail) || r.statusText);
  return data;
}
export function toast(msg, kind = "") {
  const t = document.createElement("div");
  t.className = `toast ${kind}`; t.textContent = msg;
  $("#toasts").append(t);
  setTimeout(() => t.remove(), kind === "err" ? 7000 : 3800);
}
export async function withBusy(btn, fn) {
  const html = btn.innerHTML; btn.disabled = true; btn.innerHTML = `<span class="spin"></span> ${btn.dataset.busy || "Working…"}`;
  try { return await fn(); } catch (e) { toast(e.message, "err"); } finally { btn.disabled = false; btn.innerHTML = html; }
}
export const icon = {
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
export const svg = (n, w = 18) => `<svg viewBox="0 0 24 24" width="${w}" height="${w}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${icon[n]}</svg>`;

// ------------------------------------------------------------------ confirm dialog
// Resolves true for the main button, false for the other button, Esc or a click outside.
export function confirmDialog({ title, body, ok = "OK", cancel = "Cancel" }) {
  return new Promise(resolve => {
    const root = document.createElement("div");
    root.innerHTML = `<div class="scrim"></div>
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="mtitle">
        <h3 id="mtitle">${esc(title)}</h3>
        <p class="muted">${esc(body)}</p>
        <div class="row" style="justify-content:flex-end">
          <button class="btn" data-answer="no">${esc(cancel)}</button>
          <button class="btn primary" data-answer="yes">${esc(ok)}</button>
        </div>
      </div>`;
    const close = answer => { root.remove(); document.removeEventListener("keydown", onKey); resolve(answer); };
    const onKey = e => { if (e.key === "Escape") close(false); };
    $(".scrim", root).onclick = () => close(false);
    $$("[data-answer]", root).forEach(b => (b.onclick = () => close(b.dataset.answer === "yes")));
    document.addEventListener("keydown", onKey);
    document.body.append(root);
    $("[data-answer=yes]", root).focus();
  });
}

// ------------------------------------------------------------------ tooltip for charts
document.addEventListener("mousemove", e => {
  const t = e.target.closest("[data-tip]"), tip = $("#tip");
  if (!t) { tip.hidden = true; return; }
  tip.textContent = t.dataset.tip; tip.hidden = false;
  tip.style.left = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8) + "px"; tip.style.top = (e.clientY + 14) + "px";
});

export function barChart(rows, emptyText) {
  const max = Math.max(1, ...rows.map(r => r.value));
  if (!rows.some(r => r.value)) return `<div class="empty small">${emptyText}</div>`;
  return `<div class="bars" role="table">${rows.map(r => `
    <div class="bar" role="row" data-tip="${esc(r.label)}: ${r.value}${r.extra ? " · " + r.extra : ""}">
      <span class="lbl" role="cell">${esc(r.label)}</span>
      <span class="trk"><span class="fill" style="width:${(r.value / max) * 100}%"></span></span>
      <span class="num" role="cell">${r.value}</span>
    </div>`).join("")}</div>`;
}
