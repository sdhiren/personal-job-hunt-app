/* Hash router: maps #/page to a page module and renders the sidebar. */
import { $, esc, svg } from "./core.js";
import { renderDashboard } from "./pages/dashboard.js";
import { closeDrawer } from "./jobactions.js";
import { renderJobs } from "./pages/jobs.js";
import { renderApplications } from "./pages/applications.js";
import { renderProfile } from "./pages/profile.js";
import { renderSettings } from "./pages/settings.js";

// ------------------------------------------------------------------ router
export const ROUTES = {
  dashboard: { title: "Dashboard", icon: "home", render: renderDashboard },
  jobs: { title: "Jobs", icon: "jobs", render: renderJobs },
  applications: { title: "Applications", icon: "apps", render: renderApplications },
  profile: { title: "My profile", icon: "user", render: renderProfile },
  settings: { title: "Settings", icon: "gear", render: renderSettings },
};
export const state = { jobsFilter: { decision: "apply", region: "", q: "", wfh: false }, selected: new Set(), counts: {} };

export function route() {
  const name = (location.hash.replace(/^#\//, "").split("?")[0]) || "dashboard";
  const r = ROUTES[name] || ROUTES.dashboard;
  $("#title").textContent = r.title;
  renderNav();
  closeDrawer();
  window.scrollTo(0, 0);
  renderPage(r);
}
// A page whose data fails to load shows the reason (e.g. the database is down) instead of spinning forever
export function renderPage(r) {
  // A fresh container per render, so event listeners a page put on it don't leak into the next page
  const old = $("#page");
  const el = old.cloneNode(false);
  old.replaceWith(el);
  Promise.resolve().then(() => r.render(el)).catch(e => {
    el.innerHTML = `<div class="empty"><b>Couldn't load this page.</b><div class="small muted" style="white-space:pre-line;margin-top:8px">${esc(e.message)}</div></div>`;
  });
}
export function renderNav() {
  const name = (location.hash.replace(/^#\//, "").split("?")[0]) || "dashboard";
  const cur = ROUTES[name] || ROUTES.dashboard;
  const badge = n => n ? `<span class="count">${n}</span>` : "";
  $("#nav").innerHTML = Object.entries(ROUTES).map(([k, v]) =>
    `<a href="#/${k}" class="${cur === v ? "on" : ""}">${svg(v.icon)}${v.title}${k === "jobs" ? badge(state.counts.matches) : ""}${k === "applications" ? badge(state.counts.todo) : ""}</a>`).join("");
}
export function rerender() {
  const n = location.hash.replace(/^#\//, "") || "dashboard";
  renderPage(ROUTES[n] || ROUTES.dashboard);
}
