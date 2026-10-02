"""Fill job applications in a real browser (Playwright) on Greenhouse, Lever and Ashby forms.

Safety rules baked in:
  * CAPTCHAs are never solved or bypassed — if one shows up, you finish that application yourself.
  * In `review` mode (default) nothing is submitted by the tool; you click Submit after checking.
  * In `auto` mode it submits only when every required field is filled; anything it can't answer
    (custom dropdowns, legal/EEO questions) drops back to review.
  * Sites that don't permit automation (LinkedIn, Naukri, Indeed) are never automated.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..config import BROWSER_PROFILE_DIR, SCREENSHOT_DIR, ensure_dirs, profile, resume_path
from ..models import Job

log = logging.getLogger(__name__)

CONFIRM_RE = re.compile(
    r"thank(s| you) for (applying|your application|your interest)|application (has been |was )?"
    r"(submitted|received|sent)|we('ve| have) received your application|successfully (applied|submitted)",
    re.I,
)
CAPTCHA_FRAME_RE = re.compile(
    r"recaptcha/.*/bframe|hcaptcha\.com/.*(challenge|checkbox)|challenges\.cloudflare\.com", re.I
)

COLLECT_JS = r"""
() => {
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return (r.width > 0 && r.height > 0 && s.visibility !== 'hidden') || el.type === 'file'; };
  const labelOf = el => {
    const parts = [];
    if (el.labels) for (const l of el.labels) parts.push(l.innerText);
    const lb = el.getAttribute('aria-labelledby');
    if (lb) lb.split(/\s+/).forEach(id => { const n = document.getElementById(id); if (n) parts.push(n.innerText); });
    parts.push(el.getAttribute('aria-label') || '', el.placeholder || '', el.name || '', el.id || '');
    if (parts.join('').trim().length < 3) {
      const box = el.closest('div,fieldset,li'); if (box) parts.push((box.innerText || '').slice(0, 200));
    }
    return parts.join(' | ').replace(/\s+/g, ' ').trim();
  };
  const out = [];
  document.querySelectorAll('input, textarea, select').forEach((el, i) => {
    const t = (el.type || '').toLowerCase();
    if (['hidden','submit','button','reset','image','search'].includes(t) || el.disabled || !vis(el)) return;
    el.setAttribute('data-jh', String(i));
    const label = labelOf(el);
    const required = el.required || el.getAttribute('aria-required') === 'true' || /\*/.test(label);
    let empty = !el.value;
    if (t === 'checkbox' || t === 'radio') {
      const grp = el.name ? document.querySelectorAll(`input[name="${CSS.escape(el.name)}"]`) : [el];
      empty = ![...grp].some(x => x.checked);
    }
    if (t === 'file') empty = !(el.files && el.files.length);
    out.push({idx: String(i), tag: el.tagName.toLowerCase(), type: t, label, required, empty,
              options: el.tagName === 'SELECT' ? [...el.options].map(o => o.text) : null});
  });
  return out;
}
"""


@dataclass
class ApplyResult:
    status: str  # applied | needs_manual | skipped | failed
    note: str = ""
    answers: dict = field(default_factory=dict)
    cover_letter: str | None = None
    screenshot: str | None = None


def _field_values(job: Job, abroad: bool) -> list[tuple[str, str]]:
    c = profile()["candidate"]
    full = f"{c['first_name']} {c['last_name']}"
    pairs = [
        (r"first[ _-]?name|given name|_systemfield_first", c["first_name"]),
        (r"last[ _-]?name|surname|family name|_systemfield_last", c["last_name"]),
        (r"^(full )?name\b|\bfull name|_systemfield_name|^name \|", full),
        (r"e-?mail", c["email"]),
        (r"phone|mobile|contact number", c["phone"]),
        (r"linkedin", c.get("linkedin", "")),
        (r"github", c.get("github", "")),
        (r"website|portfolio|personal (site|url)", c.get("website", "")),
        (
            r"current (company|employer)|^org\b|\| org \||company name|most recent (company|employer)",
            c.get("current_company", ""),
        ),
        (r"current (job )?title|current (role|position)", c.get("current_title", "")),
        (r"years of (professional |relevant )?experience|how many years", str(c.get("years_experience", ""))),
        (r"notice period", c.get("notice_period", "")),
        (r"current (ctc|salary|compensation)", c.get("current_ctc", "")),
        (
            r"expected (ctc|salary|compensation)|salary expectation|desired (salary|compensation)",
            c.get("expected_ctc", ""),
        ),
        (
            r"\b(current )?location\b|\bcity\b|where are you (currently )?(based|located)",
            f"{c['city']}, {c['country']}",
        ),
    ]
    return [(p, v) for p, v in pairs if v]


def _yes_no_for(label: str, abroad: bool) -> str | None:
    c = profile()["candidate"]
    text = label.lower()
    if re.search(r"(require|need).{0,40}(sponsor|visa)|sponsorship", text):
        return "yes" if (abroad and c.get("requires_visa_sponsorship_abroad")) else "no"
    if re.search(r"(legally )?(authori[sz]ed|eligible|right) to work", text):
        if "india" in text:
            return "yes" if c.get("authorized_to_work_in_india") else None
        return "no" if abroad else None
    if re.search(r"willing to relocate|open to relocat", text):
        return "yes" if c.get("willing_to_relocate") else "no"
    return None


def _pick_option(options: list[str], want: str) -> str | None:
    for o in options:
        if re.match(rf"\s*{want}\b", o, re.I):
            return o
    return None


def _confirmed(page) -> bool:
    try:
        if re.search(r"confirm|thank|success|submitted", page.url, re.I):
            return True
        return bool(CONFIRM_RE.search(page.inner_text("body", timeout=3000)))
    except Exception:
        return False


def _captcha_visible(page) -> bool:
    for fr in page.frames:
        if CAPTCHA_FRAME_RE.search(fr.url or ""):
            try:
                el = fr.frame_element()
                box = el.bounding_box()
                if box and box["width"] > 50 and box["height"] > 50 and el.is_visible():
                    return True
            except Exception:
                continue
    return False


def _shot(page, job: Job, tag: str) -> str | None:
    ensure_dirs()
    path = SCREENSHOT_DIR / f"{re.sub(r'[^a-z0-9]+', '_', job.id)}_{tag}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        return str(path)
    except Exception:
        return None


def _open_form(page, job: Job) -> None:
    page.goto(job.apply_url or job.url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    # Some boards show the description first with an "Apply" button
    for sel in [
        "a:has-text('Apply for this job')",
        "button:has-text('Apply for this job')",
        "button:has-text('Apply now')",
        "a:has-text('Apply now')",
        "button:has-text('Apply')",
    ]:
        loc = page.locator(sel).first
        try:
            if loc.is_visible(timeout=500) and not page.locator("input[type=file]").count():
                loc.click()
                page.wait_for_timeout(2000)
                break
        except Exception:
            continue


def _fill(page, job: Job, abroad: bool, use_llm: bool) -> tuple[dict, str | None, list[str]]:
    """Fill what we can. Returns (answers, cover_letter, unfilled_required_labels)."""
    answers: dict[str, str] = {}
    cover: str | None = None
    rules = _field_values(job, abroad)
    resume = str(resume_path())
    fields = page.evaluate(COLLECT_JS)

    for f in fields:
        loc = page.locator(f'[data-jh="{f["idx"]}"]')
        label = f["label"]
        key = label.split(" | ")[0][:80] or label[:80]
        try:
            if f["type"] == "file":
                if re.search(r"resume|cv\b|curriculum", label, re.I) or not answers.get("_resume"):
                    if not re.search(r"cover", label, re.I):
                        loc.set_input_files(resume)
                        answers["_resume"] = Path(resume).name
                continue
            if not f["empty"]:
                continue
            if f["tag"] == "select":
                yn = _yes_no_for(label, abroad)
                opt = _pick_option(f["options"] or [], yn) if yn else None
                if opt:
                    loc.select_option(label=opt)
                    answers[key] = opt
                continue
            if f["type"] in ("checkbox", "radio"):
                continue  # consent / EEO / custom choices: left for you
            if f["tag"] == "textarea" and re.search(
                r"cover letter|additional information|anything else|comments", label, re.I
            ):
                if use_llm:
                    from .. import llm

                    cover = cover or llm.cover_letter(job)
                    if cover:
                        loc.fill(cover)
                continue
            value = next((v for p, v in rules if re.search(p, label, re.I)), None)
            if value is None and f["tag"] == "textarea" and f["required"] and use_llm:
                from .. import llm

                question = label.split(" | ")[0][:300]
                value = llm.draft_answer(job, question)
            if value:
                loc.fill(value)
                answers[key] = value
        except Exception as e:
            log.debug("could not fill %s: %s", label, e)

    page.wait_for_timeout(800)
    after = page.evaluate(COLLECT_JS)
    missing = [f["label"].split(" | ")[0][:80] for f in after if f["required"] and f["empty"]]
    return answers, cover, missing


def _submit(page) -> bool:
    for sel in [
        "button[type=submit]",
        "input[type=submit]",
        "button:has-text('Submit application')",
        "button:has-text('Submit Application')",
        "button:has-text('Submit')",
    ]:
        loc = page.locator(sel).last
        try:
            if loc.is_visible(timeout=500):
                loc.click()
                return True
        except Exception:
            continue
    return False


def _wait_for_user(page, timeout_s: int) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if page.is_closed():
            return False
        if _confirmed(page):
            return True
        time.sleep(2)
    return False


class Applier:
    def __init__(self, mode: str | None = None, use_llm: bool | None = None, review_timeout: int = 900):
        cfg = profile()["apply"]
        self.mode = mode or cfg["mode"]
        if use_llm is None:
            from ..claude_backend import status
            from ..config import settings

            use_llm = bool(settings().get("use_claude_answers")) and status()["ready"]
        self.use_llm = use_llm
        self.headless = cfg.get("headless", False) and self.mode == "auto"
        self.review_timeout = review_timeout
        self._pw = self._ctx = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        ensure_dirs()
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            str(BROWSER_PROFILE_DIR), headless=self.headless, viewport={"width": 1280, "height": 900}
        )
        return self

    def __exit__(self, *exc):
        if self._ctx:
            self._ctx.close()
        if self._pw:
            self._pw.stop()

    def apply(self, job: Job, abroad: bool, ask=None) -> ApplyResult:
        """`ask(prompt) -> str` asks you (terminal) what happened when it can't tell.
        With ask=None (the desktop app) it waits for the confirmation page, else returns needs_manual."""
        page = self._ctx.new_page()
        try:
            _open_form(page, job)
            if job.ats not in ("greenhouse", "lever", "ashby"):
                return self._manual(page, job, ask, "not a supported ATS form — apply in the opened tab")

            answers, cover, missing = _fill(page, job, abroad, self.use_llm)
            shot = _shot(page, job, "filled")

            if self.mode == "auto" and not missing and not _captcha_visible(page):
                if _submit(page):
                    page.wait_for_timeout(5000)
                    if _confirmed(page):
                        return ApplyResult("applied", "auto-submitted", answers, cover, _shot(page, job, "done"))
                    if _captcha_visible(page):
                        log.info("CAPTCHA appeared — handing over to you")
            note = ("needs your input: " + "; ".join(missing[:6])) if missing else "please review and submit"
            res = self._manual(page, job, ask, note)
            res.answers, res.cover_letter, res.screenshot = answers, cover, res.screenshot or shot
            return res
        except Exception as e:
            return ApplyResult("failed", f"{type(e).__name__}: {e}"[:500], screenshot=_shot(page, job, "error"))
        finally:
            if not page.is_closed():
                page.close()

    def _manual(self, page, job: Job, ask, note: str) -> ApplyResult:
        if ask is None:
            if _wait_for_user(page, self.review_timeout):
                return ApplyResult(
                    "applied", "submitted by you (confirmation detected)", screenshot=_shot(page, job, "done")
                )
            return ApplyResult("needs_manual", f"{note} — no confirmation seen; mark it in the app")
        ask(
            f"[browser] {job.company} — {job.title}: {note}. "
            f"Submit in the browser (I'll detect it), or close the tab to skip. Press Enter to start waiting."
        )
        if _wait_for_user(page, self.review_timeout):
            return ApplyResult(
                "applied", "submitted by you (confirmation detected)", screenshot=_shot(page, job, "done")
            )
        answer = ask("Didn't see a confirmation page. Did you submit it? [y]es / [n]o-skip / [l]ater").strip().lower()
        if answer.startswith("y"):
            return ApplyResult("applied", "marked applied by you")
        if answer.startswith("l"):
            return ApplyResult("needs_manual", note)
        return ApplyResult("skipped", "skipped by you")
