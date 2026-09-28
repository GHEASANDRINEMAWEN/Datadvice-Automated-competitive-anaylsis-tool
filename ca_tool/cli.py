"""Command-line runner for the pipeline (the Streamlit app is the analyst UI; this is for
scripted runs and testing).

  python -m ca_tool.cli new --client "DemoCo" --product "..." --markets "..." --known "A,B"
  python -m ca_tool.cli discover <project>
  python -m ca_tool.cli approve <project> [--names "A,B"]     # Gate 1 shortcut (testing only)
  python -m ca_tool.cli collect <project> [--names "A"]
  python -m ca_tool.cli score <project>
  python -m ca_tool.cli synthesize <project>
  python -m ca_tool.cli export <project>
  python -m ca_tool.cli status <project>
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from . import store
from .llm import get_llm
from .models import Intake
from .pipeline import runner


def _names(s: str | None) -> list[str] | None:
    return [x.strip() for x in s.split(",") if x.strip()] if s else None


def status(pid: str) -> None:
    p = store.load(pid)
    print(f"{p.id}  stage={p.stage}  candidates={len(p.candidates)}  features={len(p.features)}  competitors={len(p.competitors)}")
    for c in p.candidates:
        print(f"  [{c.status:8}] {c.name} ({c.type}) {c.website}")
    for r in p.competitors:
        cells = list(r.cells.values()) + list(r.pricing.values())
        cites = [c for cell in cells for c in cell.citations]
        unavailable = sum(1 for c in cells if c.confidence == "unavailable")
        scored = sum(1 for f in r.features if f.score is not None)
        print(f"  {r.name}: {len(r.sources)} sources, {len(cells)} cells ({unavailable} unavailable), "
              f"{sum(c.verified for c in cites)}/{len(cites)} quotes verified, {scored}/{len(r.features)} features scored, "
              f"SWOT={'yes' if r.swot else 'no'}, VoC={len(r.voc)}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="ca_tool")
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--client", required=True)
    n.add_argument("--product", required=True)
    n.add_argument("--positioning", default="")
    n.add_argument("--markets", default="")
    n.add_argument("--geo", default="")
    n.add_argument("--known", default="")
    n.add_argument("--dimensions", default="")
    n.add_argument("--goals", default="")
    for cmd in ("discover", "approve", "collect", "score", "synthesize", "export", "status"):
        sp = sub.add_parser(cmd)
        sp.add_argument("project")
        sp.add_argument("--names", default=None)
        sp.add_argument("--feedback", default="")
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.v else logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("google_genai").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if a.cmd == "new":
        p = store.create(Intake(client_name=a.client, product=a.product, positioning=a.positioning, target_markets=a.markets,
                                geographies=a.geo, known_competitors=_names(a.known) or [], dimensions=a.dimensions,
                                business_goals=a.goals))
        print(p.id)
        return
    if a.cmd == "status":
        status(a.project)
        return

    p = store.load(a.project)
    t = time.time()
    if a.cmd == "approve":
        runner.approve_candidates(p, _names(a.names))
    else:
        llm = get_llm()
        step = {"discover": runner.discover, "collect": runner.collect, "score": runner.score,
                "synthesize": runner.synthesize}.get(a.cmd)
        if step:
            step(p, llm, names=_names(a.names), feedback=a.feedback, progress=lambda m: print(m, flush=True))
        elif a.cmd == "export":
            for path in runner.export(p):
                print(path)
    store.save(p)
    print(f"done in {time.time() - t:.0f}s")
    status(p.id)


if __name__ == "__main__":
    sys.exit(main())
