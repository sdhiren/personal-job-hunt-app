"""Local app server (127.0.0.1, or published to localhost only by Docker): JSON API + the UI in ./static."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import claude_backend, db
from .config import (
    RESUME_DIR,
    SCREENSHOT_DIR,
    ensure_dirs,
    extract_text,
    profile,
    resume_path,
    save_profile,
    save_settings,
    settings,
    skill_pattern,
)
from .tasks import apply_queue, search_task

STATIC = Path(__file__).parent / "static"
api = FastAPI(title="jobhunt")


@api.exception_handler(db.DatabaseUnavailable)
def database_unavailable(request, exc: db.DatabaseUnavailable):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


# ---------------------------------------------------------------- profile & resume


@api.get("/api/profile")
def get_profile():
    p = profile()
    rp = resume_path()
    return {**p, "resume": {"name": rp.name, "size": rp.stat().st_size} if rp else None}


@api.put("/api/profile")
def put_profile(body: dict):
    body.pop("resume", None)
    for s in body.get("matching", {}).get("skills", []) or []:
        if not s.get("pattern"):
            s["pattern"] = skill_pattern(s["name"], s.get("aliases"))
        s.pop("aliases", None)
    return save_profile(body)  # the UI then offers a job search, which re-scores stored jobs too


@api.post("/api/resume")
def upload_resume(file: UploadFile = File(...)):
    ensure_dirs()
    suffix = Path(file.filename or "resume.pdf").suffix.lower()
    if suffix not in (".pdf", ".docx", ".txt", ".md"):
        raise HTTPException(400, "Upload a PDF, DOCX or TXT resume")
    name = re.sub(r"[^\w.-]+", "_", Path(file.filename).stem)[:60] + suffix
    dest = RESUME_DIR / name
    dest.write_bytes(file.file.read())
    text = extract_text(dest)
    if len(text.strip()) < 200:
        raise HTTPException(400, "Couldn't read text from that file (is it a scanned image?)")
    save_profile({"candidate": {"resume_path": str(dest.relative_to(dest.parents[2]))}})
    return {"name": name, "chars": len(text)}


@api.post("/api/resume/parse")
def parse_resume():
    """Ask Claude to read the resume and propose profile fields + skills (not saved until you click Save)."""
    from . import llm

    rp = resume_path()
    if not rp:
        raise HTTPException(400, "Upload a resume first")
    try:
        data = llm.parse_resume(extract_text(rp))
    except claude_backend.ClaudeNotConfigured as e:
        raise HTTPException(400, f"Connect Claude in Settings first ({e})") from e
    except claude_backend.ClaudeError as e:
        raise HTTPException(502, str(e)) from e
    for s in data.get("skills", []):
        s["pattern"] = skill_pattern(s["name"], s.get("aliases"))
        s["weight"] = max(1, min(4, int(s.get("weight", 2))))
    return data


@api.get("/api/resume/file")
def resume_file():
    rp = resume_path()
    if not rp:
        raise HTTPException(404)
    return FileResponse(rp)


# ---------------------------------------------------------------- Claude connection & settings


class ApiKeyIn(BaseModel):
    api_key: str
    model: str = "claude-opus-5"


@api.get("/api/claude")
def claude_status():
    return claude_backend.status()


@api.post("/api/claude/mode")
def claude_mode(body: dict):
    if body.get("mode") not in ("account", "api_key", "off"):
        raise HTTPException(400, "mode must be account | api_key | off")
    save_settings({"claude_mode": body["mode"]})
    return claude_backend.status()


@api.post("/api/claude/login")
def claude_login():
    try:
        return {"message": claude_backend.start_account_login()}
    except claude_backend.ClaudeError as e:
        raise HTTPException(400, str(e)) from e


@api.post("/api/claude/api-key")
def claude_api_key(body: ApiKeyIn):
    key = body.api_key.strip()
    try:
        msg = claude_backend.ApiBackend(key, body.model).test()
    except Exception as e:
        raise HTTPException(400, f"That key didn't work: {e}") from e
    save_settings({"api_key": key, "api_model": body.model, "claude_mode": "api_key"})
    return {"message": msg, **claude_backend.status()}


@api.delete("/api/claude/api-key")
def claude_forget_key():
    s = settings()
    save_settings({"api_key": "", "claude_mode": "account" if s["claude_mode"] == "api_key" else s["claude_mode"]})
    return claude_backend.status()


@api.post("/api/claude/test")
def claude_test():
    schema = {
        "type": "object",
        "properties": {"reply": {"type": "string"}},
        "required": ["reply"],
        "additionalProperties": False,
    }
    try:
        b = claude_backend.backend()
        out = b.structured("Say hello in five words or fewer.", schema, "You are a connection test.")
    except claude_backend.ClaudeError as e:
        raise HTTPException(400, str(e)) from e
    return {"message": f"{b.name}: {out['reply']}"}


@api.get("/api/settings")
def get_settings():
    s = settings()
    s["api_key"] = claude_backend._mask(s.get("api_key", ""))
    s["adzuna_app_key"] = "••••" if s.get("adzuna_app_key") else ""
    return s


@api.put("/api/settings")
def put_settings(body: dict):
    for secret in ("api_key", "claude_mode"):
        body.pop(secret, None)
    if body.get("adzuna_app_key") == "••••":
        body.pop("adzuna_app_key")
    save_settings(body)
    return get_settings()


# ---------------------------------------------------------------- search


@api.post("/api/search")
def start_search(body: dict | None = None):
    use_claude = (body or {}).get("use_claude")
    if not search_task.start(use_claude=use_claude):
        raise HTTPException(409, "A search is already running")
    return search_task.snapshot()


@api.get("/api/search")
def search_state():
    return search_task.snapshot()


# ---------------------------------------------------------------- jobs


@api.get("/api/jobs")
def jobs(
    decision: str = "apply",
    region: str = "",
    q: str = "",
    wfh: bool = False,
    hide_handled: bool = True,
    limit: int = 200,
    offset: int = 0,
):
    sql = (
        "SELECT j.id, j.source, j.company, j.title, j.location, j.region, j.is_wfh, j.visa, j.rating, j.score, "
        "j.kw_score, j.llm_score, j.decision, j.reasons, j.url, j.posted_at, j.ats, j.first_seen, "
        "a.status AS app_status FROM jobs j LEFT JOIN applications a ON a.job_id=j.id WHERE 1=1"
    )
    args: list = []
    if decision != "all":
        sql += " AND j.decision=%s"
        args.append(decision)
    if region:
        sql += " AND j.region=%s"
        args.append(region)
    if wfh:
        sql += " AND j.is_wfh=1"
    if q:
        sql += " AND (j.title ILIKE %s OR j.company ILIKE %s OR j.location ILIKE %s)"
        args += [f"%{q}%"] * 3
    if hide_handled:
        sql += " AND (a.status IS NULL OR a.status = ANY(%s))"
        args.append(list(db.OPEN_STATUSES))
    with db.connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM ({sql}) AS matched", args).fetchone()[0]
        rows = conn.execute(
            sql + " ORDER BY j.score DESC NULLS LAST, j.posted_at DESC NULLS LAST LIMIT %s OFFSET %s",
            (*args, limit, offset),
        ).fetchall()
    return {"total": total, "jobs": [{**dict(r), "reasons": json.loads(r["reasons"] or "[]")} for r in rows]}


@api.get("/api/job")
def job_detail(id: str):
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM jobs WHERE id=%s", (id,)).fetchone()
        if not r:
            raise HTTPException(404)
        app_row = conn.execute("SELECT * FROM applications WHERE job_id=%s", (id,)).fetchone()
        events = (
            [
                dict(e)
                for e in conn.execute(
                    "SELECT ts, status, note FROM events WHERE application_id=%s ORDER BY id DESC", (app_row["id"],)
                )
            ]
            if app_row
            else []
        )
    out = {
        **dict(r),
        "reasons": json.loads(r["reasons"] or "[]"),
        "llm": json.loads(r["llm_json"]) if r["llm_json"] else None,
        "application": dict(app_row) if app_row else None,
        "events": events,
    }
    out.pop("llm_json", None)
    return out


@api.post("/api/job/score")
def job_score(body: dict):
    """Score one job with Claude now."""
    from . import llm
    from .services import _eval

    with db.connect() as conn:
        r = conn.execute("SELECT * FROM jobs WHERE id=%s", (body.get("id"),)).fetchone()
        if not r:
            raise HTTPException(404)
        job = db.row_to_job(r)
        try:
            claude_backend.backend()
        except claude_backend.ClaudeError as e:
            raise HTTPException(400, str(e)) from e
        try:
            a = llm.assess(job)
        except claude_backend.ClaudeUsageLimit as e:
            raise HTTPException(429, f"{e}. Try again after it resets.") from e
        if not a:
            raise HTTPException(502, "Claude couldn't score this job")
        db.save_evaluation(conn, job.id, _eval(job, a), json.dumps(a))
    return job_detail(body["id"])


# ---------------------------------------------------------------- applying & tracking


@api.post("/api/apply")
def apply(body: dict):
    ids = body.get("job_ids") or []
    added = apply_queue.add(ids)
    if ids and not added:
        raise HTTPException(409, "Daily application limit reached, or already queued")
    return {"added": added, **apply_queue.snapshot()}


@api.get("/api/apply")
def apply_state():
    return apply_queue.snapshot()


class StatusIn(BaseModel):
    job_id: str
    status: str
    note: str = ""


@api.post("/api/status")
def set_status(body: StatusIn):
    try:
        with db.connect() as conn:
            db.set_status(
                conn,
                body.job_id,
                body.status,
                note=body.note,
                method="manual" if body.status == "applied" else None,
                notes=body.note or None,
            )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}


@api.get("/api/applications")
def applications():
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT a.id, a.job_id, a.status, a.method, a.applied_at, a.updated_at, a.notes, a.error, a.screenshot, "
            "j.company, j.title, j.location, j.region, j.url, j.score, j.is_wfh, j.visa "
            "FROM applications a JOIN jobs j ON j.id=a.job_id ORDER BY a.updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@api.get("/api/stats")
def stats():
    from .services import stats as _stats

    return _stats()


@api.get("/api/export.csv")
def export_csv():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "status",
            "method",
            "applied_at",
            "updated_at",
            "company",
            "title",
            "location",
            "region",
            "wfh",
            "visa",
            "rating",
            "score",
            "url",
            "notes",
        ]
    )
    with db.connect() as conn:
        for r in conn.execute(
            "SELECT a.status, a.method, a.applied_at, a.updated_at, j.company, j.title, j.location, j.region, "
            "j.is_wfh, j.visa, j.rating, j.score, j.url, a.notes FROM applications a JOIN jobs j ON "
            "j.id=a.job_id ORDER BY a.updated_at DESC"
        ):
            w.writerow(tuple(r))
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=applications.csv"},
    )


@api.get("/api/screenshot")
def screenshot(path: str):
    p = Path(path).resolve()
    if not p.exists():  # recorded on the other side of Docker: same file, different mount point
        p = (SCREENSHOT_DIR / Path(path).name).resolve()
    if SCREENSHOT_DIR.resolve() not in p.parents or not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


api.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
