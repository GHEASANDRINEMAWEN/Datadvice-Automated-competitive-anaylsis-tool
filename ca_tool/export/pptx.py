"""Client insight deck + battlecards, following the structure of the Prismm reference deck:
title → executive summary → agenda → insights → feature matrix → per competitor
(Overview, SWOT, Voice of the Customer) → sources. Colours/fonts from the reference theme.
Every content slide carries a "Source:" footer.
"""
from __future__ import annotations

import re
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

from ..knowledge.sources import domain
from ..models import Cell, CompetitorRecord, Project

INK = RGBColor(0x3D, 0x30, 0x4F)
LIGHT = RGBColor(0xFA, 0xFA, 0xFA)
LAVENDER = RGBColor(0xCC, 0xB0, 0xE5)
MINT = RGBColor(0x8A, 0xE3, 0xD1)
SKY = RGBColor(0x6E, 0xD1, 0xFC)
AMBER = RGBColor(0xFA, 0xC2, 0x59)
ORANGE = RGBColor(0xF5, 0x8F, 0x4D)
GREY = RGBColor(0xDA, 0xDA, 0xDA)
FONT = "Arial"

W, H = Emu(12192000), Emu(6858000)


def _deck() -> Presentation:
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    return prs


_REFS = re.compile(r"\s*\[(?:[SD]\d+(?:\s*,\s*)?)+\]")


def clean(text: str) -> str:
    """Client-facing text: drop internal source ids like [S3, S9] and put each bullet on its own line."""
    text = _REFS.sub("", str(text))
    text = re.sub(r"\s*•\s*", "\n• ", text).strip()
    return re.sub(r"\n{2,}", "\n", text)


