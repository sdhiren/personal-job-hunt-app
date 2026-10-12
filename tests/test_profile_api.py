"""Saving the profile from the Profile page: PUT /api/profile persists, and the next GET shows it."""

import pytest
import yaml
from fastapi.testclient import TestClient

from jobhunt import config
from jobhunt.web import api


@pytest.fixture
def client(tmp_path, monkeypatch):
    """The real template, but the user's profile and data folders in a temporary directory."""
    data = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "SCREENSHOT_DIR", data / "screenshots")
    monkeypatch.setattr(config, "RESUME_DIR", data / "resume")
    monkeypatch.setattr(config, "BROWSER_PROFILE_DIR", data / "browser-profile")
    monkeypatch.setattr(config, "PROFILE_PATH", data / "profile.yaml")
    config.profile.cache_clear()
    yield TestClient(api, base_url="http://127.0.0.1:8765")
    config.profile.cache_clear()


def page_body(p: dict) -> dict:
    """What the Profile page sends on Save: every section, with the user's edits."""
    return {
        "candidate": {
            **p["candidate"],
            "city": "Pune",
            "years_experience": 7,
            "willing_to_relocate": False,
            "target_titles": ["Staff Engineer"],
        },
        "search": {**p["search"], "regions": ["india", "europe"], "india_preferred_cities": ["pune"]},
        "matching": {**p["matching"], "min_score": 70, "skills": [{"name": "Rust", "weight": 3, "aliases": []}]},
        "company": p["company"],
        "apply": {**p["apply"], "mode": "review", "max_per_day": 4},
    }


def test_saved_profile_is_returned_by_the_next_get(client):
    before = client.get("/api/profile").json()
    r = client.put("/api/profile", json=page_body(before))
    assert r.status_code == 200

    after = client.get("/api/profile").json()
    assert after["candidate"]["city"] == "Pune"
    assert after["candidate"]["years_experience"] == 7
    assert after["candidate"]["willing_to_relocate"] is False
    assert after["candidate"]["target_titles"] == ["Staff Engineer"]
    assert after["search"]["regions"] == ["india", "europe"]
    assert after["search"]["india_preferred_cities"] == ["pune"]  # lists replace, never merge
    assert after["matching"]["min_score"] == 70
    assert [(s["name"], s["weight"]) for s in after["matching"]["skills"]] == [("Rust", 3)]
    assert after["matching"]["skills"][0]["pattern"]  # built from the name on save
    assert after["apply"]["max_per_day"] == 4


def test_saved_profile_is_written_to_disk(client):
    client.put("/api/profile", json=page_body(client.get("/api/profile").json()))
    on_disk = yaml.safe_load(config.PROFILE_PATH.read_text(encoding="utf-8"))
    assert on_disk["candidate"]["city"] == "Pune"
    config.profile.cache_clear()  # as after an app restart
    assert client.get("/api/profile").json()["candidate"]["city"] == "Pune"


def test_second_save_replaces_the_first(client):
    body = page_body(client.get("/api/profile").json())
    client.put("/api/profile", json=body)
    body["candidate"]["city"] = "Delhi"
    body["candidate"]["target_titles"] = []
    client.put("/api/profile", json=body)
    after = client.get("/api/profile").json()
    assert after["candidate"]["city"] == "Delhi"
    assert after["candidate"]["target_titles"] == []
