"""Offline tests: no network, no API calls. A fake LLM stands in for the engine."""
import json

import pytest
from openpyxl import load_workbook
from pptx import Presentation

from ca_tool import config, store
from ca_tool.export import excel, pptx
from ca_tool.knowledge.scoring import SCORING_GUIDE, guide_text, label
from ca_tool.knowledge.sources import classify
from ca_tool.knowledge.template import ALL_METRICS, PRICING
from ca_tool.llm.base import LLM
from ca_tool.models import (Candidate, Cell, Citation, CompetitorRecord, FeatureDef, FeatureScore, Intake,
                            Project, Quote, Source)
from ca_tool.pipeline import collect, score, synthesize
from ca_tool.research import web
from ca_tool.research.corpus import Corpus, quote_in_text

PAGE = ("Acme Spaces was founded in 2015 and is headquartered in Austin, Texas. "
        "Our platform lets venues build interactive 3D floor plans and share virtual tours with planners. "
        "“Setup was quick and the support team answered within an hour,” says one G2 reviewer. "
        "Another reviewer wrote that the mobile app crashes when loading large floor plans.")


class FakeLLM(LLM):
    """Answers each schema with deterministic data citing S1."""
    name = "fake"
    last_model = "fake"

    def generate_text(self, prompt, system=""):
        return "ok"

    def generate_json(self, prompt, schema, system=""):
        n = schema.__name__
        cite = [{"source_id": "S1", "quote": "founded in 2015 and is headquartered in Austin, Texas"}]
        if n == "_CollectOut":
            keys = [m.key for m in ALL_METRICS + PRICING if f"- {m.key}:" in prompt]
            vals = [{"key": k, "value": f"value for {k}", "confidence": "high", "note": "", "citations": cite} for k in keys]
            vals[-1] = {"key": keys[-1], "value": "Undisclosed", "confidence": "unavailable", "note": "use proxy", "citations": []}
            data = {"values": vals}
        elif n == "_ScoreOut":
            data = {"scores": [
                {"id": "F1", "feature": "3D floor plans", "standard": True, "premium": True, "enterprise": None, "score": 4,
                 "rationale": "Advanced", "confidence": "high",
                 "citations": [{"source_id": "S1", "quote": "build interactive 3D floor plans"}]},
                {"id": "F2", "feature": "VR headset support", "standard": None, "premium": None, "enterprise": None, "score": None,
                 "rationale": "no evidence", "confidence": "unavailable", "citations": []},
                # hallucinated citation: quote not on the page
                {"id": "X", "feature": "[Planning] Seating charts", "standard": True, "premium": True, "enterprise": True, "score": 5,
                 "rationale": "Leading", "confidence": "high",
                 "citations": [{"source_id": "S1", "quote": "industry leading seating chart engine used by millions"}]},
            ]}
        elif n == "_CompOut":
            pt = [{"text": "Strong 3D", "citations": [{"source_id": "S1", "quote": "build interactive 3D floor plans"}]}]
            data = {"strengths": pt, "weaknesses": pt, "opportunities": pt, "threats": pt,
                    "voice_of_customer": [
                        {"text": "Setup was quick and the support team answered within an hour", "sentiment": "positive", "source_id": "S1"},
                        {"text": "Invented quote that nobody ever wrote anywhere at all", "sentiment": "negative", "source_id": "S1"}],
                    "narrative": "Acme is winning in venues because of 3D.", "how_client_wins": ["Lead with seating"]}
        elif n == "_InsightsOut":
            data = {k: "• point" for k in ("executive_summary", "white_space", "trends", "implications")}
        else:
            raise AssertionError(n)
        return schema.model_validate_json(json.dumps(data))


