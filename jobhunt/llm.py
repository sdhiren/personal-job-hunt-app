"""What the app asks Claude to do: read the resume, find jobs on the web, score fit, draft answers.

The prompts themselves live in prompts.py; this module sends them through whichever backend is set up
(Claude account or API key, see claude_backend.py) and handles failures.
"""

from __future__ import annotations

import logging

from . import prompts
from .claude_backend import ClaudeError, ClaudeUsageLimit, backend
from .config import profile, resume_text
from .models import Job

log = logging.getLogger(__name__)
REGION_HINT = prompts.REGION_HINT  # regions Claude can search


def _ask(prompt: prompts.Prompt, message: prompts.Message, web: bool = False) -> dict:
    return backend().structured(
        message.body, prompt.schema, prompt.system, web=web, cache_prefix=message.prefix or None
    )


def parse_resume(text: str) -> dict:
    return _ask(prompts.RESUME, prompts.resume_message(text))


def discover_jobs(region: str, limit: int) -> list[dict]:
    return _ask(prompts.DISCOVERY, prompts.discovery_message(region, limit, profile()), web=True).get("jobs", [])


def assess(job: Job) -> dict | None:
    """Claude's fit score for one job, tagged with the prompt version; None if Claude couldn't score it."""
    try:
        result = _ask(prompts.ASSESS, prompts.assess_message(resume_text(), job))
    except ClaudeUsageLimit:
        raise  # the caller stops scoring; retrying the next job would fail the same way
    except ClaudeError as e:
        log.warning("assess failed for %s: %s", job.id, e)
        return None
    return {**result, "prompt_version": prompts.ASSESS.version}


def draft_answer(job: Job, question: str, max_words: int = 150) -> str | None:
    message = prompts.answer_message(resume_text(), profile()["candidate"], job, question, max_words)
    try:
        return _ask(prompts.ANSWER, message).get("answer") or None
    except ClaudeUsageLimit:
        raise  # the form filler stops drafting for the rest of the run
    except ClaudeError as e:
        log.warning("draft failed: %s", e)
        return None


def cover_letter(job: Job) -> str | None:
    return draft_answer(job, "Write a short cover letter for this role (3 short paragraphs).", max_words=220)
