"""The app has no login, so the server must only obey the user's own browser tab."""

import pytest
from fastapi.testclient import TestClient

from jobhunt.web import api


@pytest.fixture
def client():
    return TestClient(api, base_url="http://127.0.0.1:8765")


def test_cross_site_write_is_refused(client):
    r = client.post("/api/search", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403  # refused before a search (and Claude quota) is spent


def test_cross_site_fetch_metadata_is_refused(client):
    r = client.post("/api/claude/login", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_dns_rebinding_host_is_refused():
    r = TestClient(api, base_url="http://attacker.example:8765").get("/api/settings")
    assert r.status_code == 403


def test_same_origin_write_reaches_the_endpoint(client):
    # invalid mode -> the endpoint's own 400, so the guard let the request through
    r = client.post("/api/claude/mode", json={"mode": "bogus"}, headers={"Origin": "http://127.0.0.1:8765"})
    assert r.status_code == 400


def test_extra_hosts_can_be_allowed(monkeypatch):
    monkeypatch.setenv("JOBHUNT_ALLOWED_HOSTS", "jobhunt.local")
    r = TestClient(api, base_url="http://jobhunt.local").post("/api/claude/mode", json={"mode": "bogus"})
    assert r.status_code == 400
