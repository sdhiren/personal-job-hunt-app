"""Background work for the desktop app: one job search at a time, and an apply queue that drives
a single browser window."""

from __future__ import annotations

import queue
import threading
import time
import traceback

from . import db


class SearchTask:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = {"running": False, "progress": 0.0, "log": [], "result": None, "error": None}

    def snapshot(self) -> dict:
        with self.lock:
            return {**self.state, "log": self.state["log"][-40:]}

    def _progress(self, msg: str, pct: float | None = None) -> None:
        with self.lock:
            self.state["log"].append({"t": time.strftime("%H:%M:%S"), "msg": msg})
            if pct is not None:
                self.state["progress"] = pct

    def start(self, kind: str = "search", **kwargs) -> bool:
        with self.lock:
            if self.state["running"]:
                return False
            self.state = {
                "running": True,
                "kind": kind,
                "progress": 0.0,
                "log": [],
                "result": None,
                "error": None,
                "started": time.time(),
            }
        kwargs["kind"] = kind
        threading.Thread(target=self._run, kwargs=kwargs, daemon=True).start()
        return True

    def _run(self, kind: str, **kwargs):
        from .services import evaluate_all, run_search

        try:
            if kind == "rematch":
                with db.connect() as conn:
                    evaluate_all(conn, self._progress)
                    result = {
                        "decisions": dict(
                            conn.execute("SELECT decision, COUNT(*) FROM jobs GROUP BY decision").fetchall()
                        )
                    }
                self._progress("Re-matched all jobs against your profile", 1.0)
            else:
                result = run_search(self._progress, **kwargs)
            with self.lock:
                self.state["result"] = result
        except Exception as e:
            traceback.print_exc()
            with self.lock:
                self.state["error"] = f"{type(e).__name__}: {e}"
        finally:
            with self.lock:
                self.state["running"] = False


class ApplyQueue:
    """Applications are processed one by one in a visible browser; you review and click Submit."""

    def __init__(self):
        self.q: queue.Queue[str] = queue.Queue()
        self.current: dict | None = None
        self.pending: list[str] = []
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None

    def snapshot(self) -> dict:
        with self.lock:
            return {"current": self.current, "pending": list(self.pending)}

    def add(self, job_ids: list[str]) -> int:
        from .config import profile

        with db.connect() as conn:
            budget = profile()["apply"]["max_per_day"] - db.applied_today(conn)
            added = 0
            for jid in job_ids:
                if added >= budget:
                    break
                with self.lock:
                    if jid in self.pending or (self.current and self.current["job_id"] == jid):
                        continue
                    self.pending.append(jid)
                db.set_status(conn, jid, "queued", note="queued from app")
                self.q.put(jid)
                added += 1
        if added and (self.thread is None or not self.thread.is_alive()):
            self.thread = threading.Thread(target=self._worker, daemon=True)
            self.thread.start()
        return added

    def _worker(self):
        from .apply import Applier

        with Applier(review_timeout=600) as applier:
            while True:
                try:
                    jid = self.q.get(timeout=5)
                except queue.Empty:
                    break
                with db.connect() as conn:
                    r = conn.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
                    if not r:
                        continue
                    job = db.row_to_job(r)
                    with self.lock:
                        self.pending = [p for p in self.pending if p != jid]
                        self.current = {"job_id": jid, "company": job.company, "title": job.title, "since": time.time()}
                    db.set_status(conn, jid, "in_progress", method="assisted" if job.ats else "manual")
                    conn.commit()
                    res = applier.apply(job, r["region"] in ("europe", "canada", "australia"), ask=None)
                    method = "auto" if res.note == "auto-submitted" else ("assisted" if job.ats else "manual")
                    db.set_status(
                        conn,
                        jid,
                        res.status,
                        note=res.note,
                        method=method,
                        answers=res.answers,
                        cover_letter=res.cover_letter,
                        screenshot=res.screenshot,
                        error=res.note if res.status == "failed" else None,
                    )
                with self.lock:
                    self.current = None


search_task = SearchTask()
apply_queue = ApplyQueue()
