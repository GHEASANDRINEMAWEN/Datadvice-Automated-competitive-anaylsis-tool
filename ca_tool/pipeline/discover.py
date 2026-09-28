"""Phase 1 – Define the competitive scope (PDD steps 2–4).

Searches for competitors, reads the best pages, and asks the AI for 8–20 cited candidates
plus a proposed set of comparison features. Output feeds Gate 1.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel

from ..llm import LLM
from ..models import Candidate, Citation, FeatureDef, Intake, Project
from ..research.corpus import Corpus
from ..research.web import fetch, rank_hits, search

log = logging.getLogger(__name__)

SYSTEM = (
    "You are a senior competitive-intelligence analyst at Datadvise. You only state facts supported "
    "by the numbered sources provided. Every claim must cite a source id and include a short quote "
    "copied verbatim from that source. Never invent sources, URLs or quotes."
)


class _Cite(BaseModel):
    source_id: str
    quote: str


class _Cand(BaseModel):
    name: str
    website: str
    type: Literal["direct", "indirect", "substitute"]
    justification: str
    size_group: str
    geography: str
    citations: list[_Cite]


class _DiscoveryOut(BaseModel):
    candidates: list[_Cand]


class _Feat(BaseModel):
    category: str
    name: str
    description: str


class _FeaturesOut(BaseModel):
    features: list[_Feat]


def queries(intake: Intake) -> list[str]:
    p, m = intake.product, intake.target_markets
    qs = [
        f"top competitors {p} {m}".strip(),
        f"best {p} software {m}".strip(),
        f"{p} alternatives G2",
        f"{p} Capterra comparison",
    ]
    for k in intake.known_competitors[:5]:
        qs.append(f"{k} competitors alternatives")
    if intake.client_name:
        qs.append(f"{intake.client_name} competitors")
    return qs


def build_corpus(intake: Intake, pages_to_read: int = 10, feedback: str = "", progress=lambda _: None) -> Corpus:
    hits = []
    qs = queries(intake) + ([f"{intake.product} {feedback}"] if feedback else [])
    for q in qs:
        progress(f"🔎 Searching: {q}")
        hits += search(q, max_results=8)
    hits = rank_hits(hits)
    corpus = Corpus(prefix="D")
    # search snippets are a cheap source in their own right
    snippet_text = "\n".join(f"- {h.title}: {h.snippet} ({h.url})" for h in hits[:40])
    corpus.add("search://discovery", "Web search results (titles and snippets)", snippet_text, kind="search")
    with ThreadPoolExecutor(max_workers=6) as ex:
        pages = list(ex.map(lambda h: fetch(h.url), hits[:pages_to_read * 2]))
    added = 0
    for h, pg in zip(hits, pages):
        if pg and len(pg.text) > 400 and added < pages_to_read:
            if corpus.add(pg.url, pg.title or h.title, pg.text):
                added += 1
                progress(f"📄 Read: {pg.url[:100]}")
    return corpus


def find_competitors(project: Project, llm: LLM, feedback: str = "", target: str = "8-20",
                     progress=lambda _: None) -> list[Candidate]:
    it = project.intake
    corpus = build_corpus(it, feedback=feedback, progress=progress)
    progress(f"🤖 AI is proposing competitors from {len(corpus.sources)} sources…")
    rejected = [c.name for c in project.candidates if c.status == "rejected"]
    kept = [c.name for c in project.candidates if c.status in ("accepted", "edited")]
    prompt = f"""CLIENT INTAKE
Client: {it.client_name}
Client product/service: {it.product}
Positioning: {it.positioning}
Target markets & segments: {it.target_markets}
Geographies: {it.geographies}
Known/suspected competitors: {", ".join(it.known_competitors) or "none given"}
Dimensions of interest: {it.dimensions}
Business goals: {it.business_goals}

TASK
Propose a preliminary list of {target} competitors of the client (do NOT include the client itself).
Include direct competitors (same product, same buyers), indirect competitors (different product, same need)
and substitutes. Include the known competitors if the sources support them.
For each: official website (homepage URL), type, one-line justification of why it competes with the client,
a size group (e.g. "Startup (<50 employees)", "Scale-up (50-500)", "Enterprise (500+)") and main geography
(use "Unknown" if the sources do not say), and 1-2 citations with verbatim quotes.
{"Already approved by the analyst (keep, do not repeat): " + ", ".join(kept) if kept else ""}
{"Rejected by the analyst (do NOT propose again): " + ", ".join(rejected) if rejected else ""}
{"Analyst feedback for this re-run: " + feedback if feedback else ""}

SOURCES
{corpus.render()}
"""
    out = llm.generate_json(prompt, _DiscoveryOut, system=SYSTEM)
    existing = {c.name.lower() for c in project.candidates}
    new = []
    for c in out.candidates:
        if c.name.lower() in existing or c.name.lower() == it.client_name.lower():
            continue
        cites = corpus.resolve([Citation(source_id=x.source_id, quote=x.quote) for x in c.citations])
        new.append(Candidate(name=c.name, website=c.website, type=c.type, justification=c.justification,
                             size_group=c.size_group, geography=c.geography, citations=cites))
    # client-named competitors are always in scope (PDD step 1), even if sources were thin
    names = existing | {c.name.lower() for c in new}
    for k in it.known_competitors:
        if not any(k.lower() in n or n in k.lower() for n in names):
            new.insert(0, Candidate(name=k, type="direct", justification="Named by the client in intake.",
                                    analyst_note="Added from intake; website to be confirmed."))
    project.discovery_sources = corpus.sources
    project.add_log(f"discovery: {len(new)} new candidates via {getattr(llm, 'last_model', llm.name)}")
    return new


MIN_FEATURES = 15


def propose_features(project: Project, llm: LLM) -> list[FeatureDef]:
    """Comparison dimensions for the Feature Comparison sheet (confirmed by the analyst at Gate 1).
    The reference matrix (Prismm) has ~50 features in 5 categories; we ask for 20-40."""
    it = project.intake
    corpus = Corpus(prefix="D", sources=project.discovery_sources)
    prompt = f"""The client sells: {it.product}. Positioning: {it.positioning}. Markets: {it.target_markets}.
Dimensions the client cares about: {it.dimensions or "not specified"}.
Competitors under consideration: {", ".join(c.name for c in project.candidates if c.status != "rejected")}.

Propose the feature list for a competitor Feature Comparison matrix.
- 5-6 categories, which MUST include "Analytics & Reporting", "Integrations" and "Support & Services",
  plus 2-3 categories for the core product capabilities of this market.
- Between 20 and 40 features in total, at least 4 per category.
- Concrete, checkable features that buyers in this market compare on (not vague qualities).
- Feature names short (2-6 words); description = one sentence on what evidence to look for.

Market context from sources:
{corpus.render(max_chars=30000)}
"""
    feats: list[_Feat] = []
    for _ in range(2):
        feats = llm.generate_json(prompt, _FeaturesOut, system=SYSTEM).features
        if len(feats) >= MIN_FEATURES:
            break
        prompt += f"\n\nYour previous answer had only {len(feats)} features. Return at least 20."
    seen, out = set(), []
    for f in feats:
        if f.name.lower() not in seen:
            seen.add(f.name.lower())
            out.append(FeatureDef(category=f.category, name=f.name, description=f.description))
    return out
