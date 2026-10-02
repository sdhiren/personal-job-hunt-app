from __future__ import annotations

import csv
import json
import logging
import sys

import typer
from rich.console import Console
from rich.table import Table

from . import db
from .config import companies, profile

app = typer.Typer(help="Scrape jobs, match them to your resume, apply, and track applications.", no_args_is_help=True)
console = Console()
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


@app.command()
def scrape(
    source: list[str] = typer.Option(
        None, "--source", "-s", help="companies | arbeitnow | remotive | adzuna (repeatable)"
    ),
    claude: bool = typer.Option(None, help="Use Claude for web discovery + scoring (default: Settings)"),
):
    """Find jobs from all sources (+ Claude web search if connected), store and score them."""
    from .services import run_search

    with console.status("Searching...") as st:
        result = run_search(lambda msg, pct=None: st.update(msg), sources=source, use_claude=claude)
    for e in result["errors"]:
        console.print(f"[yellow]warn[/] {e}")
    d = result["decisions"]
    console.print(
        f"Fetched [bold]{result['fetched']}[/] jobs ([green]{result['new']} new[/]). "
        f"Matches: [bold]{d.get('apply', 0)}[/], review: {d.get('review', 0)}"
        + (f", Claude scored {result['claude_scored']}" if result["claude_used"] else "")
    )
    console.print("Next: [bold]./jh app[/] for the app, or [bold]./jh list[/].")