def _box(slide, x, y, w, h, text="", size=12, bold=False, color=INK, fill=None, align=PP_ALIGN.LEFT):
    shp = slide.shapes.add_textbox(x, y, w, h) if fill is None else slide.shapes.add_shape(1, x, y, w, h)
    if fill is not None:
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
        shp.line.fill.background()
    tf = shp.text_frame
    tf.word_wrap = True
    for i, line in enumerate(clean(text).split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = line
        r.font.size, r.font.bold, r.font.name = Pt(size), bold, FONT
        r.font.color.rgb = color
    return shp


def _slide(prs, title: str, sources: list[str] | None = None, page: int | None = None):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _box(s, Inches(0.5), Inches(0.3), Inches(12.3), Inches(0.8), title, size=26, bold=True)
    bar = s.shapes.add_shape(1, Inches(0.5), Inches(1.05), Inches(1.2), Emu(45720))
    bar.fill.solid()
    bar.fill.fore_color.rgb = MINT
    bar.line.fill.background()
    if sources:
        doms = list(dict.fromkeys(domain(u) for u in sources if u and not u.startswith("search://")))
        _box(s, Inches(0.5), Inches(7.05), Inches(11), Inches(0.35), "Source: " + ", ".join(doms[:6]), size=9, color=INK)
    if page:
        _box(s, Inches(12.4), Inches(7.05), Inches(0.6), Inches(0.35), str(page), size=9, align=PP_ALIGN.RIGHT)
    return s


def _urls(*cells: Cell) -> list[str]:
    return [c.url for cell in cells if cell for c in cell.citations]


def _val(rec: CompetitorRecord, key: str, limit: int = 400) -> str:
    c = rec.cells.get(key)
    if not c or c.status == "rejected":
        return "n.a."
    v = c.value.strip()
    return v if len(v) <= limit else v[: limit - 1].rsplit(" ", 1)[0] + "…"


def title_slide(prs, p: Project) -> None:
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg = s.shapes.add_shape(1, 0, 0, W, H)
    bg.fill.solid()
    bg.fill.fore_color.rgb = INK
    bg.line.fill.background()
    _box(s, Inches(0.8), Inches(2.4), Inches(11.5), Inches(1.2), f"{p.intake.client_name}\nIndustry & Competitor Analysis Report",
         size=34, bold=True, color=LIGHT)
    _box(s, Inches(0.8), Inches(4.3), Inches(11), Inches(0.5), "by Datadvise", size=16, color=MINT)


def bullets_slide(prs, title: str, cell: Cell, page: int) -> None:
    s = _slide(prs, title, _urls(cell), page)
    text = clean(cell.value or "—")
    _box(s, Inches(0.6), Inches(1.4), Inches(12.1), Inches(5.5), text, size=16 if len(text) < 900 else 13)


def agenda(prs, p: Project, page: int) -> None:
    s = _slide(prs, "Contents", page=page)
    items = ["Executive Summary", "Insights: White Space, Trends, Implications", "Feature Comparison"]
    items += [f"Competitor Analysis – {r.name}" for r in p.competitors]
    _box(s, Inches(0.6), Inches(1.4), Inches(12), Inches(5.5), "\n".join(f"{i + 1}.  {t}" for i, t in enumerate(items)), size=16)


def feature_matrix(prs, p: Project, page: int) -> int:
    """Category-average heat table (the reference workbook's category roll-up)."""
    cats = list(dict.fromkeys(f.category for f in p.features))
    comps = p.competitors[:8]
    if not cats or not comps:
        return page
    s = _slide(prs, "Feature Comparison – average score by category (0–5)", page=page)
    rows, cols = len(cats) + 1, len(comps) + 1
    tbl = s.shapes.add_table(rows, cols, Inches(0.5), Inches(1.4), Inches(12.3), Inches(0.5) * rows).table
    tbl.columns[0].width = Inches(3.1)
    for j in range(1, cols):
        tbl.columns[j].width = int((Inches(12.3) - Inches(3.1)) / (cols - 1))

    def put(i, j, text, fill=None, bold=False):
        c = tbl.cell(i, j)
        c.text = text
        para = c.text_frame.paragraphs[0]
        para.alignment = PP_ALIGN.CENTER if j else PP_ALIGN.LEFT
        for r in para.runs:
            r.font.size, r.font.name, r.font.bold = Pt(12), FONT, bold
            r.font.color.rgb = INK
        c.fill.solid()
        c.fill.fore_color.rgb = fill or LIGHT

    put(0, 0, "Category", LAVENDER, True)
    for j, rec in enumerate(comps, 1):
        put(0, j, rec.name, LAVENDER, True)
    for i, cat in enumerate(cats, 1):
        put(i, 0, cat, bold=True)
        for j, rec in enumerate(comps, 1):
            vals = [f.score for f in rec.features if f.category == cat and f.score is not None and f.status != "rejected"]
            if not vals:
                put(i, j, "?", GREY)
                continue
            avg = sum(vals) / len(vals)
            put(i, j, f"{avg:.1f}", MINT if avg >= 4 else SKY if avg >= 3 else AMBER if avg >= 2 else ORANGE)
    _box(s, Inches(0.5), Inches(6.6), Inches(12), Inches(0.4),
         "Scored with the Datadvise Feature Scoring Guide: 0 Absent · 1 Basic · 2 Developing · 3 Competent · 4 Advanced · 5 Leading. '?' = insufficient evidence.",
         size=10)
    return page + 1


def overview(prs, rec: CompetitorRecord, page: int) -> None:
    keys = ["founding_year", "headquarters", "geographies", "employees", "target_market", "use_cases", "deployment",
            "brand_position", "usvp", "services", "innovation", "partnerships"]
    s = _slide(prs, f"{rec.name} Overview", _urls(*(rec.cells.get(k) for k in keys)), page)
    facts = [("Foundation", "founding_year"), ("Headquarter", "headquarters"), ("Geographies", "geographies"),
             ("# of employees", "employees")]
    for i, (lab, k) in enumerate(facts):
        y = Inches(1.4 + i * 1.35)
        _box(s, Inches(0.5), y, Inches(2.9), Inches(1.2), f"{lab}\n{_val(rec, k, 60)}", size=12, bold=False, fill=LAVENDER)
    blocks = [("Target Market", "target_market"), ("Primary Use Cases", "use_cases"), ("Deployment", "deployment"),
              ("Brand Positioning", "brand_position"), ("Unique Selling Proposition", "usvp"),
              ("Auxiliary Services", "services"), ("Innovation", "innovation"), ("Partnerships", "partnerships")]
    for i, (lab, k) in enumerate(blocks):
        col, row = i % 2, i // 2
        x, y = Inches(3.7 + col * 4.6), Inches(1.4 + row * 1.35)
        _box(s, x, y, Inches(4.4), Inches(0.3), lab, size=11, bold=True)
        _box(s, x, y + Inches(0.3), Inches(4.4), Inches(1.0), _val(rec, k, 230), size=9)


def swot(prs, rec: CompetitorRecord, page: int) -> None:
    s = _slide(prs, f"{rec.name} – SWOT Analysis", _urls(*rec.swot.values()), page)
    quads = [("Strengths", "strengths", MINT), ("Weaknesses", "weaknesses", AMBER),
             ("Opportunities", "opportunities", SKY), ("Threats", "threats", ORANGE)]
    for i, (lab, k, colr) in enumerate(quads):
        x, y = Inches(0.5 + (i % 2) * 6.2), Inches(1.35 + (i // 2) * 2.85)
        _box(s, x, y, Inches(6.0), Inches(0.4), lab, size=13, bold=True, fill=colr)
        cell = rec.swot.get(k)
        text = cell.value if cell and cell.status != "rejected" else "—"
        _box(s, x, y + Inches(0.45), Inches(6.0), Inches(2.3), text[:700], size=12 if len(text) < 450 else 10)


def voc(prs, rec: CompetitorRecord, page: int) -> int:
    for sentiment, colr in (("positive", MINT), ("negative", ORANGE)):
        quotes = [q for q in rec.voc if q.sentiment == sentiment][:3]
        if not quotes:
            continue
        s = _slide(prs, f"Voice of the Customer – {rec.name} ({'+ve' if sentiment == 'positive' else '-ve'})",
                   [q.citation.url for q in quotes], page)
        for i, q in enumerate(quotes):
            y = Inches(1.4 + i * 1.8)
            _box(s, Inches(0.6), y, Inches(0.15), Inches(1.5), "", fill=colr)
            _box(s, Inches(0.9), y, Inches(11.8), Inches(1.6), f"“{q.text[:450]}”\n— {domain(q.citation.url)}", size=13)
        page += 1
    return page


def sources_slide(prs, p: Project, page: int) -> None:
    s = _slide(prs, "Sources", page=page)
    doms = {}
    for rec in p.competitors:
        for src in rec.sources:
            if not src.url.startswith("search://"):
                doms.setdefault(domain(src.url), 0)
                doms[domain(src.url)] += 1
    top = sorted(doms.items(), key=lambda x: -x[1])[:45]
    text = "   ".join(f"{d} ({n})" for d, n in top)
    _box(s, Inches(0.6), Inches(1.4), Inches(12), Inches(5.5),
         f"{sum(doms.values())} pages consulted across {len(doms)} domains. Full URL list with per-cell citations is in the Excel workbook (Sources sheet).\n\n{text}",
         size=11)


def export_deck(p: Project, path: Path) -> Path:
    prs = _deck()
    title_slide(prs, p)
    page = 2
    bullets_slide(prs, "Executive Summary", p.insights.executive_summary, page); page += 1
    agenda(prs, p, page); page += 1
    for title, k in [("White Space & Competitive Gaps", "white_space"), ("Trends Across Competitors", "trends"),
                     (f"Strategic Implications for {p.intake.client_name}", "implications")]:
        bullets_slide(prs, title, getattr(p.insights, k), page); page += 1
    page = feature_matrix(prs, p, page)
    for rec in p.competitors:
        overview(prs, rec, page); page += 1
        swot(prs, rec, page); page += 1
        page = voc(prs, rec, page)
    sources_slide(prs, p, page)
    path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(path)
    return path


def export_battlecards(p: Project, path: Path) -> Path:
    """One-page battlecard per competitor for the client's sales / GTM team."""
    prs = _deck()
    for i, rec in enumerate(p.competitors, 1):
        s = _slide(prs, f"Battlecard: {p.intake.client_name} vs {rec.name}",
                   _urls(rec.cells.get("usvp"), rec.pricing.get("recurring_fees"), *rec.swot.values()), i)
        _box(s, Inches(0.5), Inches(1.3), Inches(12.3), Inches(0.7),
             f"Who they are: {_val(rec, 'description', 260)}", size=11, fill=LAVENDER)
        cols = [("Their pitch", _val(rec, "usvp", 380), SKY),
                ("Pricing", (rec.pricing.get("recurring_fees") or Cell(value="n.a.")).value[:300], GREY),
                ("Where they're strong", (rec.swot.get("strengths") or Cell()).value[:450], MINT),
                ("Where they're weak", (rec.swot.get("weaknesses") or Cell()).value[:450], AMBER)]
        for j, (lab, text, colr) in enumerate(cols):
            x, y = Inches(0.5 + (j % 2) * 6.2), Inches(2.15 + (j // 2) * 1.75)
            _box(s, x, y, Inches(6.0), Inches(0.35), lab, size=12, bold=True, fill=colr)
            _box(s, x, y + Inches(0.35), Inches(6.0), Inches(1.35), text, size=9)
        _box(s, Inches(0.5), Inches(5.7), Inches(12.3), Inches(0.35), "How we win", size=12, bold=True, fill=INK, color=LIGHT)
        _box(s, Inches(0.5), Inches(6.05), Inches(12.3), Inches(1.0), rec.battlecard.value[:600] or "—", size=10)
    path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(path)
    return path
