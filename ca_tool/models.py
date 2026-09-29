"""Core data model.

Every AI-proposed value is a `Cell`: value + citations + confidence + review status.
This is what makes the three approval gates possible.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low", "unavailable"]
ReviewStatus = Literal["proposed", "accepted", "edited", "rejected"]
CompetitorType = Literal["direct", "indirect", "substitute"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Source(BaseModel):
    """A page fetched by the research layer. The AI can only cite these."""
    id: str
    url: str
    title: str = ""
    kind: str = "web"          # website | search | review | news | funding | ...
    text: str = ""             # extracted text (truncated) used for quote verification
    fetched_at: str = Field(default_factory=now)


class Citation(BaseModel):
    source_id: str
    url: str = ""
    quote: str = ""
    verified: bool = False     # quote found in the fetched page text


class Cell(BaseModel):
    value: str = ""
    citations: list[Citation] = []
    confidence: Confidence = "low"
    note: str = ""             # assumption / proxy used, per PDD "Data unavailable" exception
    status: ReviewStatus = "proposed"
    analyst_note: str = ""

    @property
    def verified(self) -> bool:
        return any(c.verified for c in self.citations)


class Intake(BaseModel):
    """Inputs from the Datadvise process doc §2 / PDD step 1."""
    client_name: str
    product: str                                   # client's product/service
    positioning: str = ""
    target_markets: str = ""                       # markets and customer segments
    geographies: str = ""
    known_competitors: list[str] = []
    dimensions: str = ""                           # competitive dimensions of interest
    business_goals: str = ""                       # differentiation, messaging, GTM, pricing...
    notes: str = ""


class Candidate(BaseModel):
    name: str
    website: str = ""
    type: CompetitorType = "direct"
    segment: str = ""                              # market segment it was found in
    justification: str = ""
    size_group: str = ""                           # e.g. "Enterprise (1000+ employees)"
    geography: str = ""
    citations: list[Citation] = []
    status: ReviewStatus = "proposed"
    analyst_note: str = ""


class FeatureDef(BaseModel):
    category: str
    name: str
    description: str = ""


class FeatureScore(BaseModel):
    feature: str
    category: str
    standard: Optional[bool] = None                # tier availability, None = unknown
    premium: Optional[bool] = None
    enterprise: Optional[bool] = None
    score: Optional[float] = None                  # 0–5, None = "?" (could not assess)
    rationale: str = ""
    citations: list[Citation] = []
    confidence: Confidence = "low"
    status: ReviewStatus = "proposed"
    analyst_note: str = ""


class Quote(BaseModel):
    text: str
    sentiment: Literal["positive", "negative"]
    citation: Citation


class CompetitorRecord(BaseModel):
    name: str
    website: str = ""
    type: CompetitorType = "direct"
    sources: list[Source] = []
    # keyed by metric/field key from knowledge.template
    cells: dict[str, Cell] = {}
    pricing: dict[str, Cell] = {}                  # tiers, fees, trial
    features: list[FeatureScore] = []
    swot: dict[str, Cell] = {}                     # strengths/weaknesses/opportunities/threats
    voc: list[Quote] = []
    narrative: Cell = Cell()                       # "X is winning in Y due to Z"
    battlecard: Cell = Cell()                      # how the client wins against this competitor
    collected_at: str = ""

    def source(self, sid: str) -> Optional[Source]:
        return next((s for s in self.sources if s.id == sid), None)


class Insights(BaseModel):
    executive_summary: Cell = Cell()
    white_space: Cell = Cell()
    trends: Cell = Cell()
    implications: Cell = Cell()                    # opportunities + threats for client
    status: ReviewStatus = "proposed"


Stage = Literal["intake", "gate1", "collection", "gate2", "synthesis", "gate3", "export"]


class Project(BaseModel):
    id: str
    intake: Intake
    stage: Stage = "intake"
    candidates: list[Candidate] = []
    discovery_sources: list[Source] = []
    features: list[FeatureDef] = []
    competitors: list[CompetitorRecord] = []
    insights: Insights = Insights()
    metrics: dict[str, float] = {}                 # machine seconds per stage (ROI tracking, PDD appendix)
    log: list[str] = []
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)

    def record(self, name: str) -> Optional[CompetitorRecord]:
        return next((c for c in self.competitors if c.name == name), None)

    def add_log(self, msg: str) -> None:
        self.log.append(f"{now()} {msg}")
