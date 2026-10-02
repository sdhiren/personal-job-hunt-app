"""Local SQLite store: every scraped job, its evaluation, and your application history."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime

from .config import DB_PATH, ensure_dirs
from .models import Evaluation, Job

APP_STATUSES = [
    "queued",
    "in_progress",
    "applied",
    "needs_manual",
    "failed",
    "skipped",
    "screening",
    "interviewing",
    "offer",
    "rejected",
    "withdrawn",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    source TEXT, company TEXT, title TEXT, location TEXT, url TEXT, apply_url TEXT,
    description TEXT, remote INTEGER, workplace TEXT, posted_at TEXT,
    ats TEXT, ats_slug TEXT, external_id TEXT, extra TEXT,
    first_seen TEXT, last_seen TEXT,
    -- evaluation
    region TEXT, is_wfh INTEGER, preferred_city INTEGER, visa TEXT, rating REAL,
    kw_score INTEGER, llm_score INTEGER, llm_json TEXT, score INTEGER,
    decision TEXT, reasons TEXT, evaluated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_decision ON jobs(decision, score DESC);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE REFERENCES jobs(id),
    status TEXT NOT NULL,
    method TEXT,                 -- auto | assisted | manual
    applied_at TEXT, updated_at TEXT,
    cover_letter TEXT, answers TEXT, screenshot TEXT, notes TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER REFERENCES applications(id),
    ts TEXT, status TEXT, note TEXT
);
"""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


_schema_ready = False


@contextmanager
def connect():
    global _schema_ready
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    if not _schema_ready:
        conn.execute("PRAGMA journal_mode=WAL")  # readers never block on the background writer
        conn.executescript(SCHEMA)
        _schema_ready = True
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_jobs(conn, jobs: list[Job]) -> tuple[int, int]:
    new = 0
    ts = now()
    for j in jobs:
        exists = conn.execute("SELECT 1 FROM jobs WHERE id=?", (j.id,)).fetchone()
        row = dict(
            source=j.source,
            company=j.company,
            title=j.title,
            location=j.location,
            url=j.url,
            apply_url=j.apply_url,
            description=j.description,
            remote=None if j.remote is None else int(j.remote),
            workplace=j.workplace,
            posted_at=j.posted_at.isoformat() if j.posted_at else None,
            ats=j.ats,
            ats_slug=j.ats_slug,
            external_id=j.external_id,
            extra=json.dumps(j.extra),
            last_seen=ts,
        )
        if exists:
            sets = ", ".join(f"{k}=:{k}" for k in row)
            conn.execute(f"UPDATE jobs SET {sets} WHERE id=:id", {**row, "id": j.id})
        else:
            new += 1
            row.update(id=j.id, first_seen=ts)
            cols = ", ".join(row)
            conn.execute(f"INSERT INTO jobs ({cols}) VALUES ({', '.join(':' + k for k in row)})", row)
    return new, len(jobs) - new


def _aware(s: str | None) -> datetime | None:
    if not s:
        return None
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def row_to_job(r: sqlite3.Row) -> Job:
    return Job(
        source=r["source"],
        external_id=r["external_id"],
        company=r["company"],
        title=r["title"],
        location=r["location"] or "",
        url=r["url"],
        description=r["description"] or "",
        apply_url=r["apply_url"],
        remote=None if r["remote"] is None else bool(r["remote"]),
        workplace=r["workplace"],
        posted_at=_aware(r["posted_at"]),
        ats=r["ats"],
        ats_slug=r["ats_slug"],
        extra=json.loads(r["extra"] or "{}"),
    )


def save_evaluation(conn, job_id: str, ev: Evaluation, llm_json: str | None = None) -> None:
    conn.execute(
        """UPDATE jobs SET region=?, is_wfh=?, preferred_city=?, visa=?, rating=?, kw_score=?,
           llm_score=?, llm_json=COALESCE(?, llm_json), score=?, decision=?, reasons=?, evaluated_at=?
           WHERE id=?""",
        (
            ev.region,
            int(ev.is_wfh),
            int(ev.preferred_city),
            ev.visa,
            ev.rating,
            ev.kw_score,
            ev.llm_score,
            llm_json,
            ev.score,
            ev.decision,
            json.dumps(ev.reasons),
            now(),
            job_id,
        ),
    )


def set_status(conn, job_id: str, status: str, note: str = "", method: str | None = None, **fields) -> int:
    if status not in APP_STATUSES:
        raise ValueError(f"status must be one of {APP_STATUSES}")
    ts = now()
    app = conn.execute("SELECT id FROM applications WHERE job_id=?", (job_id,)).fetchone()
    if app is None:
        cur = conn.execute(
            "INSERT INTO applications (job_id, status, method, updated_at) VALUES (?,?,?,?)",
            (job_id, status, method, ts),
        )
        app_id = cur.lastrowid
    else:
        app_id = app["id"]
        conn.execute(
            "UPDATE applications SET status=?, updated_at=?, method=COALESCE(?, method) WHERE id=?",
            (status, ts, method, app_id),
        )
    if status == "applied":
        conn.execute("UPDATE applications SET applied_at=COALESCE(applied_at, ?) WHERE id=?", (ts, app_id))
    for k, v in fields.items():
        if k in ("cover_letter", "answers", "screenshot", "notes", "error"):
            conn.execute(
                f"UPDATE applications SET {k}=? WHERE id=?",
                (json.dumps(v) if isinstance(v, (dict, list)) else v, app_id),
            )
    conn.execute("INSERT INTO events (application_id, ts, status, note) VALUES (?,?,?,?)", (app_id, ts, status, note))
    return app_id


def applied_today(conn) -> int:
    day = datetime.now(UTC).date().isoformat()
    return conn.execute("SELECT COUNT(*) FROM applications WHERE applied_at >= ?", (day,)).fetchone()[0]
