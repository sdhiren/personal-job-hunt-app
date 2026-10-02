from __future__ import annotations

import csv
import json
import logging
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import db
from .config import DATA_DIR, SQLITE_PATH, companies, profile

LAST_LIST = DATA_DIR / ".last_list.json"  # ids shown by the last `list`, so `show 3` etc. work

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
    if limit := result.get("claude_limit"):
        resets = f" — resets {limit['resets']}" if limit["resets"] else ""
        console.print(f"[yellow]Claude usage limit:[/] {limit['reason']}{resets}. Remaining jobs are scored next time.")
    console.print("Next: [bold]./jh app[/] for the app, or [bold]./jh list[/].")


@app.command("evaluate")
def evaluate_cmd():
    """Re-run filters/scoring on stored jobs (after editing your profile)."""
    from .services import evaluate_all

    with db.connect() as conn, console.status("Matching...") as st:
        evaluate_all(conn, lambda msg, pct=None: st.update(msg))
        counts = db.pairs(conn, "SELECT decision, COUNT(*) FROM jobs GROUP BY decision")
    console.print("Decisions: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))


@app.command("list")
def list_jobs(
    decision: str = typer.Option("apply", "-d", help="apply | review | reject | all"),
    region: str | None = typer.Option(None, "-r"),
    limit: int = typer.Option(40, "-n", min=1),
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
        q += " AND (a.status IS NULL OR a.status = ANY(%s))"
        args.append(list(db.OPEN_STATUSES))
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
    LAST_LIST.write_text(json.dumps([r["id"] for r in rows]))


def _resolve(ref: str) -> str:
    """A job id, or the row number from the last `list`."""
    if not ref.isdigit():
        return ref
    ids = json.loads(LAST_LIST.read_text()) if LAST_LIST.exists() else []
    if not 1 <= int(ref) <= len(ids):
        raise typer.BadParameter(f"no row {ref} in the last `list` ({len(ids)} shown); run `jobhunt list` first")
    return ids[int(ref) - 1]


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
    limit: int = typer.Option(5, "-n", min=1, help="How many top matches to process"),
    mode: str | None = typer.Option(None, help="review | auto (default: profile.yaml)"),
    region: str | None = typer.Option(None, "-r"),
    llm: bool = typer.Option(None, help="Draft answers with Claude (default: Settings)"),
):
    """Open and fill application forms for your top matches, then record the outcome."""
    from .apply import Applier
    from .services import apply_job

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
            ids = [r["id"] for r in conn.execute(q + " ORDER BY j.score DESC NULLS LAST LIMIT %s", (*args, limit))]
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
                if not r:
                    console.print(f"[yellow]skip[/] no job {job_id}")
                    continue
                console.rule(f"{r['company']} — {r['title']} ({r['location']})")
                res = apply_job(conn, applier, r, ask)
                color = {"applied": "green", "failed": "red"}.get(res.status, "yellow")
                console.print(f"→ [{color}]{res.status}[/] {res.note}")


@app.command()
def track(status: str | None = typer.Option(None, "-s"), limit: int = typer.Option(100, "-n", min=1)):
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
def export(path: Path = typer.Option(DATA_DIR / "applications.csv", "--path", "-o")):
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
        w.writerows(r.values() for r in rows)
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

    if _port_in_use(host, port):
        console.print(
            f"[red]Port {port} is already in use[/] — is jobhunt already running (another terminal, or `make up`)? "
            f"Stop it, or start this one on another port with JOBHUNT_PORT in .env."
        )
        raise typer.Exit(1)
    db.pool()  # fail now with a clear message rather than on the first page load

    url = f"http://127.0.0.1:{port}"
    console.print(f"jobhunt is running at [bold]{url}[/]  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(api, host=host, port=port, log_level="warning")


def _port_in_use(host: str, port: int) -> bool:
    import socket

    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1" if host in ("0.0.0.0", "") else host, port)) == 0


@app.command(hidden=True)
def dashboard(port: int = 8765):
    """Alias for `app`."""
    run_app(port=port, host="127.0.0.1", open_browser=True)


@app.command("import-sqlite")
def import_sqlite(path: Path = typer.Argument(SQLITE_PATH, exists=True, dir_okay=False, help="Old SQLite database")):
    """Copy jobs, applications and history from the old SQLite database into PostgreSQL."""
    with db.connect() as conn:
        counts = db.import_sqlite(conn, path)
    for table, n in counts.items():
        console.print(f"{table}: {n} rows read")
    console.print("[green]Imported.[/] Rows that were already there were skipped; the SQLite file is unchanged.")


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


def main() -> None:
    """Entry point: run a command, showing database problems as a message instead of a traceback."""
    try:
        app()
    except db.DatabaseUnavailable as e:
        console.print(f"[red]{e}[/]")
        sys.exit(1)


if __name__ == "__main__":
    main()
