"""What the app asks Claude to do: read the resume, find jobs on the web, score fit, draft answers.
Works with either backend (Claude account or API key) — see claude_backend.py."""

from __future__ import annotations

import logging

from .claude_backend import ClaudeError, ClaudeUsageLimit, backend
from .config import profile, resume_text
from .models import Job

log = logging.getLogger(__name__)


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or list(props), "additionalProperties": False}


STR, INT, BOOL = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}


def _arr(items: dict) -> dict:
    return {"type": "array", "items": items}


# ---------------------------------------------------------------- resume -> profile

RESUME_SCHEMA = _obj(
    {
        "first_name": STR,
        "last_name": STR,
        "email": STR,
        "phone": STR,
        "city": STR,
        "country": STR,
        "linkedin": STR,
        "github": STR,
        "current_company": STR,
        "current_title": STR,
        "years_experience": INT,
        "summary": STR,
        "target_titles": _arr(STR),
        "skills": _arr(_obj({"name": STR, "aliases": _arr(STR), "weight": INT})),
    }
)


def parse_resume(text: str) -> dict:
    system = (
        "You extract structured data from resumes. Use only what the resume states; leave a string "
        "empty if it isn't there."
    )
    prompt = (
        f"<resume>\n{text[:40000]}\n</resume>\n\n"
        "Extract the candidate's details. Also:\n"
        "- summary: one sentence, third person, about their level and focus.\n"
        "- target_titles: 4-6 job titles this person should search for, at their real seniority.\n"
        "- skills: 15-25 technologies/competencies a job posting might mention, each with common "
        "aliases as they'd appear in a job description (e.g. Go -> golang; AWS -> amazon web services), "
        "and weight 1-4 (4 = core strength, used heavily in recent roles; 1 = minor)."
    )
    return backend().structured(prompt, RESUME_SCHEMA, system)


# ---------------------------------------------------------------- job discovery (web search)

DISCOVERY_SCHEMA = _obj(
    {
        "jobs": _arr(
            _obj(
                {
                    "company": STR,
                    "title": STR,
                    "location": STR,
                    "url": STR,
                    "remote_policy": {"type": "string", "enum": ["remote", "hybrid", "onsite", "unknown"]},
                    "visa_sponsorship": {"type": "string", "enum": ["yes", "no", "unknown"]},
                    "posted": STR,
                    "summary": STR,
                    "employer_rating": {
                        "type": "number",
                        "description": "approx. Glassdoor rating 1-5, or 0 if unknown",
                    },
                }
            )
        )
    }
)

REGION_HINT = {
    "india": "in India (any city; prefer {cities}). Prefer remote / work-from-home roles.",
    "europe": "in Europe (incl. UK, Ireland, Germany, Netherlands, Nordics) that explicitly offer visa "
    "sponsorship or relocation support for non-EU candidates",
    "canada": "in Canada that explicitly offer visa sponsorship / relocation support",
    "australia": "in Australia that explicitly offer visa sponsorship (e.g. 482/TSS) or relocation",
}


