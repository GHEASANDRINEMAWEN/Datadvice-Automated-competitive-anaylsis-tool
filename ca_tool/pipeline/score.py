"""Phase 3a – Feature comparison scored with the Datadvise 0–5 scoring guide (PDD step 10)."""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel

from ..knowledge.scoring import guide_text
from ..llm import LLM
from ..models import Citation, CompetitorRecord, FeatureDef, FeatureScore, Intake
from ..research.corpus import Corpus

SYSTEM = (
    "You are a Datadvise product analyst scoring competitor features. Apply the Datadvise Feature "
    "Scoring Guide strictly and objectively, without bias toward the client. Use ONLY the numbered "
    "sources. Each score must cite evidence with a verbatim quote (max ~25 words). If the sources say "
    "nothing about a feature, return score null (shown as '?') and confidence 'unavailable' — do NOT "
    "guess 0; 0 means the sources show the feature is absent."
)


class _Cite(BaseModel):
    source_id: str
    quote: str


class _Score(BaseModel):
    id: str
    feature: str
    standard: Optional[bool]
    premium: Optional[bool]
    enterprise: Optional[bool]
    score: Optional[int]
    rationale: str
    confidence: Literal["high", "medium", "low", "unavailable"]
    citations: list[_Cite]


class _ScoreOut(BaseModel):
    scores: list[_Score]


def score(rec: CompetitorRecord, features: list[FeatureDef], intake: Intake, llm: LLM,
          feedback: str = "", only: list[str] | None = None) -> list[FeatureScore]:
    feats = [f for f in features if not only or f.name in only]
    ids = {f"F{i}": f for i, f in enumerate(feats, 1)}
    corpus = Corpus(prefix="S", sources=rec.sources)
    tiers = rec.pricing.get("pricing_tiers")
    prompt = f"""Competitor: {rec.name}
Known pricing tiers: {tiers.value if tiers else "unknown"}

{guide_text()}

For each feature below return: tier availability (standard / premium / enterprise: true, false, or null
if unknown; if the product has a single plan, use standard), a score 0-5 (or null), a one-to-two sentence
rationale naming the scoring-guide level (the "context note"), confidence, and citations.
Return one entry per feature below, with its id (F1, F2, ...) exactly as given:
{chr(10).join(f"- id={fid} | {f.category} | {f.name}: {f.description}" for fid, f in ids.items())}
{"Analyst feedback to address in this re-score: " + feedback if feedback else ""}

SOURCES
{corpus.render()}
"""
    out = llm.generate_json(prompt, _ScoreOut, system=SYSTEM)
    by_id = {s.id.strip().upper(): s for s in out.scores}
    by_name = {_key(s.feature): s for s in out.scores}
    results, matched = [], 0
    for fid, f in ids.items():
        s = by_id.get(fid) or by_name.get(_key(f.name)) or next(
            (v for k, v in by_name.items() if _key(f.name) and _key(f.name) in k), None)
        matched += s is not None
        if not s:
            results.append(FeatureScore(feature=f.name, category=f.category, confidence="unavailable",
                                        rationale="Not returned by the model; needs manual review."))
            continue
        cites = corpus.resolve([Citation(source_id=c.source_id, quote=c.quote) for c in s.citations])
        val = None if s.score is None else float(max(0, min(5, s.score)))
        verified = any(c.verified for c in cites)
        rationale = s.rationale
        if val == 0 and not verified:
            # "not found" is not "absent" (scoring guide 0 = shown to be absent). The pilot showed
            # unsupported zeros were the largest source of disagreement with analysts.
            val, rationale = None, f"No evidence found either way — needs checking. (AI suggested 0: {s.rationale})"
        conf = s.confidence if (verified or s.confidence == "unavailable") else "low"
        results.append(FeatureScore(feature=f.name, category=f.category, standard=s.standard, premium=s.premium,
                                    enterprise=s.enterprise, score=val, rationale=rationale,
                                    citations=cites, confidence=conf,
                                    analyst_note=f"Re-score: {feedback}" if feedback else ""))
    if feats and matched < len(feats) / 2:
        # never silently return a matrix of blanks
        raise ValueError(f"scoring output could not be matched to features ({matched}/{len(feats)})")
    return results


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", re.sub(r"^\[[^\]]*\]", "", name.lower())).strip()
