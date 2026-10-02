/* Profile page: resume upload, personal details, skills and matching rules. */
import { $, $$, esc, money, REGION, api, toast, withBusy, svg, confirmDialog } from "../core.js";
import { startSearch } from "../topbar.js";

// ------------------------------------------------------------------ PROFILE
export const getPath = (o, p) => p.split(".").reduce((x, k) => x?.[k], o);
export function setPath(o, p, v) { const ks = p.split("."); let x = o; ks.slice(0, -1).forEach(k => x = x[k] ??= {}); x[ks.at(-1)] = v; }

export function chipInput(id, values, placeholder) {
  return `<div class="chipinput" id="${id}" data-values='${esc(JSON.stringify(values || []))}'>
    ${(values || []).map((v, i) => `<span class="chip">${esc(v)}<button type="button" data-rm="${i}" aria-label="remove">×</button></span>`).join("")}
    <input type="text" placeholder="${esc(placeholder)}"></div>`;
}
export function bindChipInput(box) {
  const vals = () => JSON.parse(box.dataset.values);
  const set = v => { box.dataset.values = JSON.stringify(v); box.outerHTML = chipInput(box.id, v, $("input", box).placeholder); bindChipInput($("#" + box.id)); };
  $$("[data-rm]", box).forEach(b => b.onclick = () => { const v = vals(); v.splice(+b.dataset.rm, 1); set(v); });
  const inp = $("input", box);
  inp.onkeydown = e => {
    if ((e.key === "Enter" || e.key === ",") && inp.value.trim()) { e.preventDefault(); const v = vals(); v.push(inp.value.trim()); set(v); $("#" + box.id + " input").focus(); }
    if (e.key === "Backspace" && !inp.value) { const v = vals(); v.pop(); set(v); $("#" + box.id + " input").focus(); }
  };
}

export function skillsEditor(skills) {
  return `<div class="chips" id="skills">${skills.map((s, i) => `
    <span class="chip" title="importance ${s.weight}/4 — click the dots">${esc(s.name)}
      <span class="weight" data-w="${i}">${[1, 2, 3, 4].map(n => `<i class="${n <= s.weight ? "on" : ""}"></i>`).join("")}</span>
      <button type="button" data-rmskill="${i}" aria-label="remove">×</button></span>`).join("")}
    <input type="text" id="addskill" placeholder="+ add skill" style="width:140px;padding:4px 8px;border-radius:99px"></div>`;
}

export async function renderProfile(el) {
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
    renderProfile(el);
    const search = await confirmDialog({
      title: "Profile saved",
      body: "Run a job search now? It finds new jobs and re-scores all your saved jobs against the updated profile. " +
        "Until then, saved jobs keep their current scores.",
      ok: "Run job search",
      cancel: "Not now",
    });
    if (search) startSearch();
  });
}
