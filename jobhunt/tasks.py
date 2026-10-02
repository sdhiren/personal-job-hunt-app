"""Background work for the desktop app: one job search at a time, and an apply queue that drives
a single browser window."""

from __future__ import annotations

import os
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

    def start(self, **kwargs) -> bool:
        with self.lock:
            if self.state["running"]:
                return False
            self.state = {
                "running": True,
                "progress": 0.0,
                "log": [],
                "result": None,
                "error": None,
                "started": time.time(),
            }
        threading.Thread(target=self._run, kwargs=kwargs, daemon=True).start()
        return True

    def _run(self, **kwargs):
        from .services import run_search

        try:
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
    """Applications are processed one by one in a visible browser; you review and click Submit.

    One worker thread at a time owns the browser. `_running` is changed only under `lock`, and the
    worker re-checks the queue under that lock before exiting, so a job queued while the browser is
    closing is never stranded.
    """

    idle_timeout = 5.0  # seconds without new jobs before the browser is closed

    def __init__(self):
        self.q: queue.Queue[str] = queue.Queue()
        self.current: dict | None = None
        self.pending: list[str] = []
        self.lock = threading.Lock()
        self._running = False

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "current": self.current,
                "pending": list(self.pending),
                # in Docker the browser runs on a virtual display you open in a tab (noVNC)
                "browser_view": os.environ.get("JOBHUNT_BROWSER_VIEW_URL") or None,
            }

    def add(self, job_ids: list[str]) -> int:
        """Queue jobs, within today's limit (applied today + already queued count against it)."""
        from .config import profile

        with db.connect() as conn:
            with self.lock:
                in_flight = len(self.pending) + (1 if self.current else 0)
            budget = profile()["apply"]["max_per_day"] - db.applied_today(conn) - in_flight
            added = 0
            for jid in job_ids:
                if added >= budget:
                    break
                with self.lock:
                    if jid in self.pending or (self.current and self.current["job_id"] == jid):
                        continue
                db.set_status(conn, jid, "queued", note="queued from app")
                conn.commit()  # visible before the worker picks it up
                with self.lock:
                    self.pending.append(jid)
                    self.q.put(jid)
                    if not self._running:
                        self._running = True
                        threading.Thread(target=self._worker, daemon=True).start()
                added += 1
        return added

    def _worker(self):
        from .apply import Applier

        try:
            while True:
                with Applier(review_timeout=600) as applier:
                    self._drain(applier)
                with self.lock:
                    if self.q.empty():
                        self._running = False
                        return
                # more jobs arrived while the browser was closing: open it again
        except Exception:
            traceback.print_exc()
            with self.lock:
                self._running = False

    def _drain(self, applier) -> None:
        from .services import apply_job

        while True:
            try:
                jid = self.q.get(timeout=self.idle_timeout)
            except queue.Empty:
                return
            with self.lock:
                self.pending = [p for p in self.pending if p != jid]
            with db.connect() as conn:
                r = conn.execute("SELECT * FROM jobs WHERE id=%s", (jid,)).fetchone()
                if not r:
                    continue
                with self.lock:
                    self.current = {"job_id": jid, "company": r["company"], "title": r["title"], "since": time.time()}
                try:
                    apply_job(conn, applier, r)
                finally:
                    with self.lock:
                        self.current = None


search_task = SearchTask()
apply_queue = ApplyQueue()
