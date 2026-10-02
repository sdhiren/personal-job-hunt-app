"""The pipeline (fetch → discover with Claude → evaluate → Claude scoring), shared by the CLI and the app."""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import logging
import re
from collections.abc import Callable

from . import db
from .claude_backend import ClaudeError
from .claude_backend import status as claude_status
from .config import profile, settings
from .matching import evaluate
from .models import Job

log = logging.getLogger(__name__)
Progress = Callable[[str, float | None], None]


def _noop(msg: str, pct: float | None = None) -> None:
    log.info(msg)


# ---------------------------------------------------------------- Claude discovery

ATS_URL = [
    (re.compile(r"greenhouse\.io/(?:embed/job_app\?for=)?([\w-]+)/jobs/(\d+)"), "greenhouse"),
    (re.compile(r"jobs\.lever\.co/([\w-]+)/([0-9a-f-]{36})"), "lever"),
    (re.compile(r"jobs\.ashbyhq\.com/([\w.-]+)/([0-9a-f-]{36})"), "ashby"),
]


def _ats_from_url(url: str) -> tuple[str | None, str | None, str | None, str | None]:
    for rx, ats in ATS_URL:
        m = rx.search(url)
        if m:
            slug, jid = m.group(1), m.group(2)
            apply_url = {
                "greenhouse": f"https://job-boards.greenhouse.io/{slug}/jobs/{jid}",
                "lever": f"https://jobs.lever.co/{slug}/{jid}/apply",
                "ashby": f"https://jobs.ashbyhq.com/{slug}/{jid}/application",
            }[ats]
            return ats, slug, jid, apply_url
    return None, None, None, None


def discover(progress: Progress = _noop) -> tuple[list[Job], list[str]]:
    from . import llm

    regions = [r for r in profile()["search"]["regions"] if r in llm.REGION_HINT]
    per = int(settings().get("discovery_per_region", 12))
    jobs, errors = [], []

    def one(region):
        return region, llm.discover_jobs(region, per)

    progress(f"Claude is searching the web for jobs in {', '.join(regions)}…", None)
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(one, r) for r in regions]
        for f in cf.as_completed(futures):
            try:
                region, found = f.result()
            except ClaudeError as e:
                errors.append(f"Claude discovery: {e}")
                continue
            progress(f"Claude found {len(found)} jobs in {region}", None)
            for j in found:
                url = (j.get("url") or "").strip()
                if not url.startswith("http"):
                    continue
                ats, slug, jid, apply_url = _ats_from_url(url)
                visa = j.get("visa_sponsorship")
                desc = j.get("summary", "")
                if visa == "yes":
                    desc += "\nVisa sponsorship is available."  # so the rule-based visa check sees it
                jobs.append(
                    Job(
                        source="claude",
                        external_id=jid or hashlib.sha1(url.encode()).hexdigest()[:16],
                        company=j.get("company", ""),
                        title=j.get("title", ""),
                        location=j.get("location", ""),
                        url=url,
                        apply_url=apply_url or url,
                        description=desc,
                        remote=True if j.get("remote_policy") == "remote" else None,
                        workplace=j.get("remote_policy") if j.get("remote_policy") != "unknown" else None,
                        ats=ats,
                        ats_slug=slug,
                        extra={
                            "posted": j.get("posted"),
                            "visa_sponsorship": visa == "yes",
                            "region_hint": region,
                            "rating": j.get("employer_rating") or None,
                        },
                    )
                )
    return jobs, errors


# ---------------------------------------------------------------- evaluation


def _eval(job: Job, a: dict | None):
    if not a:
        return evaluate(job)
    notes = [f"+ {s}" for s in a.get("strengths", [])[:3]] + [f"- {g}" for g in a.get("gaps", [])[:2]]
    return evaluate(
        job,
        llm_score=a["score"],
        llm_notes=notes,
        llm_visa=a.get("visa_sponsorship"),
        llm_remote=a.get("remote_policy"),
    )


def evaluate_all(conn, progress: Progress = _noop) -> None:
    rows = conn.execute("SELECT * FROM jobs").fetchall()
    for i, r in enumerate(rows):
        if i % 500 == 0:
            conn.commit()  # short transactions keep the app responsive
        if i % 1000 == 0:
            progress(f"Matching jobs to your profile… {i}/{len(rows)}", 0.5 + 0.3 * i / max(1, len(rows)))
        job = db.row_to_job(r)
        db.save_evaluation(conn, job.id, _eval(job, json.loads(r["llm_json"]) if r["llm_json"] else None))
    mark_duplicates(conn)
    conn.commit()


