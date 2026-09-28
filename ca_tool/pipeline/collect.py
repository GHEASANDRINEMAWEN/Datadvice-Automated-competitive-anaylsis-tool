"""Phase 2 – Data collection (PDD steps 5–9).

For each approved competitor: read its own site (home, about, pricing, product, customers,
partners, news, careers), run targeted searches (reviews, funding, press, LinkedIn,
partnerships), then have the AI fill every template metric with citations. Feeds Gate 2.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel

from ..knowledge.sources import classify, domain, fetchable, site_name
from ..knowledge.template import ALL_METRICS, METRIC_BY_KEY, PRICING, Metric
from ..llm import LLM
from ..models import Candidate, Cell, Citation, CompetitorRecord, Intake, now
from ..research.corpus import Corpus
from ..research.web import KEY_PAGE_PATTERNS, fetch, guessed_pages, key_pages, mentions, rank_hits, search

log = logging.getLogger(__name__)

SYSTEM = (
    "You are a Datadvise competitive-intelligence analyst filling the Competitive Analysis template. "
    "Use ONLY the numbered sources. Every non-empty value must cite source ids with a short quote copied "
    "verbatim from that source's body text (max ~25 words; never quote page titles). Do NOT use your own "
    "background knowledge: if a fact is not in the source text, it is unavailable. Prefer the company's own site for facts about the company "
    "and third-party sources (reviews, news, funding databases) for opinions and numbers. "
    "If the sources do not contain the answer, set confidence to 'unavailable', value to 'Undisclosed', "
    "and in note say what proxy could be used. Overview facts (year, HQ, employees, geographies) are short. "
    "Analysis rows are written like a consulting report: 2-4 specific sentences with names, numbers and "
    "dates (e.g. products launched, partner names, amounts raised, review themes with platform ratings)."
)

PRICING_BY_KEY = {m.key: m for m in PRICING}


class _Cite(BaseModel):
    source_id: str
    quote: str


class _Val(BaseModel):
    key: str
    value: str
    confidence: Literal["high", "medium", "low", "unavailable"]
    note: str
    citations: list[_Cite]


class _CollectOut(BaseModel):
    values: list[_Val]


def resolve_website(name: str) -> str:
    for h in search(f"{name} official website", max_results=5):
        d = domain(h.url)
        if not any(x in d for x in ("linkedin", "g2.com", "capterra", "crunchbase", "wikipedia", "facebook", "youtube")):
            return f"https://{d}"
    return ""


def research_queries(name: str, site: str) -> list[tuple[str, str]]:
    d = domain(site) if site else ""
    n = f'"{name}"'
    return [
        ("review", f"{n} reviews G2 Capterra"),
        ("review", f"{n} reviews pros cons"),
        ("funding", f"{n} funding raised investors Crunchbase"),
        ("news", f"{n} announces press release"),
        ("company", f"{n} LinkedIn headquarters founded employees"),
        ("company", f"{n} partnership integration {d}".strip()),
        ("company", f"{n} pricing plans"),
    ]


def _noop(_: str) -> None:
    pass


def build_corpus(name: str, site: str, max_external: int = 10, progress=_noop) -> Corpus:
    corpus = Corpus(prefix="S")
    # 1. competitor's own site (PDD step 6)
    if site:
        progress(f"🌐 Reading {name}'s website: {site}")
        home = fetch(site)
        if home:
            corpus.add(home.url, home.title or f"{name} homepage", home.text, kind="website")
            pages = list(key_pages(home).items())
            missing = [k for k in KEY_PAGE_PATTERNS if k not in dict(pages)]
            pages += guessed_pages(home.url, missing)
            with ThreadPoolExecutor(max_workers=8) as ex:
                fetched = list(ex.map(lambda kv: fetch(kv[1]), pages))
            got: set[str] = set()
            for (kind, _), pg in zip(pages, fetched):
                # one page per kind; skip soft-404s that redirect back to the homepage
                if pg and kind not in got and len(pg.text) > 200 and pg.url.rstrip("/") != home.url.rstrip("/"):
                    if corpus.add(pg.url, pg.title or f"{name} {kind}", pg.text, kind="website"):
                        got.add(kind)
            progress(f"   read {1 + len(got)} pages on their site ({', '.join(sorted(got)) or 'homepage only'})")
        else:
            progress("   ⚠️ website could not be read")
    # 2. third-party sources (PDD steps 7–8)
    hits = []
    for _, q in research_queries(name, site):
        progress(f"🔎 Searching: {q}")
        hits += search(q, max_results=6)
    own = domain(site) if site else "\x00"
    # keep hits about this company (drops e.g. LinkedIn's own page or a database homepage)
    hits = [h for h in rank_hits(hits) if domain(h.url) != own and mentions(f"{h.title} {h.snippet} {h.url}", name)]
    snippets = "\n".join(f"- {h.title}: {h.snippet} ({h.url})" for h in hits[:30])
    corpus.add(f"search://{name}", f"Web search results about {name}", snippets, kind="search")
    per_site: dict[str, int] = {}
    chosen = []
    for h in hits:
        site = site_name(h.url)
        if fetchable(h.url) and per_site.get(site, 0) < 2:  # blocked review sites: snippets only
            per_site[site] = per_site.get(site, 0) + 1
            chosen.append(h)
    with ThreadPoolExecutor(max_workers=6) as ex:
        fetched = list(ex.map(lambda h: fetch(h.url), chosen[: max_external * 2]))
    added = 0
    for h, pg in zip(chosen, fetched):
        if pg and len(pg.text) > 300 and added < max_external:
            # a third-party page must actually mention the company
            if mentions(pg.text, name):
                if corpus.add(pg.url, pg.title or h.title, pg.text):
                    added += 1
                    progress(f"📄 Read ({classify(pg.url)[0]}): {pg.url[:100]}")
    progress(f"   {len(corpus.sources)} sources collected")
    return corpus


def _metric_lines(metrics: list[Metric]) -> str:
    return "\n".join(f"- {m.key}: {m.label} — {m.question}" for m in metrics)


def extract(name: str, intake: Intake, corpus: Corpus, metrics: list[Metric], llm: LLM,
            feedback: str = "") -> dict[str, Cell]:
    prompt = f"""Competitor being analysed: {name}
