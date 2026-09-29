"""Stage orchestration shared by the app and the CLI. Each step saves progress per competitor
so a failure part-way through loses nothing."""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from .. import store
from ..export import excel, pptx
from ..llm import LLM
from ..models import Candidate, Project
from . import collect as _collect
from . import discover as _discover
from . import score as _score
from . import synthesize as _synth

log = logging.getLogger(__name__)
Progress = Callable[[str], None]


def _noop(_: str) -> None:
    pass


@contextmanager
def _timed(p: Project, stage: str):
    """Accumulate machine time per stage for ROI tracking (PDD appendix: turnaround manual vs AI)."""
    t = time.time()
    try:
        yield
    finally:
        p.metrics[stage] = round(p.metrics.get(stage, 0.0) + time.time() - t, 1)


def approved(p: Project) -> list[Candidate]:
    return [c for c in p.candidates if c.status in ("accepted", "edited")]


def discover(p: Project, llm: LLM, names=None, feedback: str = "", progress: Progress = _noop) -> None:
    with _timed(p, "discovery"):
        _discover_impl(p, llm, names, feedback, progress)


def _discover_impl(p: Project, llm: LLM, names, feedback: str, progress: Progress) -> None:
    progress("Searching and reading sources for competitors…")
    p.candidates += _discover.find_competitors(p, llm, feedback=feedback, progress=progress)
    progress(f"{len(p.candidates)} candidates. Proposing comparison features…")
    if not p.features:  # never overwrite a feature list the analyst may have edited at Gate 1
        p.features = _discover.propose_features(p, llm)
    p.stage = "gate1"
    store.save(p)


def reverify(p: Project) -> int:
    """Re-run the quote check on every stored citation (cheap, no network). Keeps old projects
    consistent after verifier improvements. Returns how many flags changed."""
    from ..research.corpus import numbers_supported, verify
    changed = 0
    flag = "⚠️ The figure in this value does not appear in the quoted evidence — check it."
    for rec in p.competitors:
        cites = [c for cell in [*rec.cells.values(), *rec.pricing.values(), *rec.swot.values()] for c in cell.citations]
        cites += [c for f in rec.features for c in f.citations]
        for c in cites:
            ok = verify(rec.source(c.source_id), c.quote)
            if ok != c.verified:
                c.verified, changed = ok, changed + 1
        # a verified quote must also back the figure in the value (only unreviewed cells are touched)
        for cell in (*rec.cells.values(), *rec.pricing.values()):
            if cell.confidence in ("high", "medium") and cell.status == "proposed" and flag not in cell.note and \
                    numbers_supported(cell.value, [c.quote for c in cell.citations if c.verified]) is False:
                cell.confidence, cell.note, changed = "low", f"{flag} {cell.note}".strip(), changed + 1
    return changed


def approve_candidates(p: Project, names: list[str] | None = None) -> None:
    for c in p.candidates:
        if c.status == "proposed" and (names is None or c.name in names):
            c.status = "accepted"
    p.add_log(f"gate1: approved {[c.name for c in approved(p)]}")


def collect(p: Project, llm: LLM, names=None, feedback: str = "", progress: Progress = _noop) -> None:
    with _timed(p, "collection"):
        _collect_impl(p, llm, names, feedback, progress)


def _collect_impl(p: Project, llm: LLM, names, feedback: str, progress: Progress) -> None:
    todo = [c for c in approved(p) if (names is None or c.name in names)]
    for i, cand in enumerate(todo, 1):
        if names is None and p.record(cand.name) and p.record(cand.name).cells:
            continue  # already collected; re-run by naming it explicitly
        progress(f"[{i}/{len(todo)}] Researching {cand.name}…")
        try:
            rec = _collect.collect(cand, p.intake, llm, progress=progress)
        except Exception as e:  # keep going; the analyst sees the failure in the log
            log.exception("collect failed for %s", cand.name)
            p.add_log(f"collect FAILED for {cand.name}: {e}")
            progress(f"  failed: {e}")
            continue
        p.competitors = [r for r in p.competitors if r.name != cand.name] + [rec]
        p.add_log(f"collected {cand.name}: {len(rec.sources)} sources via {getattr(llm, 'last_model', '')}")
        store.save(p)
    p.stage = "gate2"
    store.save(p)


