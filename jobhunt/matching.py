"""Rule-based filtering + scoring: region, WFH, visa sponsorship, company rating, resume match."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from .config import company_index, extra_ratings, profile
from .config import skills as profile_skills
from .models import Evaluation, Job

# ---------------------------------------------------------------- locations

INDIA = [
    "india",
    "bengaluru",
    "bangalore",
    "pune",
    "gurugram",
    "gurgaon",
    "delhi",
    "noida",
    "hyderabad",
    "chennai",
    "mumbai",
    "kolkata",
    "ahmedabad",
    "kochi",
    "jaipur",
    "chandigarh",
    "ghaziabad",
    "faridabad",
    "trivandrum",
    "thiruvananthapuram",
    "coimbatore",
    "indore",
]
EUROPE = [
    "europe",
    "emea",
    "united kingdom",
    "uk",
    "england",
    "london",
    "manchester",
    "edinburgh",
    "ireland",
    "dublin",
    "germany",
    "berlin",
    "munich",
    "münchen",
    "hamburg",
    "frankfurt",
    "cologne",
    "köln",
    "stuttgart",
    "düsseldorf",
    "netherlands",
    "amsterdam",
    "rotterdam",
    "utrecht",
    "the hague",
    "eindhoven",
    "france",
    "paris",
    "spain",
    "madrid",
    "barcelona",
    "portugal",
    "lisbon",
    "porto",
    "sweden",
    "stockholm",
    "gothenburg",
    "denmark",
    "copenhagen",
    "norway",
    "oslo",
    "finland",
    "helsinki",
    "poland",
    "warsaw",
    "krakow",
    "kraków",
    "wroclaw",
    "austria",
    "vienna",
    "switzerland",
    "zurich",
    "zürich",
    "geneva",
    "belgium",
    "brussels",
    "italy",
    "milan",
    "rome",
    "czech",
    "prague",
    "estonia",
    "tallinn",
    "lithuania",
    "vilnius",
    "latvia",
    "riga",
    "romania",
    "bucharest",
    "hungary",
    "budapest",
    "greece",
    "athens",
    "luxembourg",
    "serbia",
    "belgrade",
    "croatia",
    "zagreb",
    "cyprus",
    "malta",
    "bulgaria",
    "sofia",
    "slovakia",
    "slovenia",
    "remote - de",
    "remote (de)",
]
CANADA = [
    "canada",
    "toronto",
    "vancouver",
    "montreal",
    "montréal",
    "ottawa",
    "calgary",
    "waterloo",
    "edmonton",
    "winnipeg",
    "halifax",
    "quebec",
    "ontario",
    "british columbia",
    "alberta",
]
AUSTRALIA = [
    "australia",
    "sydney",
    "melbourne",
    "brisbane",
    "perth",
    "adelaide",
    "canberra",
    "hobart",
    "new south wales",
    "nsw",
    "victoria, au",
    "queensland",
]
GLOBAL_REMOTE = ["worldwide", "anywhere", "global", "remote - global", "remote (global)"]
REGION_WORDS = {
    "india": INDIA,
    "europe": EUROPE,
    "canada": CANADA,
    "australia": AUSTRALIA,
    "remote_global": GLOBAL_REMOTE,
}


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", text) is not None


def regions_for(location: str) -> list[str]:
    loc = location.lower()
    return [r for r, words in REGION_WORDS.items() if any(_has_word(loc, w) for w in words)]


REMOTE_RE = re.compile(
    r"\bremote\b|work from home|\bwfh\b|work from anywhere|fully[- ]distributed"
    r"|remote[- ]first|distributed team",
    re.I,
)
HYBRID_RE = re.compile(r"\bhybrid\b|\d+ days? (a|per) week in (the )?office|in[- ]office \d", re.I)
ONSITE_RE = re.compile(r"\bon[- ]?site\b|\bin[- ]office\b|work from (the )?office|\bwfo\b", re.I)


def is_wfh(job: Job) -> bool:
    if job.workplace:
        return job.workplace == "remote"
    if job.remote:
        return True
    if REMOTE_RE.search(job.location):
        return True
    head = job.description[:3000]
    return bool(REMOTE_RE.search(head)) and not HYBRID_RE.search(head) and not ONSITE_RE.search(head)


# ---------------------------------------------------------------- visa

VISA_NO = re.compile(
    r"(not|unable to|cannot|can't|can not|don't|do not|won't|will not|are not able to)\s+"
    r"(be able to\s+)?(provide|offer|support|sponsor)\w*\s*(any\s+)?(visa|work permit|immigration|sponsorship)"
    r"|(no|without)\s+(visa\s+)?sponsorship"
    r"|sponsorship\s+(is\s+)?(not\s+(available|provided|offered|possible))"
    r"|must\s+(already\s+)?(have|hold|possess)\s+(the\s+|a\s+|full\s+|valid\s+|existing\s+)*"
    r"(right|authori[sz]ation|eligibility|permission|work permit)"
    r"|(existing|current|valid)\s+right to work"
    r"|(eu|uk|canadian|australian)\s+(citizenship|residency|work permit)\s+(is\s+)?required"
    r"|not\s+eligible\s+for\s+(visa\s+)?sponsorship",
    re.I,
)
VISA_YES = re.compile(
    r"visa\s+sponsorship\s+(is\s+)?(available|provided|offered|possible|supported)"
    r"|(we|will|can|happy to|able to)\s+(also\s+)?(provide\s+|offer\s+)?sponsor"
    r"|sponsor(ship)?\s+(of\s+)?(your|a|the|work|employment)\s+(work\s+)?(visa|permit)"
    r"|(visa|immigration|relocation)\s+(support|assistance|package|sponsorship|help)"
    r"|relocation\s+(bonus|budget|allowance|benefits?)"
    r"|help\s+(you\s+)?(with\s+)?(your\s+)?relocat"
    r"|(we|will)\s+(support|help)\s+(you\s+)?(with\s+)?(your\s+)?(relocation|visa|move)"
    r"|blue\s*card|highly\s+skilled\s+migrant|kennismigrant|skilled\s+worker\s+visa"
    r"|global\s+talent\s+(stream|visa)|tss\s+visa|482\s+visa|lmia",
    re.I,
)


def visa_status(job: Job, known_sponsor: bool) -> str:
    text = f"{job.title}\n{job.description}"
    if job.extra.get("visa_sponsorship") is True:
        return "yes"
    if VISA_NO.search(text):
        return "no"
    if VISA_YES.search(text):
        return "yes"
    return "likely" if known_sponsor else "unknown"


# ---------------------------------------------------------------- company rating


def company_rating(job: Job) -> tuple[float | None, bool]:
    idx = company_index()
    c = idx.get(job.company.lower())
    if c:
        return c.rating, c.known_sponsor
    if job.extra.get("rating"):
        return round(float(job.extra["rating"]), 1), False  # Claude's estimate from its web search
    name = job.company.lower()
    for key, rating in extra_ratings().items():
        if key in name:
            return rating, False
    return None, False


# ---------------------------------------------------------------- keyword match score

SENIOR_RE = re.compile(r"\b(senior|sr\.?|staff|lead|principal|architect|manager|head)\b", re.I)
FOCUS_RE = re.compile(
    r"backend|back[- ]end|platform|infrastructure|distributed|full[- ]?stack|cloud|"
    r"\bai\b|\bml\b|llm|genai|devops|sre|reliability|data platform|\.net|golang|\bgo\b|api",
    re.I,
)
STACK_WORDS = [
    "java",
    "scala",
    "kotlin",
    "ruby",
    "rails",
    "php",
    "c++",
    "rust",
    "elixir",
    "swift",
    "react native",
    "salesforce",
    "sap",
    "abap",
    "mainframe",
    "cobol",
    "python",
    "golang",
    ".net",
    "c#",
    "node.js",
    "react",
    "angular",
    "flutter",
    "unity",
]


@lru_cache(maxsize=1)
def _compiled_skills(key: int):
    sk = profile_skills()
    mine = " ".join(f"{s.name} {s.pattern}".lower() for s in sk)
    return [(s.name, re.compile(s.pattern, re.I), s.weight) for s in sk], mine


def _skills():
    return _compiled_skills(id(profile()))[0]


def _foreign_stack(title: str) -> str | None:
    """A main language/platform in the title that the candidate doesn't list as a skill."""
    t = title.lower()
    mine = _compiled_skills(id(profile()))[1]
    for w in STACK_WORDS:
        if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", t) and w not in mine:
            if any(re.search(p.pattern, title) for _, p, _ in _skills()):
                return None  # title also names one of your skills (e.g. "Java/Go")
            return w
    return None


YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?years?", re.I)


def keyword_score(job: Job) -> tuple[int, list[str]]:
    text = f"{job.title}\n{job.description}"
    reasons: list[str] = []

    title = 0
    if SENIOR_RE.search(job.title):
        title += 20
    if FOCUS_RE.search(job.title):
        title += 15
    elif re.search(r"software|engineer|developer", job.title, re.I):
        title += 8

    matched, total = [], 0
    for name, rx, weight in _skills():
        total += weight
        if rx.search(text):
            matched.append((name, weight))
    got = sum(w for _, w in matched)
    # a JD rarely mentions all of the resume — 60% of the weight is already a full skills score
    skills = min(55, round(55 * got / (0.6 * total))) if total else 25  # no skills yet: neutral
    if matched:
        reasons.append("skills: " + ", ".join(m for m, _ in sorted(matched, key=lambda x: -x[1])[:8]))

    years_needed = [int(m.group(1)) for m in YEARS_RE.finditer(job.description[:6000]) if 1 <= int(m.group(1)) <= 25]
    exp = 10
    if years_needed:
        need = max(years_needed)
        mine = int(profile()["candidate"].get("years_experience") or 0) or 99
        exp = 10 if need <= mine else 3
        if need < 4:
            exp = 4  # probably too junior
            reasons.append(f"asks only {need}y experience")

    # primary language in the title that isn't one of yours
    penalty = 0
    other = _foreign_stack(job.title)
    if other:
        penalty = 20
        reasons.append(f"title stack is {other}")
    return max(0, min(100, title + skills + exp - penalty)), reasons