def discover_jobs(region: str, limit: int) -> list[dict]:
    p = profile()
    c = p["candidate"]
    cities = ", ".join(sorted({x.title() for x in p["search"].get("india_preferred_cities", [])})[:6])
    skills = ", ".join(
        s["name"]
        for s in sorted(p["matching"].get("skills") or [], key=lambda s: -int(s.get("weight", 1)))[:10]
        if isinstance(s, dict)
    )
    titles = ", ".join(c.get("target_titles") or [c.get("current_title") or "Senior Software Engineer"])
    system = (
        "You are a meticulous job-search assistant. Use web search to find real job postings that are open "
        "now. Only return postings you actually saw, with the direct URL to the posting (prefer the "
        "company careers page or its Greenhouse/Lever/Ashby/Workday page over aggregators). Never invent "
        "postings, URLs or benefits."
    )
    prompt = (
        f"Find up to {limit} currently open job postings {REGION_HINT[region].format(cities=cities)}.\n"
        f"Candidate: {c.get('summary') or ''} {c.get('years_experience', '')} years of experience.\n"
        f"Target titles: {titles}\nKey skills: {skills}\n"
        "Prefer companies with a good employer reputation (Glassdoor ~3.5+). Skip staffing agencies, "
        "postings older than ~45 days, and roles clearly below the candidate's seniority.\n"
        "For each: company, title, location, url, remote_policy, visa_sponsorship (only 'yes' if the "
        "posting says so), posted (date if shown), summary (3-5 sentences: stack, scope, seniority, key "
        "requirements), employer_rating (the company's approximate Glassdoor rating if you know or "
        "find it, else 0). Keep the search focused: a handful of searches is enough."
    )
    return backend().structured(prompt, DISCOVERY_SCHEMA, system, web=True).get("jobs", [])


# ---------------------------------------------------------------- scoring

ASSESS_SCHEMA = _obj(
    {
        "score": INT,
        "seniority_fit": {"type": "string", "enum": ["under", "good", "over"]},
        "remote_policy": {"type": "string", "enum": ["remote", "hybrid", "onsite", "unknown"]},
        "visa_sponsorship": {"type": "string", "enum": ["yes", "no", "unknown"]},
        "strengths": _arr(STR),
        "gaps": _arr(STR),
    }
)

ASSESS_SYSTEM = """You are a strict technical recruiter screening roles for one candidate.
Score fit on 0-100: 85+ excellent, 70-84 strong, 55-69 plausible, below 55 weak. Weigh core stack,
seniority, domain, and hard requirements the candidate clearly lacks. Judge only from the posting
text; do not assume benefits it doesn't state. Strengths: up to 4 short phrases. Gaps: up to 3."""


def assess(job: Job) -> dict | None:
    prompt = (
        f"<resume>\n{resume_text()[:30000]}\n</resume>\n\n"
        f'<job company="{job.company}" location="{job.location}">\n'
        f"Title: {job.title}\n\n{job.description[:20000]}\n</job>"
    )
    try:
        return backend().structured(prompt, ASSESS_SCHEMA, ASSESS_SYSTEM)
    except ClaudeUsageLimit:
        raise  # the caller stops scoring; retrying the next job would fail the same way
    except ClaudeError as e:
        log.warning("assess failed for %s: %s", job.id, e)
        return None


# ---------------------------------------------------------------- application answers

ANSWER_SCHEMA = _obj({"answer": STR})


def draft_answer(job: Job, question: str, max_words: int = 150) -> str | None:
    c = profile()["candidate"]
    facts = (
        f"notice period: {c.get('notice_period')}; based in {c.get('city')}, {c.get('country')}; "
        f"expected compensation: {c.get('expected_ctc')} {c.get('currency', '')}; "
        f"needs visa sponsorship abroad: {c.get('requires_visa_sponsorship_abroad')}; "
        f"willing to relocate: {c.get('willing_to_relocate')}"
    )
    prompt = (
        f"<resume>\n{resume_text()[:30000]}\n</resume>\n<candidate_facts>{facts}</candidate_facts>\n"
        f'<job company="{job.company}">Title: {job.title}\n{job.description[:12000]}</job>\n\n'
        f"Question: {question}"
    )
    system = (
        f"Write the candidate's answer to a job-application question, first person, at most {max_words} "
        "words. Use only facts from the resume and candidate facts — never invent employers, numbers or "
        "skills."
    )
    try:
        return backend().structured(prompt, ANSWER_SCHEMA, system).get("answer") or None
    except ClaudeError as e:
        log.warning("draft failed: %s", e)
        return None


def cover_letter(job: Job) -> str | None:
    return draft_answer(job, "Write a short cover letter for this role (3 short paragraphs).", max_words=220)
