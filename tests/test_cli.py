from typer.testing import CliRunner

import jobhunt.services
from jobhunt.cli import app


def test_scrape_suggests_make_targets(monkeypatch):
    def fake_run_search(progress, sources=None, use_claude=None):
        return {"errors": [], "decisions": {}, "fetched": 0, "new": 0, "claude_used": False}

    monkeypatch.setattr(jobhunt.services, "run_search", fake_run_search)
    result = CliRunner().invoke(app, ["scrape"])
    assert result.exit_code == 0, result.output
    assert "make run" in result.output
    assert "make list" in result.output
    assert "./jh" not in result.output
