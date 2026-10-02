"""Job sources. Every source uses a public, documented JSON endpoint — no login, no CAPTCHA bypass.

- greenhouse / lever / ashby: companies' own public job-board APIs (config/companies.yaml)
- arbeitnow: Europe-focused board (free API)
- remotive: remote jobs (free API; many are "Worldwide" = workable from India)
- adzuna: aggregator covering India, UK, EU, Canada, Australia (free key: developer.adzuna.com)
"""

from __future__ import annotations

import concurrent.futures as cf
import html
import logging
import os
from collections.abc import Callable, Iterable
from datetime import UTC, datetime

import httpx
from bs4 import BeautifulSoup

from ..config import Company, companies
from ..models import Job

log = logging.getLogger(__name__)
UA = {"User-Agent": "jobhunt/0.1 (personal job search tool)"}


def html_to_text(s: str | None) -> str:
    if not s:
        return ""
    return BeautifulSoup(html.unescape(s), "html.parser").get_text("\n", strip=True)


def _get(client: httpx.Client, url: str, **params):
    r = client.get(url, params=params or None, timeout=30)
    r.raise_for_status()
    return r.json()


def _ts(value) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, tz=UTC)
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


# ---------------------------------------------------------------- ATS boards


def greenhouse(client: httpx.Client, c: Company) -> list[Job]:
    data = _get(client, f"https://boards-api.greenhouse.io/v1/boards/{c.slug}/jobs", content="true")
    jobs = []
    for j in data.get("jobs", []):
        offices = ", ".join(o.get("name", "") for o in j.get("offices") or [])
        loc = (j.get("location") or {}).get("name", "")
        jobs.append(
            Job(
                source="greenhouse",
                external_id=str(j["id"]),
                company=c.name,
                title=j["title"].strip(),
                location=", ".join(x for x in (loc, offices) if x),
                url=j.get("absolute_url") or "",
                apply_url=f"https://job-boards.greenhouse.io/{c.slug}/jobs/{j['id']}",
                description=html_to_text(j.get("content")),
                posted_at=_ts(j.get("first_published") or j.get("updated_at")),
                ats="greenhouse",
                ats_slug=c.slug,
            )
        )
    return jobs


def lever(client: httpx.Client, c: Company) -> list[Job]:
    data = _get(client, f"https://api.lever.co/v0/postings/{c.slug}", mode="json")
    jobs = []
    for j in data:
        cat = j.get("categories") or {}
        locs = cat.get("allLocations") or [cat.get("location", "")]
        lists = "\n".join(
            f"{item.get('text', '')}\n{html_to_text(item.get('content'))}" for item in j.get("lists") or []
        )
        wp = (j.get("workplaceType") or "").lower() or None
        jobs.append(
            Job(
                source="lever",
                external_id=j["id"],
                company=c.name,
                title=j["text"].strip(),
                location=", ".join(filter(None, locs)),
                url=j.get("hostedUrl", ""),
                apply_url=j.get("applyUrl") or f"https://jobs.lever.co/{c.slug}/{j['id']}/apply",
                description="\n".join(filter(None, [j.get("descriptionPlain"), lists, j.get("additionalPlain")])),
                remote=(wp == "remote") if wp else None,
                workplace=wp,
                posted_at=_ts(j.get("createdAt")),
                ats="lever",
                ats_slug=c.slug,
            )
        )
    return jobs


def ashby(client: httpx.Client, c: Company) -> list[Job]:
    data = _get(client, f"https://api.ashbyhq.com/posting-api/job-board/{c.slug}")
    jobs = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        locs = [j.get("location", "")] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
        wp = (j.get("workplaceType") or "").lower() or None
        jobs.append(
            Job(
                source="ashby",
                external_id=j["id"],
                company=c.name,
                title=j["title"].strip(),
                location=", ".join(filter(None, locs)),
                url=j.get("jobUrl", ""),
                apply_url=j.get("applyUrl") or f"https://jobs.ashbyhq.com/{c.slug}/{j['id']}/application",
                description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
                remote=bool(j.get("isRemote")) or wp == "remote",
                workplace=wp,
                posted_at=_ts(j.get("publishedAt")),
                ats="ashby",
                ats_slug=c.slug,
            )
        )
    return jobs


ATS_FETCHERS: dict[str, Callable[[httpx.Client, Company], list[Job]]] = {
    "greenhouse": greenhouse,
    "lever": lever,
    "ashby": ashby,
}


