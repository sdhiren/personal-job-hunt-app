from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv
from psycopg.conninfo import make_conninfo

ROOT = Path(os.environ.get("JOBHUNT_HOME", Path(__file__).resolve().parent.parent))
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
SQLITE_PATH = DATA_DIR / "jobhunt.db"  # the pre-Postgres store, kept for `jobhunt import-sqlite`
SCREENSHOT_DIR = DATA_DIR / "screenshots"
RESUME_DIR = DATA_DIR / "resume"
BROWSER_PROFILE_DIR = Path(os.environ.get("JOBHUNT_BROWSER_PROFILE", DATA_DIR / "browser-profile"))
DEFAULT_PROFILE_PATH = CONFIG_DIR / "profile.yaml"  # template shipped with the app
PROFILE_PATH = DATA_DIR / "profile.yaml"  # the user's own profile (edited in the app)
SETTINGS_PATH = DATA_DIR / "settings.json"  # Claude connection etc. (chmod 600)

# .env holds the database password and ports (see .env.example). Real environment variables win, so
# Docker's own settings for the app container aren't overridden. Quoting follows docker compose: wrap a
# value in single quotes if it contains `$`.
load_dotenv(ROOT / ".env", override=False, interpolate=False)


def database_conninfo() -> str:
    """How to reach PostgreSQL: DATABASE_URL if set, otherwise the POSTGRES_* settings.

    Built with psycopg's make_conninfo, which quotes each value, so passwords may contain any character
    (a hand-built postgresql:// URL breaks on `@`, `:`, `/` or `#`).
    """
    if url := os.environ.get("DATABASE_URL"):
        return url
    env = os.environ.get
    return make_conninfo(
        host=env("POSTGRES_HOST", "localhost"),
        port=env("POSTGRES_PORT", "5432"),
        user=env("POSTGRES_USER", "jobhunt"),
        password=env("POSTGRES_PASSWORD", "jobhunt"),
        dbname=env("POSTGRES_DB", "jobhunt"),
    )


@dataclass(frozen=True)
class Company:
    name: str
    ats: str
    slug: str
    rating: float | None = None
    known_sponsor: bool = False


@dataclass(frozen=True)
class Skill:
    name: str
    pattern: str
    weight: int


def ensure_dirs() -> None:
    for d in (DATA_DIR, SCREENSHOT_DIR, RESUME_DIR, BROWSER_PROFILE_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


# ---------------------------------------------------------------- profile


@lru_cache
def profile() -> dict:
    """Template defaults overlaid with the user's saved profile."""
    base = _load_yaml(DEFAULT_PROFILE_PATH)
    return _merge(base, _load_yaml(PROFILE_PATH)) if PROFILE_PATH.exists() else base


def save_profile(data: dict) -> dict:
    ensure_dirs()
    merged = _merge(profile(), data)
    if "skills" in data.get("matching", {}):
        merged["matching"]["skills"] = data["matching"]["skills"]  # lists replace, never merge
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(merged, f, sort_keys=False, allow_unicode=True)
    profile.cache_clear()
    resume_text.cache_clear()
    return profile()


def skill_pattern(name: str, aliases: list[str] | None = None) -> str:
    terms = [name, *(aliases or [])]
    return "|".join(rf"(?<![a-z0-9]){re.escape(t.strip().lower())}(?![a-z0-9])" for t in terms if t.strip())


def skills() -> list[Skill]:
    raw = profile().get("matching", {}).get("skills") or []
    if isinstance(raw, dict):  # legacy {regex: weight}
        return [Skill(p.split("|")[0].strip("\\b()?-:i"), p, int(w)) for p, w in raw.items()]
    return [
        Skill(s["name"], s.get("pattern") or skill_pattern(s["name"], s.get("aliases")), int(s.get("weight", 2)))
        for s in raw
        if s.get("name")
    ]


def resume_path() -> Path | None:
    p = profile().get("candidate", {}).get("resume_path")
    if not p:
        return None
    path = Path(os.path.expanduser(p))
    path = path if path.is_absolute() else ROOT / path
    return path if path.exists() else None


@lru_cache
def resume_text() -> str:
    p = resume_path()
    if not p:
        return ""
    return extract_text(p)


def extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    if path.suffix.lower() == ".docx":
        import zipfile

        xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8", "ignore")
        return re.sub(r"<[^>]+>", " ", xml.replace("</w:p>", "\n"))
    return path.read_text(encoding="utf-8", errors="ignore")


# ---------------------------------------------------------------- settings (Claude connection)

DEFAULT_SETTINGS = {
    "claude_mode": "account",  # account (Claude Pro/Max via Claude Code) | api_key | off
    "api_key": "",
    "api_model": "claude-opus-5",
    "cli_model": "",  # blank = Claude Code's default for your plan
    "use_claude_discovery": True,  # web-search for jobs beyond the company boards
    "use_claude_scoring": True,  # re-score the shortlist against your resume
    "use_claude_answers": True,  # draft answers to free-text application questions
    "discovery_per_region": 10,
    "sources": {"companies": True, "arbeitnow": True, "remotive": True, "adzuna": False},
    "adzuna_app_id": "",
    "adzuna_app_key": "",
}


def settings() -> dict:
    if SETTINGS_PATH.exists():
        return _merge(DEFAULT_SETTINGS, json.loads(SETTINGS_PATH.read_text()))
    return copy.deepcopy(DEFAULT_SETTINGS)


def save_settings(data: dict) -> dict:
    ensure_dirs()
    merged = _merge(settings(), data)
    SETTINGS_PATH.write_text(json.dumps(merged, indent=2))
    os.chmod(SETTINGS_PATH, 0o600)
    return merged


# ---------------------------------------------------------------- companies


@lru_cache
def _companies_file() -> dict:
    return _load_yaml(CONFIG_DIR / "companies.yaml")


def companies() -> list[Company]:
    return [Company(**c) for c in _companies_file().get("companies", [])]


def company_index() -> dict[str, Company]:
    return {c.name.lower(): c for c in companies()}


def extra_ratings() -> dict[str, float]:
    return {k.lower(): float(v) for k, v in (_companies_file().get("ratings") or {}).items()}
