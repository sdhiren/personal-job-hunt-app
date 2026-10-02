"""Prompts are split into a cacheable prefix (the resume) and a per-call body (the job)."""

import json
from types import SimpleNamespace

from jobhunt import llm, prompts
from jobhunt.claude_backend import ApiBackend
from jobhunt.models import Job

JOB = Job(
    source="t",
    external_id="1",
    company="Acme",
    title="Staff Engineer",
    location="Pune",
    url="",
    description="Go and AWS.",
)


def test_assess_message_keeps_resume_in_the_prefix_and_job_in_the_body():
    m = prompts.assess_message("RESUME TEXT", JOB)
    assert "RESUME TEXT" in m.prefix and "Acme" not in m.prefix
    assert "Staff Engineer" in m.body and "RESUME TEXT" not in m.body


def test_answer_prompt_is_identical_across_questions():
    a = prompts.answer_message("R", {}, JOB, "Why us?", 150)
    b = prompts.answer_message("R", {}, JOB, "Cover letter", 220)
    assert a.prefix == b.prefix  # same cache entry for every answer in a run
    assert "Word limit: 150" in a.body and "Word limit: 220" in b.body


def test_every_schema_is_strict():
    for p in (prompts.RESUME, prompts.DISCOVERY, prompts.ASSESS, prompts.ANSWER):
        assert p.schema["additionalProperties"] is False
        assert set(p.schema["required"]) == set(p.schema["properties"])


def test_assess_tags_result_with_prompt_version(monkeypatch):
    class Fake:
        def structured(self, prompt, schema, system, web=False, cache_prefix=None):
            assert cache_prefix and "<resume>" in cache_prefix
            return {"score": 80, "strengths": [], "gaps": []}

    monkeypatch.setattr(llm, "backend", Fake)
    monkeypatch.setattr(llm, "resume_text", lambda: "resume")
    assert llm.assess(JOB)["prompt_version"] == prompts.ASSESS.version


def test_api_backend_marks_the_prefix_for_caching():
    sent = {}

    def create(**kwargs):
        sent.update(kwargs)
        return SimpleNamespace(
            stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps({"ok": 1}))]
        )

    b = ApiBackend.__new__(ApiBackend)  # skip the real client
    b.model = "claude-opus-5"
    b.client = SimpleNamespace(messages=SimpleNamespace(create=create))
    assert b.structured("job text", {}, "system", cache_prefix="resume text") == {"ok": 1}
    first, second = sent["messages"][0]["content"]
    assert first == {"type": "text", "text": "resume text", "cache_control": {"type": "ephemeral"}}
    assert second == {"type": "text", "text": "job text"}
