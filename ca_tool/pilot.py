"""Pilot: compare a tool run against a completed manual engagement (PDD weeks 8–9).

The manual deliverables live only in the git-ignored `reference_private/` folder. This module
reads them LOCALLY (never sent to the AI) into a baseline, then compares a tool project against it:
competitor recall, overview-fact agreement, feature-score agreement, sources and turnaround.

  python -m ca_tool.pilot baseline <workbook.xlsx> <deck.pptx> --out <baseline.json>
  python -m ca_tool.pilot compare <project_id> <baseline.json>
"""
from __future__ import annotations

import argparse
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter

from . import store
from .pipeline import runner

MANUAL_DAYS = (7, 9)          # SOP §7: typical landscape of 3–5 competitors
WORKDAY_HOURS = 8


def _norm(s: str) -> str:
    s = re.sub(r"\(.*?\)", "", str(s or "")).lower()
    s = re.sub(r"\b(inc|ltd|llc|the|by \w+|acquired by \w+)\b", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def same_company(a: str, b: str) -> bool:
    x, y = _norm(a), _norm(b)
    if not x or not y:
        return False
    return x == y or (min(len(x), len(y)) >= 5 and (x in y or y in x)) or SequenceMatcher(None, x, y).ratio() >= 0.85


def same_feature(a: str, b: str) -> float:
    wa = set(re.findall(r"[a-z0-9]+", a.lower())) - {"and", "the", "of", "in", "with", "tools", "tool"}
    wb = set(re.findall(r"[a-z0-9]+", b.lower())) - {"and", "the", "of", "in", "with", "tools", "tool"}
    if not wa or not wb:
        return 0.0
    return max(len(wa & wb) / len(wa | wb), SequenceMatcher(None, a.lower(), b.lower()).ratio() - 0.25)


# ------------------------------------------------------------------ baseline extraction (local)

def _cell(ws, ref: str):
    v = ws[ref].value
    return str(v).strip() if v is not None else ""


def baseline_from_workbook(path: Path) -> dict:
    wb = load_workbook(path, data_only=True)
    out: dict = {"competitors": [], "facts": {}, "scores": {}}
    # Company Analysis: header row with competitor names from column D
    ws = next((wb[n] for n in wb.sheetnames if n.strip().lower() == "company analysis"), None)
    if ws is not None:
        hdr_row = next(r for r in range(1, 10) if _cell(ws, f"B{r}").lower() == "metric")
        names = {}
        for col in range(4, ws.max_column + 1):
            v = ws.cell(hdr_row, col).value
            if v and str(v).strip():
                names[col] = str(v).strip()
        client = names.pop(4, None)  # first column is the client itself in the reference layout
        out["client"] = client
        out["competitors"] = list(dict.fromkeys(names.values()))
        for r in range(hdr_row + 1, min(ws.max_row, hdr_row + 40) + 1):
            label = _cell(ws, f"B{r}")
            if not label:
                continue
            for col, name in names.items():
                v = ws.cell(r, col).value
                if v and str(v).strip():
                    out["facts"].setdefault(name, {})[label] = str(v).strip()[:600]
    # Feature Comparison: one block per competitor (Standard/Premium/Enterprise/Score, then notes).
    # Hand-filled sheets aren't perfectly aligned, so the score is the first real number in the block.
    ws = next((wb[n] for n in wb.sheetnames if n.strip().lower() == "feature comparison"), None)
    if ws is not None:
        name_row = 6
        starts = [col for col in range(column_index_from_string("D"), ws.max_column + 1)
                  if ws.cell(name_row, col).value and "context" not in str(ws.cell(name_row, col).value).lower()]
        blocks = []
        for i, col in enumerate(starts):
            end = min(col + 4, (starts[i + 1] - 1) if i + 1 < len(starts) else col + 4)
            blocks.append((str(ws.cell(name_row, col).value).strip(), range(col, end + 1)))
        cat = ""
        for r in range(name_row + 1, ws.max_row + 1):
            a, b = _cell(ws, f"A{r}"), _cell(ws, f"B{r}")
            if a.lower().startswith("scoring guide"):
                break
            if a:
                cat = a
            if not b or b.lower().startswith(("feature type", "pricing", "standard", "trial", "rationale", "company description")):
                continue
            for name, cols in blocks:
                # bool is a subclass of int: TRUE/FALSE tier flags must not be read as scores
                v = next((ws.cell(r, c).value for c in cols
                          if isinstance(ws.cell(r, c).value, (int, float)) and not isinstance(ws.cell(r, c).value, bool)), None)
                if v is not None and 0 <= v <= 5:
                    out["scores"].setdefault(name, {})[b] = {"category": cat, "score": float(v)}
    return out


def baseline_from_deck(path: Path) -> dict:
    """'<Company> Overview' slides: Foundation / Headquarter / Geographies / # of employee(s)."""
    from pptx import Presentation
    facts: dict = {}
    keys = {"foundation": "founding_year", "headquarter": "headquarters", "geographies": "geographies",
            "# of employee": "employees", "# of employees": "employees"}
    for slide in Presentation(path).slides:
        texts = [sh.text_frame.text.strip() for sh in slide.shapes if sh.has_text_frame and sh.text_frame.text.strip()]
        title = next((t for t in texts if t.lower().endswith(" overview")), None)
        if not title:
            continue
        name = title[: -len(" overview")].strip()
        # values follow their label, either in the same box or in the next one
        flat = [line.strip() for t in texts for line in t.split("\n") if line.strip()]
        for i, line in enumerate(flat[:-1]):
            k = keys.get(line.lower())
            if k and k not in facts.get(name, {}):
                facts.setdefault(name, {})[k] = flat[i + 1]
    return facts


def build_baseline(workbook: Path, deck: Path) -> dict:
    b = baseline_from_workbook(workbook)
    b["overview"] = baseline_from_deck(deck)
    b["deck_competitors"] = list(b["overview"])
    return b


# ------------------------------------------------------------------ comparison

def _year(s: str) -> str:
    m = re.search(r"(19|20)\d{2}", s or "")
    return m.group(0) if m else ""


def _emp_range(s: str) -> tuple[float, float] | None:
    """Headcount as (low, high). Only an explicit range ('51-200', '1,000–5,000') or the figure
    tied to 'employees'/'staff' counts; years and other numbers in the text are ignored."""
    num = lambda x: float(x.replace(",", ""))
    m = re.search(r"(\d[\d,]*)\s*(?:-|–|to)\s*(\d[\d,]*)", s or "")   # ranges first: "1001-2000"
    if m:
        return num(m.group(1)), num(m.group(2))
    s = re.sub(r"\b(19|20)\d{2}\b", " ", s or "")           # then drop years, e.g. "(LinkedIn, 2024)"
    m = re.search(r"(\d[\d,]*)\s*\+?\s*(?:employees|staff|people|team members)", s, re.I) or \
        re.fullmatch(r"\D*(\d[\d,]*)\s*\+?\D*", s)
    if m:
        v = num(m.group(1))
        return (v, v * 10 if "+" in s else v)
    return None


def fact_agrees(key: str, manual: str, tool: str) -> bool | None:
    if not manual or not tool or tool.lower().startswith(("undisclosed", "n.a")) or manual.lower() in ("n.a", "n/a"):
        return None
    if key == "founding_year":
        return _year(manual) == _year(tool) if _year(manual) and _year(tool) else None
    if key == "employees":
        a, b = _emp_range(manual), _emp_range(tool)
        if not a or not b:
            return None
        # strict: ranges must overlap; single figures within ±25% (a pilot must not flatter the tool)
        if a[0] == a[1] and b[0] == b[1]:
            return abs(a[0] - b[0]) <= 0.25 * max(a[0], b[0])
        return a[0] <= b[1] and b[0] <= a[1]
    generic = {"usa", "united", "states", "state", "the", "and", "with", "including", "countries", "region", "regions"}
    words = lambda x: set(re.findall(r"[a-z]{3,}", x.lower())) - generic
    m, t = words(manual), words(tool)
    if key == "headquarters":
        # the more specific place named in the manual value (the city: first word group) must appear
        first = [w for w in re.findall(r"[a-z]{3,}", manual.lower().split(",")[0]) if w not in generic]
        if first and len(manual.split(",")) > 1:
            return all(w in t for w in first)
        return bool(m) and m <= t
    return bool(m & t)


def compare(pid: str, baseline: dict) -> dict:
    p = store.load(pid)
    manual: list[str] = []
    client = baseline.get("client", "")
    for m in baseline.get("competitors", []) + baseline.get("deck_competitors", []) + list(baseline.get("scores", {})):
        if client and same_company(m, client):
            continue
        if not any(same_company(m, x) for x in manual):  # workbook and deck spell names differently
            manual.append(m)
    found = [c.name for c in p.candidates]
    matched = {m: next((f for f in found if same_company(m, f)), None) for m in manual}
    new = [f for f in found if not any(same_company(f, m) for m in manual)]

    facts = []
    for rec in p.active():
        mname = next((m for m in baseline.get("overview", {}) if same_company(m, rec.name)), None)
        if not mname:
            continue
        for key, mval in baseline["overview"][mname].items():
            cell = rec.cells.get(key)
            facts.append({"competitor": rec.name, "field": key, "manual": mval, "tool": cell.value if cell else "",
                          "verified": bool(cell and cell.verified), "agrees": fact_agrees(key, mval, cell.value if cell else "")})

    scores = []
    for rec in p.active():
        mname = next((m for m in baseline.get("scores", {}) if same_company(m, rec.name)), None)
        if not mname:
            continue
        for fs in rec.features:
            if fs.score is None:
                continue
            best = max(baseline["scores"][mname].items(), key=lambda kv: same_feature(fs.feature, kv[0]), default=None)
            if best and same_feature(fs.feature, best[0]) >= 0.5:
                scores.append({"competitor": rec.name, "tool_feature": fs.feature, "manual_feature": best[0],
                               "tool": fs.score, "manual": best[1]["score"], "diff": abs(fs.score - best[1]["score"])})

    decided = [f for f in facts if f["agrees"] is not None]
    r = runner.roi(p)
    return {
        "project": pid,
        "competitor_recall": {"manual_total": len(manual), "found": sum(1 for v in matched.values() if v),
                              "matched": matched, "new_candidates": new},
        "facts": facts,
        "facts_agree": f"{sum(f['agrees'] for f in decided)}/{len(decided)}" if decided else "n/a",
        "scores": scores,
        "scores_exact": sum(1 for s in scores if s["diff"] == 0),
        "scores_within_1": sum(1 for s in scores if s["diff"] <= 1),
        "turnaround": {"tool_machine_minutes": r["machine_minutes_total"],
                       "manual_hours": [d * WORKDAY_HOURS for d in MANUAL_DAYS]},
        "roi": r,
    }


def report_md(res: dict) -> str:
    rc = res["competitor_recall"]
    lines = [f"# Pilot comparison – project `{res['project']}`", "",
             "Local report: contains content from confidential reference deliverables. Do not commit or share.", "",
             "## Competitor discovery recall",
             f"Tool found **{rc['found']} of {rc['manual_total']}** competitors listed in the manual deliverables.", ""]
    lines += [f"- {'✅' if v else '❌'} {m}" + (f" → `{v}`" if v else "") for m, v in rc["matched"].items()]
    lines += ["", f"New candidates not in the manual list ({len(rc['new_candidates'])}): " + ", ".join(rc["new_candidates"]), "",
              f"## Overview facts (agree: {res['facts_agree']})", "", "| Competitor | Field | Manual | Tool | Quote verified | Agrees |", "|---|---|---|---|---|---|"]
    for f in res["facts"]:
        mark = {True: "✅", False: "❌", None: "–"}[f["agrees"]]
        lines.append(f"| {f['competitor']} | {f['field']} | {f['manual'][:40]} | {f['tool'][:40]} | {'yes' if f['verified'] else 'no'} | {mark} |")
    sc = res["scores"]
    lines += ["", f"## Feature scores ({len(sc)} matched features: {res['scores_exact']} exact, {res['scores_within_1']} within 1 point)", "",
              "| Competitor | Tool feature | Manual feature | Tool | Manual |", "|---|---|---|---|---|"]
    lines += [f"| {s['competitor']} | {s['tool_feature']} | {s['manual_feature']} | {s['tool']:g} | {s['manual']:g} |" for s in sc]
    t = res["turnaround"]
    lines += ["", "## Turnaround and ROI variables",
              f"- Tool machine time: **{t['tool_machine_minutes']} min** (plus analyst review at the gates)",
              f"- Manual process: {t['manual_hours'][0]}–{t['manual_hours'][1]} working hours (SOP: 7–9 business days)", ""]
    lines += [f"- {k}: {v}" for k, v in res["roi"].items()]
    return "\n".join(lines)


def scorecheck(pid: str, baseline: dict, llm=None) -> dict:
    """Re-score the project's competitors on the MANUAL feature list (names + categories only;
    Datadvise's own taxonomy, no client facts) in a copy of the project, then compare exactly.
    Answers: given the same features, does the tool score like the analysts?"""
    from .llm import get_llm
    from .models import FeatureDef
    llm = llm or get_llm()
    src = store.load(pid)
    manual_scores = baseline.get("scores", {})
    feats: dict[str, FeatureDef] = {}
    for per in manual_scores.values():
        for name, v in per.items():
            feats.setdefault(name, FeatureDef(category=v["category"], name=name))
    copy = src.model_copy(deep=True)
    copy.id = f"{pid}-scorecheck"
    copy.features = list(feats.values())
    copy.metrics = {}
    for rec in copy.competitors:
        rec.features = []
    store.save(copy)
    runner.score(copy, llm, progress=lambda m: print(m, flush=True))
    store.save(copy)
    rows = []
    for rec in copy.competitors:
        mname = next((m for m in manual_scores if same_company(m, rec.name)), None)
        if not mname:
            continue
        for fs in rec.features:
            m = manual_scores[mname].get(fs.feature)
            if m is not None and fs.score is not None:
                rows.append({"competitor": rec.name, "feature": fs.feature, "tool": fs.score, "manual": m["score"],
                             "diff": abs(fs.score - m["score"]), "verified": any(c.verified for c in fs.citations)})
    n = len(rows)
    return {"rows": rows, "n": n,
            "unscored": sum(1 for r in copy.competitors for f in r.features if f.score is None),
            "exact": sum(r["diff"] == 0 for r in rows), "within1": sum(r["diff"] <= 1 for r in rows),
            "mean_abs_diff": round(sum(r["diff"] for r in rows) / n, 2) if n else None,
            "by_competitor": {c: {"n": len(v), "within1": sum(r["diff"] <= 1 for r in v)}
                              for c in {r["competitor"] for r in rows}
                              for v in [[r for r in rows if r["competitor"] == c]]}}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="ca_tool.pilot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("baseline")
    b.add_argument("workbook")
    b.add_argument("deck")
    b.add_argument("--out", required=True)
    c = sub.add_parser("compare")
    c.add_argument("project")
    c.add_argument("baseline")
    s = sub.add_parser("scorecheck")
    s.add_argument("project")
    s.add_argument("baseline")
    a = ap.parse_args(argv)
    if a.cmd == "scorecheck":
        import logging
        logging.getLogger("google_genai").setLevel(logging.ERROR)
        res = scorecheck(a.project, json.loads(Path(a.baseline).read_text(encoding="utf-8")))
        out = store.output_dir(a.project) / "pilot_scorecheck.json"
        out.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1))
        print(f"saved {out}")
        return
    if a.cmd == "baseline":
        data = build_baseline(Path(a.workbook), Path(a.deck))
        Path(a.out).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"baseline: {len(data['competitors'])} workbook competitors, {len(data['overview'])} deck overviews, "
              f"{sum(len(v) for v in data['scores'].values())} scores -> {a.out}")
    else:
        res = compare(a.project, json.loads(Path(a.baseline).read_text(encoding="utf-8")))
        out = store.output_dir(a.project) / "pilot_comparison.md"
        out.write_text(report_md(res), encoding="utf-8")
        print(report_md(res))
        print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