# ---------------------------------------------------------------- decision


def title_allowed(title: str) -> bool:
    s = profile()["search"]
    if not any(re.search(p, title, re.I) for p in s["title_include"]):
        return False
    return not any(re.search(p, title, re.I) for p in s["title_exclude"])


def evaluate(
    job: Job,
    llm_score: int | None = None,
    llm_notes: list[str] | None = None,
    llm_visa: str | None = None,
    llm_remote: str | None = None,
) -> Evaluation:
    p = profile()
    mcfg, ccfg = p["matching"], p["company"]
    reasons: list[str] = []

    regions = [r for r in regions_for(job.location) if r in p["search"]["regions"] or r == "remote_global"]
    wfh = is_wfh(job)
    if llm_remote == "remote":
        wfh = True
    elif llm_remote in ("hybrid", "onsite") and not job.workplace:
        wfh = False
    # "Remote, Worldwide" is workable from India -> treat as India WFH
    region = (
        "india"
        if "india" in regions
        else "remote_global"
        if "remote_global" in regions and wfh
        else next((r for r in regions if r != "remote_global"), "other")
    )
    preferred = region == "india" and any(
        _has_word(job.location.lower(), c) for c in p["search"]["india_preferred_cities"]
    )

    rating, known_sponsor = company_rating(job)
    abroad = region in ("europe", "canada", "australia")
    visa = visa_status(job, known_sponsor) if abroad else "n/a"
    if abroad and visa in ("unknown", "likely") and llm_visa in ("yes", "no"):
        visa = llm_visa
    if abroad and wfh and visa == "likely":
        visa = "unknown"  # remote roles abroad almost always need existing right to work

    kw, kw_reasons = keyword_score(job)
    reasons += kw_reasons
    score = llm_score if llm_score is not None else kw
    if preferred:
        score = min(100, score + 3)
        reasons.append("preferred city")
    if llm_notes:
        reasons += llm_notes

    def done(decision: str, why: str) -> Evaluation:
        return Evaluation(region, wfh, preferred, visa, rating, kw, llm_score, score, decision, [why, *reasons])

    # hard filters
    if not title_allowed(job.title):
        return done("reject", "title not a fit")
    if region == "other":
        return done("reject", f"location out of scope: {job.location or '?'}")
    max_age = p["search"].get("max_age_days")
    if max_age and job.posted_at and job.posted_at < datetime.now(UTC) - timedelta(days=max_age):
        return done("reject", "posting too old")
    if abroad and visa == "no":
        return done("reject", "JD says no visa sponsorship")

    # match threshold (India on-site/hybrid needs a strong match)
    need = mcfg["min_score"]
    if region == "india" and not wfh:
        need = mcfg["strong_match_score"]
    if score < need:
        note = " (India non-WFH needs strong match)" if need > mcfg["min_score"] else ""
        return done("reject", f"score {score} < {need}{note}")
    strong = score >= mcfg["strong_match_score"]

    # company rating (flexible for strong matches)
    if rating is None:
        if ccfg["unknown_rating_policy"] == "reject":
            return done("reject", "company rating unknown")
        return done("review", "company rating unknown — check Glassdoor")
    if rating < ccfg["flexible_min_rating"] or (rating < ccfg["min_rating"] and not strong):
        return done("reject", f"company rating {rating} too low")

    if abroad and visa not in p["visa"]["accept"]:
        return done("review", f"visa sponsorship {visa} — confirm before applying")

    tag = "WFH" if wfh else ("on-site/hybrid, strong match" if region == "india" else f"visa: {visa}")
    return done("apply", f"{region} · {tag} · rating {rating}")