def score(p: Project, llm: LLM, names=None, feedback: str = "", progress: Progress = _noop) -> None:
    with _timed(p, "scoring"):
        _score_impl(p, llm, names, feedback, progress)


def _score_impl(p: Project, llm: LLM, names, feedback: str, progress: Progress) -> None:
    for rec in p.active():
        if names and rec.name not in names:
            continue
        progress(f"Scoring features for {rec.name}…")
        try:
            new = _score.score(rec, p.features, p.intake, llm, feedback=feedback)
            scored = [f for f in new if f.score is not None]
            progress(f"   {len(scored)}/{len(new)} features scored · "
                     f"{sum(1 for f in scored if any(c.verified for c in f.citations))} with verified evidence · "
                     f"{len(new) - len(scored)} marked '?' (no evidence)")
        except Exception as e:
            p.add_log(f"score FAILED for {rec.name}: {e}")
            progress(f"  failed: {e}")
            continue
        # keep analyst-adjudicated scores; replace the rest
        keep = {f.feature: f for f in rec.features if f.status in ("accepted", "edited") and not names}
        rec.features = [keep.get(f.feature, f) for f in new]
        store.save(p)


def synthesize(p: Project, llm: LLM, names=None, feedback: str = "", progress: Progress = _noop) -> None:
    with _timed(p, "synthesis"):
        _synthesize_impl(p, llm, names, feedback, progress)


def _synthesize_impl(p: Project, llm: LLM, names, feedback: str, progress: Progress) -> None:
    for rec in p.active():
        if names and rec.name not in names:
            continue
        progress(f"SWOT, Voice of Customer and battlecard for {rec.name}…")
        try:
            _synth.synthesize_competitor(rec, p.intake, llm, feedback=feedback)
            progress(f"   SWOT done · {len(rec.voc)} verified customer quotes kept")
        except Exception as e:
            p.add_log(f"synthesis FAILED for {rec.name}: {e}")
            progress(f"  failed: {e}")
        store.save(p)
    if not names:
        progress("Cross-competitor insights…")
        p.insights = _synth.synthesize_insights(p, llm, feedback=feedback)
    p.stage = "gate3"
    store.save(p)


def export(p: Project) -> list[Path]:
    out = store.output_dir(p.id)
    base = f"{p.id}"
    paths = [excel.export(p, out / f"{base} Competitive Analysis.xlsx"),
             pptx.export_deck(p, out / f"{base} Insight Deck.pptx"),
             pptx.export_battlecards(p, out / f"{base} Battlecards.pptx")]
    p.stage = "export"
    p.add_log("exported " + ", ".join(x.name for x in paths))
    return paths


def roi(p: Project) -> dict:
    """ROI tracking variables (PDD appendix) and the README success measures, from project data."""
    comps = p.active()
    cells = [c for r in comps for c in (*r.cells.values(), *r.pricing.values())]
    cites = [x for c in cells for x in c.citations]
    feats = [f for r in comps for f in r.features if f.score is not None]
    reviewed = [f for f in feats if f.status in ("accepted", "edited", "rejected")]
    domains = {s.url.split("/")[2] for r in comps for s in r.sources if not s.url.startswith("search://")}
    machine = sum(p.metrics.values())
    return {
        "machine_minutes_total": round(machine / 60, 1),
        "machine_minutes_by_stage": {k: round(v / 60, 1) for k, v in p.metrics.items()},
        "competitors": len(comps),
        "inputs_per_project": len(cells) + len(feats),
        "sources_total": sum(len(r.sources) for r in comps),
        "sources_per_competitor": round(sum(len(r.sources) for r in comps) / len(comps), 1) if comps else 0,
        "distinct_domains": len(domains),
        "quotes_verified_pct": round(100 * sum(x.verified for x in cites) / len(cites)) if cites else None,
        "cells_unavailable": sum(1 for c in cells if c.confidence == "unavailable"),
        "cells_edited": sum(1 for c in cells if c.status == "edited"),
        "cells_rejected": sum(1 for c in cells if c.status == "rejected"),
        "scores_reviewed": len(reviewed),
        # success measure: >=80% of AI-drafted scores accepted (with light edits) by end of pilot
        "scores_accepted_pct": round(100 * sum(f.status == "accepted" for f in reviewed) / len(reviewed)) if reviewed else None,
    }