@app.command("evaluate")
def evaluate_cmd():
    """Re-run filters/scoring on stored jobs (after editing your profile)."""
    from .services import evaluate_all

    with db.connect() as conn, console.status("Matching...") as st:
        evaluate_all(conn, lambda msg, pct=None: st.update(msg))
        counts = dict(conn.execute("SELECT decision, COUNT(*) FROM jobs GROUP BY decision").fetchall())
    console.print("Decisions: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))


@app.command("list")
def list_jobs(
    decision: str = typer.Option("apply", "-d", help="apply | review | reject | all"),
    region: str | None = typer.Option(None, "-r"),
    limit: int = typer.Option(40, "-n"),
    include_applied: bool = typer.Option(False, "--all-status", help="Include jobs already handled"),
):
    """Show matched jobs, best first."""
    q = "SELECT j.*, a.status AS app_status FROM jobs j LEFT JOIN applications a ON a.job_id=j.id WHERE 1=1"
    args: list = []
    if decision != "all":
        q += " AND j.decision=%s"
        args.append(decision)
    if region:
        q += " AND j.region=%s"
        args.append(region)
    if not include_applied:
        q += " AND (a.status IS NULL OR a.status IN ('queued','needs_manual','failed'))"
    q += " ORDER BY j.score DESC NULLS LAST, j.posted_at DESC NULLS LAST LIMIT %s"
    args.append(limit)
    with db.connect() as conn:
        rows = conn.execute(q, args).fetchall()
    t = Table(show_lines=False, header_style="bold")
    for col in ("#", "score", "company", "title", "location", "region", "wfh", "visa", "rating", "why"):
        t.add_column(col, overflow="fold")
    for i, r in enumerate(rows, 1):
        reasons = json.loads(r["reasons"] or "[]")
        t.add_row(
            str(i),
            str(r["score"]),
            r["company"],
            r["title"],
            (r["location"] or "")[:40],
            r["region"],
            "✓" if r["is_wfh"] else "",
            r["visa"] or "",
            str(r["rating"] or "?"),
            (reasons[0] if reasons else "")[:60],
        )
    console.print(t)
    console.print(f"[dim]{len(rows)} shown. `jobhunt show <#|id>` for details.[/]")
    _remember_listing([r["id"] for r in rows])


def _remember_listing(ids: list[str]) -> None:
    from .config import DATA_DIR

    (DATA_DIR / ".last_list.json").write_text(json.dumps(ids))


def _resolve(ref: str) -> str:
    from .config import DATA_DIR

    if ref.isdigit():
        ids = json.loads((DATA_DIR / ".last_list.json").read_text())
        return ids[int(ref) - 1]
    return ref


@app.command()
def show(ref: str):
    """Show one job (number from the last `list`, or full job id)."""
    job_id = _resolve(ref)
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM jobs WHERE id=%s", (job_id,)).fetchone()
        app_row = conn.execute("SELECT * FROM applications WHERE job_id=%s", (job_id,)).fetchone()
    if not r:
        raise typer.BadParameter("no such job")
    console.rule(f"{r['company']} — {r['title']}")
    console.print(
        f"id: {r['id']}\nlocation: {r['location']}  region: {r['region']}  WFH: {bool(r['is_wfh'])}"
        f"\nvisa: {r['visa']}  rating: {r['rating']}  score: {r['score']} (kw {r['kw_score']}, "
        f"llm {r['llm_score']})  decision: {r['decision']}\nurl: {r['url']}\napply: {r['apply_url']}"
    )
    for reason in json.loads(r["reasons"] or "[]"):
        console.print(f"  • {reason}")
    if app_row:
        console.print(
            f"\napplication: [bold]{app_row['status']}[/] ({app_row['method']}) "
            f"applied {app_row['applied_at'] or '-'}  notes: {app_row['notes'] or ''}"
        )
    console.print("\n" + (r["description"] or "")[:2500])


@app.command()
def apply(
    ref: list[str] | None = typer.Argument(None, help="Specific jobs (# from list, or ids)"),
    limit: int = typer.Option(5, "-n", help="How many top matches to process"),
    mode: str | None = typer.Option(None, help="review | auto (default: profile.yaml)"),
    region: str | None = typer.Option(None, "-r"),
    llm: bool = typer.Option(None, help="Draft answers with Claude (default: Settings)"),
):
    """Open and fill application forms for your top matches, then record the outcome."""
    from .apply import Applier

    cfg = profile()["apply"]
    with db.connect() as conn:
        if ref:
            ids = [_resolve(x) for x in ref]
        else:
            q = (
                "SELECT j.id FROM jobs j LEFT JOIN applications a ON a.job_id=j.id WHERE j.decision='apply' "
                "AND (a.status IS NULL OR a.status IN ('queued','failed'))"
            )
            args: list = []
            if region:
                q += " AND j.region=%s"
                args.append(region)
            ids = [r[0] for r in conn.execute(q + " ORDER BY j.score DESC NULLS LAST LIMIT %s", (*args, limit))]
        if not ids:
            console.print("Nothing to apply to. Run [bold]jobhunt scrape[/] or check [bold]jobhunt list -d review[/].")
            return
        budget = cfg["max_per_day"] - db.applied_today(conn)
        if budget <= 0:
            console.print(f"Daily cap of {cfg['max_per_day']} reached (apply.max_per_day).")
            return
        ids = ids[:budget]

        use_mode = mode or cfg["mode"]
        console.print(f"Applying to {len(ids)} job(s) in [bold]{use_mode}[/] mode. A browser window will open.")
        ask = lambda msg: console.input(f"[cyan]{msg}[/] ")  # noqa: E731
        with Applier(mode=use_mode, use_llm=llm) as applier:
            for job_id in ids:
                r = conn.execute("SELECT * FROM jobs WHERE id=%s", (job_id,)).fetchone()
                job = db.row_to_job(r)
                abroad = r["region"] in ("europe", "canada", "australia")
                console.rule(f"{job.company} — {job.title} ({r['location']})")
                db.set_status(conn, job_id, "in_progress", method="auto" if job.ats else "manual")
                conn.commit()
                res = applier.apply(job, abroad, ask)
                method = "auto" if res.note == "auto-submitted" else ("assisted" if job.ats else "manual")
                db.set_status(
                    conn,
                    job_id,
                    res.status,
                    note=res.note,
                    method=method,
                    answers=res.answers,
                    cover_letter=res.cover_letter,
                    screenshot=res.screenshot,
                    error=res.note if res.status == "failed" else None,
                )
                conn.commit()
                color = {"applied": "green", "failed": "red"}.get(res.status, "yellow")
                console.print(f"→ [{color}]{res.status}[/] {res.note}")


@app.command()
def track(status: str | None = typer.Option(None, "-s"), limit: int = typer.Option(100, "-n")):
    """Your application tracker."""
    q = "SELECT a.*, j.company, j.title, j.location, j.url, j.score FROM applications a JOIN jobs j ON j.id=a.job_id"
    args: list = []
    if status:
        q += " WHERE a.status=%s"
        args.append(status)
    q += " ORDER BY a.updated_at DESC LIMIT %s"
    args.append(limit)
    with db.connect() as conn:
        rows = conn.execute(q, args).fetchall()
        summary = conn.execute("SELECT status, COUNT(*) FROM applications GROUP BY status").fetchall()
    t = Table(header_style="bold")
    for col in ("app#", "status", "company", "title", "location", "applied", "updated", "notes"):
        t.add_column(col, overflow="fold")
    for r in rows:
        t.add_row(
            str(r["id"]),
            r["status"],
            r["company"],
            r["title"],
            (r["location"] or "")[:30],
            (r["applied_at"] or "")[:10],
            (r["updated_at"] or "")[:10],
            (r["notes"] or r["error"] or "")[:50],
        )
    console.print(t)
    console.print("  ".join(f"{s}: {n}" for s, n in summary))


@app.command()
def status(
    ref: str = typer.Argument(..., help="a<N> = app# from `track` (e.g. a12), <N> = # from `list`, or job id"),
    new_status: str = typer.Argument(..., help=" | ".join(db.APP_STATUSES)),
    note: str = typer.Option("", "--note", "-m"),
):
    """Update an application's status (e.g. after an interview call)."""
    with db.connect() as conn:
        if ref[:1] == "a" and ref[1:].isdigit():
            row = conn.execute("SELECT job_id FROM applications WHERE id=%s", (int(ref[1:]),)).fetchone()
            if not row:
                raise typer.BadParameter(f"no application {ref}")
            job_id = row["job_id"]
        else:
            job_id = _resolve(ref)
        db.set_status(conn, job_id, new_status, note=note, method=None, notes=note or None)
    console.print(f"{job_id} → [bold]{new_status}[/]")


@app.command("mark-applied")
def mark_applied(ref: str, note: str = typer.Option("", "--note", "-m")):
    """Record a job you applied to yourself (e.g. via LinkedIn or the company site)."""
    with db.connect() as conn:
        db.set_status(conn, _resolve(ref), "applied", note=note, method="manual", notes=note or None)
    console.print("recorded.")


@app.command()
def export(path: str = "data/applications.csv"):
    """Export the tracker to CSV (opens in Excel/Sheets)."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT a.id, a.status, a.method, a.applied_at, a.updated_at, j.company, j.title, j.location, "
            "j.region, j.is_wfh, j.visa, j.rating, j.score, j.url, a.notes FROM applications a "
            "JOIN jobs j ON j.id=a.job_id ORDER BY a.updated_at DESC"
        ).fetchall()
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        if rows:
            w.writerow(rows[0].keys())
        w.writerows([tuple(r) for r in rows])
    console.print(f"wrote {len(rows)} rows to {path}")


@app.command("app")
def run_app(
    port: int = typer.Option(8765, envvar="JOBHUNT_PORT"),
    host: str = typer.Option("127.0.0.1", envvar="JOBHUNT_HOST", help="0.0.0.0 inside Docker"),
    open_browser: bool = typer.Option(True, "--open/--no-open"),
):
    """Start the jobhunt app (local only) and open it in your browser."""
    import threading
    import webbrowser

    import uvicorn

    from .web import api

    url = f"http://127.0.0.1:{port}"
    console.print(f"jobhunt is running at [bold]{url}[/]  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(api, host=host, port=port, log_level="warning")


@app.command(hidden=True)
def dashboard(port: int = 8765):
    """Alias for `app`."""
    run_app(port=port, host="127.0.0.1", open_browser=True)


@app.command("import-sqlite")
def import_sqlite(path: str = typer.Argument(None, help="SQLite file (default: data/jobhunt.db)")):
    """Copy jobs, applications and history from the old SQLite database into PostgreSQL."""
    import sqlite3
    from pathlib import Path

    from .config import SQLITE_PATH

    file = Path(path) if path else SQLITE_PATH
    if not file.exists():
        raise typer.BadParameter(f"{file} not found")
    src = sqlite3.connect(file)
    src.row_factory = sqlite3.Row
    with db.connect() as conn:
        for table in ("jobs", "applications", "events"):
            rows = src.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                continue
            cols = rows[0].keys()
            sql = (
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
                "ON CONFLICT DO NOTHING"
            )
            with conn.cursor() as cur:
                cur.executemany(sql, [tuple(db._text(v) if isinstance(v, str) else v for v in r) for r in rows])
            if table != "jobs":  # keep the id sequence ahead of the copied ids
                conn.execute(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 1)) FROM {table}"
                )
            console.print(f"{table}: {len(rows)} rows read (rows already present are skipped)")
    src.close()
    console.print("[green]Imported.[/] The SQLite file was left untouched.")


@app.command("check-companies")
def check_companies():
    """Validate the ATS slugs in config/companies.yaml."""
    import httpx

    from .sources import ATS_FETCHERS, UA

    with httpx.Client(headers=UA, follow_redirects=True) as client:
        for c in companies():
            try:
                n = len(ATS_FETCHERS[c.ats](client, c))
                console.print(f"[green]ok[/]   {c.name:18} {c.ats:10} {n} jobs")
            except Exception as e:
                console.print(f"[red]fail[/] {c.name:18} {c.ats:10} {e}")


if __name__ == "__main__":
    sys.exit(app())