@pytest.fixture
def tmp_projects(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    return tmp_path


@pytest.fixture
def corpus():
    c = Corpus()
    c.add("https://acme.example/about", "About Acme", PAGE, kind="website")
    return c


def test_quote_verification_exact_and_fuzzy():
    assert quote_in_text("founded in 2015 and is headquartered in Austin", PAGE)
    assert quote_in_text("Setup was quick and the support team answered within an hour", PAGE)  # curly quotes on page
    assert quote_in_text("FOUNDED in 2015   and is headquartered in Austin, Texas.", PAGE)  # case/space
    assert not quote_in_text("founded in 2012 and is headquartered in Denver, Colorado", PAGE)
    assert not quote_in_text("short", PAGE)


def test_quote_verification_bullets_and_ellipses():
    page = ("Its ecosystem has expanded into\n- commercial office\n- hospitality\n- retail\n"
            "Enterprise customers mention account managers by name, including Saba and Dan, "
            "and describe them as responsive and proactive.")
    assert quote_in_text("expanded into: commercial office, hospitality, retail", page)
    assert quote_in_text("Enterprise customers mention account managers by name... and describe them as responsive", page)
    assert quote_in_text("Enterprise customers mention account managers by name … responsive and proactive", page)
    # parts out of order or a fabricated part must fail
    assert not quote_in_text("describe them as responsive... Enterprise customers mention account managers", page)
    assert not quote_in_text("Enterprise customers mention account managers by name... and pay $9.99 per month", page)
    # page titles are not evidence
    assert not quote_in_text("Cvent | Event Platform for In-person, Virtual and Hybrid Events", "Welcome to our site")


def test_corpus_resolve_drops_unknown_sources_and_flags_unverified(corpus):
    out = corpus.resolve([Citation(source_id="S1", quote="build interactive 3D floor plans"),
                          Citation(source_id="[S1]", quote="completely made up claim about pricing tiers"),
                          Citation(source_id="S9", quote="anything")])
    assert [c.verified for c in out] == [True, False]
    assert out[0].url == "https://acme.example/about"


def test_corpus_dedupes_and_respects_budget(corpus):
    assert corpus.add("https://acme.example/about", "dup", "x" * 500) is None
    corpus.add("https://b.example", "B", "y" * 5000)
    assert len(corpus.render(max_chars=1000)) <= 1010


def test_source_priorities():
    assert classify("https://www.g2.com/products/x/reviews") == ("review", 1)
    assert classify("https://news.crunchbase.com/a") == ("funding", 1)
    assert classify("https://pinterest.com/pin/1")[1] == 9
    hits = [web.SearchHit("a", "https://blog.example/x", ""), web.SearchHit("b", "https://www.g2.com/x", ""),
            web.SearchHit("c", "https://pinterest.com/y", ""), web.SearchHit("d", "https://www.g2.com/x", "")]
    assert [h.url for h in web.rank_hits(hits)] == ["https://www.g2.com/x", "https://blog.example/x"]


def test_scoring_guide_is_complete():
    assert sorted(SCORING_GUIDE) == [0, 1, 2, 3, 4, 5]
    assert all(set(d) == {"Presence", "Quality", "Maturity"} for _, d in SCORING_GUIDE.values())
    assert label(None) == "?" and label(4.0) == "Advanced"
    assert "5 - Leading" in guide_text()


def test_key_pages_and_guessed_paths():
    home = web.Page(url="https://acme.example/", title="", text="", links=[
        ("About us", "https://acme.example/company/about"), ("Pricing", "https://acme.example/pricing"),
        ("Partner site", "https://other.example/partners")])
    kp = web.key_pages(home)
    assert kp["about"].endswith("/company/about") and kp["pricing"].endswith("/pricing") and "partners" not in kp
    g = web.guessed_pages("https://acme.example/", ["careers"])
    assert ("careers", "https://acme.example/careers") in g


def test_extract_fills_every_metric_with_verified_citations(corpus):
    intake = Intake(client_name="Client", product="3D venue software")
    cells = collect.extract("Acme", intake, corpus, ALL_METRICS + PRICING, FakeLLM())
    assert set(cells) == {m.key for m in ALL_METRICS + PRICING}
    assert cells["founding_year"].verified and cells["founding_year"].confidence == "high"
    last = (ALL_METRICS + PRICING)[-1].key
    assert cells[last].confidence == "unavailable" and cells[last].note == "use proxy"


def _record(corpus) -> CompetitorRecord:
    return CompetitorRecord(name="Acme", website="https://acme.example", sources=corpus.sources)


def test_scoring_unknown_is_question_mark_and_fake_quotes_downgraded(corpus):
    feats = [FeatureDef(category="Design", name="3D floor plans"), FeatureDef(category="Design", name="VR headset support"),
             FeatureDef(category="Planning", name="Seating charts"), FeatureDef(category="Planning", name="Budgeting")]
    out = {f.feature: f for f in score.score(_record(corpus), feats, Intake(client_name="C", product="p"), FakeLLM())}
    assert out["3D floor plans"].score == 4 and out["3D floor plans"].confidence == "high"
    assert out["VR headset support"].score is None
    assert out["Seating charts"].confidence == "low"          # quote not found on page
    assert out["Budgeting"].confidence == "unavailable"       # model skipped it


def test_synthesis_keeps_only_verified_customer_quotes(corpus):
    rec = _record(corpus)
    synthesize.synthesize_competitor(rec, Intake(client_name="C", product="p"), FakeLLM())
    assert set(rec.swot) == {"strengths", "weaknesses", "opportunities", "threats"}
    assert [q.sentiment for q in rec.voc] == ["positive"]      # invented negative quote dropped
    assert rec.battlecard.value.startswith("•")


def _full_project(corpus) -> Project:
    p = Project(id="t", intake=Intake(client_name="Client", product="3D venue software"))
    p.features = [FeatureDef(category="Design", name="3D floor plans"), FeatureDef(category="Planning", name="Seating charts")]
    llm = FakeLLM()
    for name in ("Acme", "Beta"):
        rec = CompetitorRecord(name=name, website=f"https://{name.lower()}.example", sources=corpus.sources)
        cells = collect.extract(name, p.intake, corpus, ALL_METRICS + PRICING, llm)
        rec.pricing = {k: cells.pop(k) for k in collect.PRICING_BY_KEY}
        rec.cells = cells
        rec.features = score.score(rec, p.features, p.intake, llm)
        synthesize.synthesize_competitor(rec, p.intake, llm)
        p.competitors.append(rec)
    p.competitors[1].cells["description"].status = "rejected"
    p.insights = synthesize.synthesize_insights(p, llm)
    return p


def test_excel_export_matches_template_layout(tmp_path, corpus):
    p = _full_project(corpus)
    path = excel.export(p, tmp_path / "out.xlsx")
    wb = load_workbook(path)
    assert {"Company Analysis", "Feature Comparison", "Scoring Guide", "Insights", "Sources"} <= set(wb.sheetnames)
    ca = wb["Company Analysis"]
    assert ca["B2"].value == "Metric" and ca["C2"].value == "What it means?" and ca["D2"].value == "Acme"
    assert ca["D3"].hyperlink is not None
    row = next(r for r in range(4, 60) if ca.cell(r, 2).value == "Founding Year")
    assert ca.cell(row, 4).comment and "✓" in ca.cell(row, 4).comment.text
    desc = next(r for r in range(4, 60) if ca.cell(r, 2).value == "Description")
    assert ca.cell(desc, 5).fill.fgColor.rgb.endswith("F4CCCC")  # rejected -> red
    fc = wb["Feature Comparison"]
    assert fc["C6"].value == "Standard" and fc["F6"].value == "Score" and fc["G6"].value == "Context Notes"
    assert fc["F7"].value == 4 and fc["C5"].value == "Acme"


def test_pptx_exports(tmp_path, corpus):
    p = _full_project(corpus)
    deck = Presentation(pptx.export_deck(p, tmp_path / "deck.pptx"))
    titles = [next((sh.text_frame.text for sh in s.shapes if sh.has_text_frame and sh.text_frame.text), "") for s in deck.slides]
    assert "Executive Summary" in titles and "Acme Overview" in titles and "Acme – SWOT Analysis" in titles
    assert any(t.startswith("Voice of the Customer – Acme") for t in titles)
    body = " ".join(sh.text_frame.text for s in deck.slides for sh in s.shapes if sh.has_text_frame)
    assert "Source: acme.example" in body
    cards = Presentation(pptx.export_battlecards(p, tmp_path / "cards.pptx"))
    assert len(cards.slides) == 2


def test_store_roundtrip(tmp_projects):
    p = store.create(Intake(client_name="Demo Co!", product="x", known_competitors=["A"]))
    assert p.id == "demo-co"
    p.candidates.append(Candidate(name="A", citations=[Citation(source_id="D1", quote="q", verified=True)]))
    store.save(p)
    q = store.load("demo-co")
    assert q.candidates[0].citations[0].verified and store.list_ids() == ["demo-co"]
    assert store.create(Intake(client_name="Demo Co!", product="x")).id == "demo-co-2"


def test_scoring_fails_loudly_when_output_unmatchable(corpus):
    class Garbled(FakeLLM):
        def generate_json(self, prompt, schema, system=""):
            out = super().generate_json(prompt, schema, system)
            for sc in getattr(out, "scores", []):
                sc.id, sc.feature = "?", "something else entirely"
            return out
    feats = [FeatureDef(category="Design", name="3D floor plans"), FeatureDef(category="Design", name="VR headset support")]
    with pytest.raises(ValueError):
        score.score(_record(corpus), feats, Intake(client_name="C", product="p"), Garbled())


def test_deck_text_cleaning():
    out = pptx.clean("• Consolidation [S11], signal. • AI adoption [S14] and [S1, S9] models. • Third [D3]")
    assert out == "• Consolidation, signal.\n• AI adoption and models.\n• Third"


def test_snippet_citation_resolves_to_real_url():
    from ca_tool.research.corpus import snippet_url
    c = Corpus()
    c.add("search://X", "results", "- G2: I find the tool incredibly helpful for reducing admin tasks (https://www.g2.com/x)\n"
                                   "- Other page: unrelated text here (https://a.example/c)")
    cite = c.resolve([Citation(source_id="S1", quote="I find the tool incredibly helpful")])[0]
    assert cite.verified and cite.url == "https://www.g2.com/x"
    assert snippet_url("no urls here", "anything at all goes") == ""


def test_company_mention_matching():
    assert web.mentions("Try Event Diagram today", "EventDiagram")
    assert web.mentions("see eventdiagram.com for pricing", "EventDiagram")
    assert web.mentions("Cvent's diagramming tool", "Cvent Event Diagramming")
    assert not web.mentions("A page about floor plans", "EventDiagram")


def test_blocked_review_sites_are_snippet_only():
    from ca_tool.knowledge.sources import fetchable, site_name
    assert site_name("https://www.capterra.co.uk/x") == site_name("https://capterra.ae/y") == "capterra"
    assert not fetchable("https://www.g2.com/products/x/reviews")
    assert fetchable("https://en.wikipedia.org/wiki/Matterport")


def test_llm_waits_and_retries_when_all_models_busy(monkeypatch):
    from ca_tool.llm import gemini as g
    from google.genai import errors

    calls = []

    class Models:
        def generate_content(self, model, contents, config):
            calls.append(model)
            if len(calls) <= 2:
                raise errors.APIError(503, {"error": {"code": 503, "message": "busy", "status": "UNAVAILABLE"}})
            part = type("P", (), {"text": "ok"})()
            cand = type("C", (), {"content": type("X", (), {"parts": [part]})()})()
            return type("R", (), {"candidates": [cand]})()

    llm = g.GeminiLLM(api_key="x", models=["m1", "m2"], retries=1, round_wait=0)
    llm.client = type("Cl", (), {"models": Models()})()
    g.GeminiLLM._cooldown.clear()
    assert llm.generate_text("hi") == "ok" and calls == ["m1", "m2", "m1"]
    g.GeminiLLM._cooldown.clear()
