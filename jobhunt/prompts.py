"""Every prompt the app sends to Claude, in one place.

Each task is a `Prompt`: a version, a system prompt and the JSON schema of the answer, plus a function
that builds the user message. Bump a task's `version` whenever you change its wording or schema.
Claude scores are stored with the version that produced them, so after a scoring-prompt change the
outdated scores are redone on later searches (a few per search, like unscored jobs).

User messages are split into a `prefix` that is the same for every call in a run (the resume) and the
part that changes (the job). The API-key backend marks the prefix for prompt caching, so scoring 40
jobs sends the resume at full price once instead of 40 times.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Job

RESUME_CHARS = 30_000  # more than any real resume; keeps a pasted novel from blowing the context
JOB_CHARS = 20_000


@dataclass(frozen=True)
class Prompt:
    version: str
    system: str
    schema: dict


@dataclass(frozen=True)
class Message:
    prefix: str  # identical across calls in a run: cacheable
    body: str


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _arr(items: dict) -> dict:
    return {"type": "array", "items": items}


def _enum(*values: str) -> dict:
    return {"type": "string", "enum": list(values)}


STR, INT = {"type": "string"}, {"type": "integer"}


def _resume_block(resume: str) -> str:
    return f"<resume>\n{resume[:RESUME_CHARS]}\n</resume>"


def _job_block(job: Job, chars: int = JOB_CHARS) -> str:
    return (
        f'<job company="{job.company}" location="{job.location}">\n'
        f"Title: {job.title}\n\n{job.description[:chars]}\n</job>"
    )


# ---------------------------------------------------------------- resume -> profile

RESUME = Prompt(
    version="resume-v1",
    system="You extract structured data from resumes. Use only what the resume states; leave a string empty "
    "if it isn't there.",
    schema=_obj(
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
    ),
)


def resume_message(resume: str) -> Message:
    return Message(
        prefix=_resume_block(resume),
        body="Extract the candidate's details. Also:\n"
        "- summary: one sentence, third person, about their level and focus.\n"
        "- target_titles: 4-6 job titles this person should search for, at their real seniority.\n"
        "- skills: 15-25 technologies/competencies a job posting might mention, each with common aliases as "
        "they'd appear in a job description (e.g. Go -> golang; AWS -> amazon web services), and weight 1-4 "
        "(4 = core strength, used heavily in recent roles; 1 = minor).",
    )


# ---------------------------------------------------------------- job discovery (web search)

DISCOVERY = Prompt(
    version="discovery-v1",
    system="You are a meticulous job-search assistant. Use web search to find real job postings that are open "
    "now. Only return postings you actually saw, with the direct URL to the posting (prefer the company careers "
    "page or its Greenhouse/Lever/Ashby/Workday page over aggregators). Never invent postings, URLs or benefits.",
    schema=_obj(
        {
            "jobs": _arr(
                _obj(
                    {
                        "company": STR,
                        "title": STR,
                        "location": STR,
                        "url": STR,
                        "remote_policy": _enum("remote", "hybrid", "onsite", "unknown"),
                        "visa_sponsorship": _enum("yes", "no", "unknown"),
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
    ),
)

REGION_HINT = {
    "india": "in India (any city; prefer {cities}). Prefer remote / work-from-home roles.",
    "europe": "in Europe (incl. UK, Ireland, Germany, Netherlands, Nordics) that explicitly offer visa "
    "sponsorship or relocation support for non-EU candidates",
    "canada": "in Canada that explicitly offer visa sponsorship / relocation support",
    "australia": "in Australia that explicitly offer visa sponsorship (e.g. 482/TSS) or relocation",
}


def discovery_message(region: str, limit: int, profile: dict) -> Message:
    c = profile["candidate"]
    cities = ", ".join(sorted({x.title() for x in profile["search"].get("india_preferred_cities", [])})[:6])
    skills = sorted(
        (s for s in profile["matching"].get("skills") or [] if isinstance(s, dict)),
        key=lambda s: -int(s.get("weight", 1)),
    )
    titles = ", ".join(c.get("target_titles") or [c.get("current_title") or "Senior Software Engineer"])
    return Message(
        prefix="",  # web-search calls aren't cached: each region is a different request
        body=f"Find up to {limit} currently open job postings {REGION_HINT[region].format(cities=cities)}.\n"
        f"Candidate: {c.get('summary') or ''} {c.get('years_experience', '')} years of experience.\n"
        f"Target titles: {titles}\nKey skills: {', '.join(s['name'] for s in skills[:10])}\n"
        "Prefer companies with a good employer reputation (Glassdoor ~3.5+). Skip staffing agencies, postings "
        "older than ~45 days, and roles clearly below the candidate's seniority.\n"
        "For each: company, title, location, url, remote_policy, visa_sponsorship (only 'yes' if the posting "
        "says so), posted (date if shown), summary (3-5 sentences: stack, scope, seniority, key requirements), "
        "employer_rating (the company's approximate Glassdoor rating if you know or find it, else 0). Keep the "
        "search focused: a handful of searches is enough.",
    )


# ---------------------------------------------------------------- scoring

ASSESS = Prompt(
    version="assess-v1",
    system="You are a strict technical recruiter screening roles for one candidate.\n"
    "Score fit on 0-100: 85+ excellent, 70-84 strong, 55-69 plausible, below 55 weak. Weigh core stack, "
    "seniority, domain, and hard requirements the candidate clearly lacks. Judge only from the posting text; "
    "do not assume benefits it doesn't state. Strengths: up to 4 short phrases. Gaps: up to 3.",
    schema=_obj(
        {
            "score": INT,
            "seniority_fit": _enum("under", "good", "over"),
            "remote_policy": _enum("remote", "hybrid", "onsite", "unknown"),
            "visa_sponsorship": _enum("yes", "no", "unknown"),
            "strengths": _arr(STR),
            "gaps": _arr(STR),
        }
    ),
)
# Scores saved before versioning existed came from this same prompt
LEGACY_ASSESS_VERSION = "assess-v1"


def assess_message(resume: str, job: Job) -> Message:
    return Message(prefix=_resume_block(resume), body=_job_block(job))


# ---------------------------------------------------------------- application answers

ANSWER = Prompt(
    version="answer-v1",
    system="Write the candidate's answer to a job-application question, in the first person, within the word "
    "limit given. Use only facts from the resume and candidate facts — never invent employers, numbers or "
    "skills.",
    schema=_obj({"answer": STR}),
)


def answer_message(resume: str, candidate: dict, job: Job, question: str, max_words: int) -> Message:
    facts = (
        f"notice period: {candidate.get('notice_period')}; based in {candidate.get('city')}, "
        f"{candidate.get('country')}; expected compensation: {candidate.get('expected_ctc')} "
        f"{candidate.get('currency', '')}; needs visa sponsorship abroad: "
        f"{candidate.get('requires_visa_sponsorship_abroad')}; willing to relocate: "
        f"{candidate.get('willing_to_relocate')}"
    )
    return Message(
        prefix=f"{_resume_block(resume)}\n<candidate_facts>{facts}</candidate_facts>",
        body=f"{_job_block(job, chars=12_000)}\n\nQuestion: {question}\nWord limit: {max_words}",
    )