def fetch_companies(client: httpx.Client, only: Iterable[str] | None = None) -> tuple[list[Job], list[str]]:
    targets = [c for c in companies() if not only or c.name.lower() in {o.lower() for o in only}]
    jobs: list[Job] = []
    errors: list[str] = []

    def run(c: Company) -> list[Job]:
        try:
            return ATS_FETCHERS[c.ats](client, c)
        except Exception as e:  # one broken board must not stop the run
            errors.append(f"{c.name} ({c.ats}/{c.slug}): {e}")
            return []

    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        for js in ex.map(run, targets):
            jobs.extend(js)
    return jobs, errors


# ---------------------------------------------------------------- aggregators


def arbeitnow(client: httpx.Client, pages: int = 5) -> list[Job]:
    jobs = []
    for page in range(1, pages + 1):
        data = _get(client, "https://www.arbeitnow.com/api/job-board-api", page=page)
        for j in data.get("data", []):
            jobs.append(
                Job(
                    source="arbeitnow",
                    external_id=j["slug"],
                    company=j.get("company_name", ""),
                    title=j.get("title", "").strip(),
                    location=j.get("location", ""),
                    url=j.get("url", ""),
                    description=html_to_text(j.get("description")),
                    remote=j.get("remote"),
                    posted_at=_ts(j.get("created_at")),
                    extra={"tags": j.get("tags"), "visa_sponsorship": j.get("visa_sponsorship")},
                )
            )
        if not (data.get("links") or {}).get("next"):
            break
    return jobs


def remotive(client: httpx.Client) -> list[Job]:
    data = _get(client, "https://remotive.com/api/remote-jobs", category="software-dev")
    return [
        Job(
            source="remotive",
            external_id=str(j["id"]),
            company=j.get("company_name", ""),
            title=j.get("title", "").strip(),
            location=j.get("candidate_required_location") or "Worldwide",
            url=j.get("url", ""),
            description=html_to_text(j.get("description")),
            remote=True,
            workplace="remote",
            posted_at=_ts(j.get("publication_date")),
        )
        for j in data.get("jobs", [])
    ]


ADZUNA_COUNTRIES = {
    "in": "India",
    "gb": "United Kingdom",
    "de": "Germany",
    "nl": "Netherlands",
    "ie": "Ireland",
    "fr": "France",
    "ca": "Canada",
    "au": "Australia",
}
ADZUNA_QUERIES = [
    "senior software engineer",
    "lead engineer",
    "staff engineer",
    "backend engineer .net",
    "golang engineer",
    "solution architect",
]


def adzuna(client: httpx.Client) -> list[Job]:
    from ..config import settings

    st = settings()
    app_id = st.get("adzuna_app_id") or os.environ.get("ADZUNA_APP_ID")
    app_key = st.get("adzuna_app_key") or os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        log.info("adzuna: ADZUNA_APP_ID/ADZUNA_APP_KEY not set, skipping")
        return []
    jobs = []
    for cc, cname in ADZUNA_COUNTRIES.items():
        for q in ADZUNA_QUERIES:
            try:
                data = _get(
                    client,
                    f"https://api.adzuna.com/v1/api/jobs/{cc}/search/1",
                    app_id=app_id,
                    app_key=app_key,
                    what=q,
                    results_per_page=50,
                    max_days_old=30,
                    content_type="application/json",
                )
            except httpx.HTTPError as e:
                log.warning("adzuna %s/%s: %s", cc, q, e)
                continue
            for j in data.get("results", []):
                loc = (j.get("location") or {}).get("display_name", "")
                jobs.append(
                    Job(
                        source="adzuna",
                        external_id=str(j["id"]),
                        company=(j.get("company") or {}).get("display_name", ""),
                        title=j.get("title", "").strip(),
                        location=f"{loc}, {cname}" if cname.lower() not in loc.lower() else loc,
                        url=j.get("redirect_url", ""),
                        description=html_to_text(j.get("description")),
                        posted_at=_ts(j.get("created")),
                    )
                )
    return jobs


AGGREGATORS: dict[str, Callable[[httpx.Client], list[Job]]] = {
    "arbeitnow": arbeitnow,
    "remotive": remotive,
    "adzuna": adzuna,
}


def fetch_all(sources: Iterable[str] | None = None) -> tuple[list[Job], list[str]]:
    sources = set(sources or ["companies", *AGGREGATORS])
    jobs: list[Job] = []
    errors: list[str] = []
    with httpx.Client(headers=UA, follow_redirects=True) as client:
        if "companies" in sources:
            js, errs = fetch_companies(client)
            jobs += js
            errors += errs
        for name, fn in AGGREGATORS.items():
            if name in sources:
                try:
                    jobs += fn(client)
                except Exception as e:
                    errors.append(f"{name}: {e}")
    return jobs, errors