def claude_score(conn, progress: Progress = _noop, limit: int = 40) -> int:
    """Have Claude re-score the best not-yet-scored candidates (costs quota/tokens, so capped)."""
    from . import llm

    prefilter = profile()["matching"].get("llm_prefilter_score", 45)
    hard_reject = ("title not a fit", "location out of scope", "posting too old", "JD says no", "duplicate")
    # Claude-discovered jobs only have a short summary, so keyword scores undersell them: always score those
    rows = conn.execute(
        "SELECT * FROM jobs WHERE llm_json IS NULL AND ((decision IN ('apply','review') AND kw_score >= ?) "
        "OR source='claude') ORDER BY source='claude' DESC, kw_score DESC",
        (prefilter,),
    ).fetchall()
    rows = [r for r in rows if not json.loads(r["reasons"] or '[""]')[0].startswith(hard_reject)][:limit]
    done = 0

    def one(r):
        job = db.row_to_job(r)
        return job, llm.assess(job)

    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        for job, a in ex.map(one, rows):
            done += 1
            pct = 0.8 + 0.2 * done / max(1, len(rows))
            progress(f"Claude scored {done}/{len(rows)}: {job.company} — {job.title}", pct)
            if a:
                db.save_evaluation(conn, job.id, _eval(job, a), json.dumps(a))
                conn.commit()
    mark_duplicates(conn)
    conn.commit()
    return done


def mark_duplicates(conn) -> None:
    """Same company + title + region posted several times (multi-city reposts): keep the best one."""
    rows = conn.execute(
        "SELECT id, company, title, region, reasons FROM jobs WHERE decision IN ('apply','review') "
        "ORDER BY score DESC, posted_at DESC"
    ).fetchall()
    seen = set()
    for r in rows:
        key = (r["company"].lower().strip(), " ".join(r["title"].lower().split()), r["region"])
        if key in seen:
            reasons = ["duplicate posting", *json.loads(r["reasons"] or "[]")]
            conn.execute("UPDATE jobs SET decision='reject', reasons=? WHERE id=?", (json.dumps(reasons), r["id"]))
        seen.add(key)


# ---------------------------------------------------------------- full run


def run_search(progress: Progress = _noop, sources: list[str] | None = None, use_claude: bool | None = None) -> dict:
    from .sources import fetch_all

    st = settings()
    claude_ok = claude_status()["ready"] if use_claude is not False else False
    sources = sources or [k for k, on in st["sources"].items() if on]
    errors: list[str] = []

    progress("Fetching jobs from company career boards…", 0.05)
    jobs, errs = fetch_all(sources)
    errors += errs
    progress(f"Fetched {len(jobs)} jobs from {len(sources)} sources", 0.35)

    if claude_ok and st.get("use_claude_discovery"):
        found, errs = discover(progress)
        jobs += found
        errors += errs

    with db.connect() as conn:
        new, updated = db.upsert_jobs(conn, jobs)
        conn.commit()
        progress(f"Saved: {new} new, {updated} updated", 0.5)
        evaluate_all(conn, progress)
        scored = 0
        if claude_ok and st.get("use_claude_scoring"):
            scored = claude_score(conn, progress)
        counts = dict(conn.execute("SELECT decision, COUNT(*) FROM jobs GROUP BY decision").fetchall())
    summary = {
        "fetched": len(jobs),
        "new": new,
        "claude_scored": scored,
        "decisions": counts,
        "errors": errors[:20],
        "claude_used": claude_ok,
    }
    progress(f"Done — {counts.get('apply', 0)} matches, {counts.get('review', 0)} to review", 1.0)
    return summary


def stats() -> dict:
    with db.connect() as conn:
        q = lambda sql, *a: conn.execute(sql, a).fetchone()[0]  # noqa: E731
        by_status = dict(conn.execute("SELECT status, COUNT(*) FROM applications GROUP BY status").fetchall())
        by_region = dict(
            conn.execute("SELECT region, COUNT(*) FROM jobs WHERE decision='apply' GROUP BY region").fetchall()
        )
        recent = [
            dict(r)
            for r in conn.execute(
                "SELECT e.ts, e.status, e.note, j.company, j.title FROM events e "
                "JOIN applications a ON a.id=e.application_id JOIN jobs j ON j.id=a.job_id "
                "ORDER BY e.id DESC LIMIT 12"
            )
        ]
        return {
            "jobs_total": q("SELECT COUNT(*) FROM jobs"),
            "matches": q("SELECT COUNT(*) FROM jobs WHERE decision='apply'"),
            "review": q("SELECT COUNT(*) FROM jobs WHERE decision='review'"),
            "applied": q("SELECT COUNT(*) FROM applications WHERE applied_at IS NOT NULL"),
            "applied_today": db.applied_today(conn),
            "interviews": by_status.get("interviewing", 0) + by_status.get("offer", 0),
            "by_status": by_status,
            "by_region": by_region,
            "recent": recent,
            "last_scrape": q("SELECT MAX(last_seen) FROM jobs"),
        }
