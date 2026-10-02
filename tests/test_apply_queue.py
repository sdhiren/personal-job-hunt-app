"""ApplyQueue with a fake browser and database: no Chromium, PostgreSQL or Claude needed."""

import threading
import time
from contextlib import contextmanager

import pytest

import jobhunt.apply
import jobhunt.services
from jobhunt import db
from jobhunt.tasks import ApplyQueue


class FakeConn:
    def execute(self, *_):
        return self

    def fetchone(self):
        return {"company": "Acme", "title": "Engineer"}

    def commit(self):
        pass


class FakeApplier:
    close_delay = 0.0
    on_close = None

    def __init__(self, **_):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if FakeApplier.on_close:
            FakeApplier.on_close()
        time.sleep(FakeApplier.close_delay)


@pytest.fixture
def applied(monkeypatch):
    done: list[str] = []

    @contextmanager
    def connect():
        yield FakeConn()

    monkeypatch.setattr(db, "connect", connect)
    monkeypatch.setattr(db, "set_status", lambda *a, **k: None)
    monkeypatch.setattr(db, "applied_today", lambda conn: 0)
    monkeypatch.setattr(jobhunt.apply, "Applier", FakeApplier)
    monkeypatch.setattr(jobhunt.services, "apply_job", lambda conn, applier, row: done.append(row))
    monkeypatch.setattr("jobhunt.config.profile", lambda: {"apply": {"max_per_day": 3}})
    FakeApplier.close_delay, FakeApplier.on_close = 0.0, None
    return done


def wait_until(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_job_added_while_browser_closes_is_still_applied(applied):
    q = ApplyQueue()
    q.idle_timeout = 0.05
    closing = threading.Event()
    FakeApplier.close_delay = 0.3
    FakeApplier.on_close = closing.set

    assert q.add(["job-a"]) == 1
    assert closing.wait(2)  # the worker is now shutting the browser down
    assert q.add(["job-b"]) == 1
    assert wait_until(lambda: len(applied) == 2), "job-b was stranded in the queue"
    assert wait_until(lambda: not q._running)


def test_daily_cap_counts_jobs_already_queued(applied, monkeypatch):
    q = ApplyQueue()
    started = threading.Event()
    release = threading.Event()

    def slow_apply(conn, applier, row):  # hold the first job "in progress"
        started.set()
        release.wait(2)
        applied.append(row)

    monkeypatch.setattr(jobhunt.services, "apply_job", slow_apply)
    assert q.add(["a", "b"]) == 2
    assert started.wait(2)
    assert q.add(["c", "d", "e"]) == 1  # cap 3: two already in flight
    release.set()
    assert wait_until(lambda: len(applied) == 3)
