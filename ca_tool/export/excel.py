"""Populated Competitive Analysis workbook, laid out like `Prismm Comp Analysis v1.xlsx`:
Company Analysis (metric rows × competitor columns), Feature Comparison (Standard/Premium/
Enterprise/Score/Context Notes per competitor), Scoring Guide, Insights, Sources.

Citations are attached as cell comments; cell fill shows confidence / review status.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..knowledge.scoring import SCORING_GUIDE, label
from ..knowledge.template import ALL_METRICS, PRICING, SWOT_QUESTIONS, TIER_TERMINOLOGY
from ..models import Cell, Citation, Project

GREEN = PatternFill("solid", fgColor="D9EAD3")      # comp analysis colour in the reference workbook
HEAD = PatternFill("solid", fgColor="274E13")
AMBER = PatternFill("solid", fgColor="FFF2CC")       # low confidence / unverified
GREY = PatternFill("solid", fgColor="EFEFEF")        # unavailable
RED = PatternFill("solid", fgColor="F4CCCC")         # rejected at a gate
WHITE_BOLD = Font(bold=True, color="FFFFFF")
BOLD = Font(bold=True)
WRAP = Alignment(wrap_text=True, vertical="top")
THIN = Border(*(Side(style="thin", color="BBBBBB"),) * 4)


def _safe(v):
    """Text from the web/AI: drop characters Excel cannot store (they crash the export)."""
    return ILLEGAL_CHARACTERS_RE.sub("", v) if isinstance(v, str) else v


def _no_formulas(wb: Workbook) -> None:
    """Never let scraped text become a live formula ('=HYPERLINK(...)' from a page title etc.).
    The tool writes no formulas of its own, so every formula-typed cell is forced to plain text."""
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.data_type == "f":
                    c.data_type = "s"


def _cite_text(cites: list[Citation]) -> str:
    return "\n".join(f"[{c.source_id}]{' ✓' if c.verified else ' (unverified)'} {c.url}\n“{c.quote}”" for c in cites)


def _fill_for(cell: Cell) -> PatternFill | None:
    if cell.status == "rejected":
        return RED
    if cell.confidence == "unavailable":
        return GREY
    if cell.confidence == "low" or not cell.verified:
        return AMBER
    return None


def _put(ws, row: int, col: int, cell: Cell) -> None:
    c = ws.cell(row=row, column=col, value=_safe(cell.value))
    c.alignment, c.border = WRAP, THIN
    notes = []
    if cell.citations:
        notes.append(_cite_text(cell.citations))
    if cell.note:
        notes.append(f"Note: {cell.note}")
    if cell.analyst_note:
        notes.append(f"Analyst: {cell.analyst_note}")
    notes.append(f"Confidence: {cell.confidence} · Review: {cell.status}")
    c.comment = Comment(_safe("\n\n".join(notes)[:3000]), "Datadvise CA tool", width=420, height=240)
    fill = _fill_for(cell)
    if fill:
        c.fill = fill


def _header(ws, row: int, col: int, text: str, fill=HEAD, font=WHITE_BOLD) -> None:
    c = ws.cell(row=row, column=col, value=_safe(text))
    c.fill, c.font, c.alignment, c.border = fill, font, WRAP, THIN


def company_analysis(wb: Workbook, p: Project) -> None:
    ws = wb.create_sheet("Company Analysis")
    _header(ws, 2, 1, "Section")
    _header(ws, 2, 2, "Metric")
    _header(ws, 2, 3, "What it means?")
    for j, rec in enumerate(p.active()):
        _header(ws, 2, 4 + j, rec.name)
        if rec.website:
            ws.cell(row=3, column=4 + j, value=_safe(rec.website)).hyperlink = rec.website  # PDD step 5
    rows = [(m.group, m.label, m.question, lambda r, k=m.key: r.cells.get(k)) for m in ALL_METRICS]
    rows += [(m.group, m.label, m.question, lambda r, k=m.key: r.pricing.get(k)) for m in PRICING]
    rows += [("SWOT Analysis", k.title(), q, lambda r, k=k: r.swot.get(k)) for k, q in SWOT_QUESTIONS.items()]
    rows += [("Synthesis", "Strategic narrative", "Competitor X is winning in Y due to Z", lambda r: r.narrative)]
    for i, (group, lab, q, get) in enumerate(rows):
        r = 4 + i
        ws.cell(row=r, column=1, value=_safe(group)).font = BOLD
        ws.cell(row=r, column=2, value=_safe(lab)).font = BOLD
        ws.cell(row=r, column=3, value=_safe(q)).alignment = WRAP
        for col in (1, 2, 3):
            ws.cell(row=r, column=col).fill = GREEN
            ws.cell(row=r, column=col).border = THIN
        for j, rec in enumerate(p.active()):
            cell = get(rec)
            if cell and cell.value:
                _put(ws, r, 4 + j, cell)
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 26
    ws.column_dimensions["C"].width = 40
    for j in range(len(p.active())):
        ws.column_dimensions[get_column_letter(4 + j)].width = 48
    ws.freeze_panes = "D3"


def feature_comparison(wb: Workbook, p: Project) -> None:
    ws = wb.create_sheet("Feature Comparison")
    ws["A1"], ws["A1"].font = "Terminology", BOLD
    for i, (k, v) in enumerate(TIER_TERMINOLOGY.items()):
        ws.cell(row=2 + i, column=1, value=_safe(f"{k.title()}: {v}"))
    ws["D1"] = "Cell colours: amber = low confidence / unverified quote · grey = could not assess ('?') · red = rejected"
    hdr = 6
    _header(ws, hdr, 1, "Category")
    _header(ws, hdr, 2, "Feature type (+notes)")
    block = 5  # Standard, Premium, Enterprise, Score, Context Notes
    for j, rec in enumerate(p.active()):
        c0 = 3 + j * block
        ws.merge_cells(start_row=hdr - 1, start_column=c0, end_row=hdr - 1, end_column=c0 + block - 1)
        _header(ws, hdr - 1, c0, rec.name)
        for k, name in enumerate(["Standard", "Premium", "Enterprise", "Score", "Context Notes"]):
            _header(ws, hdr, c0 + k, name, fill=GREEN, font=BOLD)
        ws.column_dimensions[get_column_letter(c0 + 4)].width = 50
    order = [(f.category, f.name) for f in p.features]
    r = hdr + 1
    last_cat = None
    for cat, name in order:
        if cat != last_cat:
            ws.cell(row=r, column=1, value=_safe(cat)).font = BOLD
            ws.cell(row=r, column=1).fill = GREEN
            last_cat = cat
        ws.cell(row=r, column=2, value=_safe(name)).alignment = WRAP
        for j, rec in enumerate(p.active()):
            c0 = 3 + j * block
            fs = next((f for f in rec.features if f.feature == name), None)
            if not fs:
                continue
            for k, v in enumerate([fs.standard, fs.premium, fs.enterprise]):
                ws.cell(row=r, column=c0 + k, value=_safe("?" if v is None else v))
            sc = ws.cell(row=r, column=c0 + 3, value=_safe("?" if fs.score is None else fs.score))
            note = ws.cell(row=r, column=c0 + 4, value=_safe(fs.rationale))
            note.alignment = WRAP
            if fs.citations:
                sc.comment = Comment(_safe(_cite_text(fs.citations)[:3000]), "Datadvise CA tool", width=420, height=200)
            fill = RED if fs.status == "rejected" else GREY if fs.score is None else AMBER if (
                fs.confidence == "low" or not any(c.verified for c in fs.citations)) else None
            if fill:
                sc.fill = fill
        r += 1
    # category averages (the "Vanessa Categories" roll-up in the reference workbook)
    r += 1
    ws.cell(row=r, column=1, value=_safe("Category averages")).font = BOLD
    for cat in dict.fromkeys(c for c, _ in order):
        r += 1
        ws.cell(row=r, column=2, value=_safe(cat))
        for j, rec in enumerate(p.active()):
            vals = [f.score for f in rec.features if f.category == cat and f.score is not None and f.status != "rejected"]
            if vals:
                ws.cell(row=r, column=3 + j * block + 3, value=round(sum(vals) / len(vals), 1))
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 34
    ws.freeze_panes = ws.cell(row=hdr + 1, column=3)


def scoring_guide(wb: Workbook) -> None:
    ws = wb.create_sheet("Scoring Guide")
    r = 1
    for s, (name, dims) in SCORING_GUIDE.items():
        ws.cell(row=r, column=1, value=_safe(f"{s} - {name}")).font = BOLD
        for k, v in dims.items():
            r += 1
            ws.cell(row=r, column=1, value=_safe(f"{k} = {v}")).alignment = WRAP
        r += 2
    ws.column_dimensions["A"].width = 120


def insights(wb: Workbook, p: Project) -> None:
    ws = wb.create_sheet("Insights")
    for i, (k, lab) in enumerate([("executive_summary", "Executive Summary"), ("white_space", "White Space & Gaps"),
                                  ("trends", "Trends Across Competitors"), ("implications", "Implications for Client")]):
        ws.cell(row=1 + i, column=1, value=_safe(lab)).font = BOLD
        ws.cell(row=1 + i, column=2, value=_safe(getattr(p.insights, k).value)).alignment = WRAP
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 120


def sources(wb: Workbook, p: Project) -> None:
    ws = wb.create_sheet("Sources")
    for k, h in enumerate(["Competitor", "Source ID", "Type", "Title", "URL", "Fetched"]):
        _header(ws, 1, 1 + k, h)
    r = 2
    for rec in p.active():
        for s in rec.sources:
            if s.url.startswith("search://"):
                continue
            for k, v in enumerate([rec.name, s.id, s.kind, s.title, s.url, s.fetched_at[:10]]):
                ws.cell(row=r, column=1 + k, value=_safe(v))
            ws.cell(row=r, column=5).hyperlink = s.url
            r += 1
    for col, w in zip("ABCDEF", (22, 10, 10, 50, 70, 12)):
        ws.column_dimensions[col].width = w


def export(p: Project, path: Path) -> Path:
    wb = Workbook()
    ov = wb.active
    ov.title = "Document Overview"
    ov["A1"] = _safe(f"Competitive Analysis — {p.intake.client_name}")
    ov["A1"].font = Font(bold=True, size=14)
    ov["A3"] = _safe(f"Client product: {p.intake.product}")
    ov["A4"] = _safe(f"Competitors analysed: {', '.join(r.name for r in p.active())}")
    ov["A5"] = _safe(f"Generated by the Datadvise CA tool; project {p.id}, stage {p.stage}.")
    ov["A6"] = "Every AI value has a citation comment. Amber = low confidence or unverified quote; grey = unavailable; red = rejected."
    company_analysis(wb, p)
    feature_comparison(wb, p)
    scoring_guide(wb)
    insights(wb, p)
    sources(wb, p)
    _no_formulas(wb)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


__all__ = ["export", "label"]