Context: our client ({intake.client_name}) sells {intake.product} to {intake.target_markets}.
Answer from the perspective of an analyst comparing {name} against the client.

Fill one value per metric key below (return exactly these keys):
{_metric_lines(metrics)}
{"Analyst feedback to address in this re-run: " + feedback if feedback else ""}

SOURCES
{corpus.render()}
"""
    out = llm.generate_json(prompt, _CollectOut, system=SYSTEM)
    wanted = {m.key for m in metrics}
    cells: dict[str, Cell] = {}
    for v in out.values:
        if v.key not in wanted:
            continue
        cites = corpus.resolve([Citation(source_id=c.source_id, quote=c.quote) for c in v.citations])
        conf = v.confidence
        if conf != "unavailable" and not any(c.verified for c in cites):
            conf = "low"  # no verified evidence -> cannot be medium/high, whatever the model says
        cells[v.key] = Cell(value=v.value, citations=cites, confidence=conf, note=v.note)
    for k in wanted - cells.keys():
        cells[k] = Cell(value="Undisclosed", confidence="unavailable", note="Not returned by the model; needs manual research.")
    return cells


def collect(candidate: Candidate, intake: Intake, llm: LLM, progress=_noop) -> CompetitorRecord:
    site = candidate.website
    if not site:
        progress(f"🔎 Finding {candidate.name}'s official website…")
        site = resolve_website(candidate.name)
    corpus = build_corpus(candidate.name, site, progress=progress)
    rec = CompetitorRecord(name=candidate.name, website=site, type=candidate.type)
    progress(f"🤖 AI is filling {len(ALL_METRICS + PRICING)} template fields from these sources…")
    cells = extract(candidate.name, intake, corpus, ALL_METRICS + PRICING, llm)
    cites = [c for cell in cells.values() for c in cell.citations]
    progress(f"✅ Checked the AI's quotes against the pages: {sum(c.verified for c in cites)}/{len(cites)} found word for word · "
             f"{sum(1 for c in cells.values() if c.confidence == 'unavailable')} fields unavailable")
    rec.pricing = {k: cells.pop(k) for k in PRICING_BY_KEY}
    rec.cells = cells
    rec.sources = corpus.sources
    rec.collected_at = now()
    return rec


def rerun(rec: CompetitorRecord, intake: Intake, keys: list[str], feedback: str, llm: LLM) -> None:
    """Gate 2 'send back': targeted extra search driven by the analyst's feedback, then re-extract."""
    corpus = Corpus(prefix="S", sources=rec.sources)
    if feedback:
        for h in rank_hits(search(f'"{rec.name}" {feedback}', max_results=6))[:4]:
            pg = fetch(h.url)
            if pg:
                corpus.add(pg.url, pg.title or h.title, pg.text)
    metrics = [METRIC_BY_KEY.get(k) or PRICING_BY_KEY[k] for k in keys]
    new = extract(rec.name, intake, corpus, metrics, llm, feedback=feedback)
    for k, cell in new.items():
        target = rec.pricing if k in PRICING_BY_KEY else rec.cells
        cell.analyst_note = f"Re-run: {feedback}" if feedback else "Re-run"
        target[k] = cell
    rec.sources = corpus.sources
