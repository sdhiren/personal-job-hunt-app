from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Job:
    source: str  # greenhouse | lever | ashby | arbeitnow | remotive | adzuna
    external_id: str
    company: str
    title: str
    location: str
    url: str
    description: str = ""
    apply_url: str | None = None
    remote: bool | None = None  # True when the source explicitly says remote
    workplace: str | None = None  # remote | hybrid | onsite (when the source says)
    posted_at: datetime | None = None
    ats: str | None = None  # ATS we know how to auto-fill (greenhouse | lever | ashby)
    ats_slug: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.source}:{self.ats_slug or self.company}:{self.external_id}".lower()


@dataclass
class Evaluation:
    region: str  # india | europe | canada | australia | remote_global | other
    is_wfh: bool
    preferred_city: bool
    visa: str  # yes | likely | no | unknown | n/a
    rating: float | None
    kw_score: int
    llm_score: int | None
    score: int
    decision: str  # apply | review | reject
    reasons: list[str]
