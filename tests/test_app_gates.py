"""Headless UI test of Gate 2, Gate 3 and export on a realistic project (no network, no AI calls)."""
import pytest
from streamlit.testing.v1 import AppTest

from ca_tool import config, store
from ca_tool.models import Candidate, FeatureDef, Intake, Project
from tests.test_core import FakeLLM, PAGE, _full_project
from ca_tool.research.corpus import Corpus


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    c = Corpus()
    c.add("https://acme.example/about", "About Acme", PAGE, kind="website")
    p = _full_project(c)
    p.id = "gates"
    p.candidates = [Candidate(name="Acme", status="accepted"), Candidate(name="Beta", status="accepted")]
    p.stage = "gate2"
    store.save(p)
    return p


def _open(project_id: str) -> AppTest:
    at = AppTest.from_file("../app.py", default_timeout=60).run()
    at.sidebar.selectbox[0].select(project_id).run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _button(at, prefix):
    return next(b for b in at.button if b.label.startswith(prefix))


def test_gate2_edit_reject_accept_and_approve(project):
    at = _open("gates")
    # edit one value, reject another, then save
    at.text_area(key="v_Acme_headquarters").input("Austin, Texas, USA").run()
    at.radio(key="s_Acme_description").set_value("rejected").run()
    _button(at, "💾 Save decisions").click().run()
    assert not at.exception, [e.value for e in at.exception]
    rec = store.load("gates").record("Acme")
    assert rec.cells["headquarters"].value == "Austin, Texas, USA" and rec.cells["headquarters"].status == "edited"
    assert rec.cells["description"].status == "rejected"
    # bulk accept keeps the rejected / edited ones as they are
    at = _open("gates")
    _button(at, "Accept all cells with verified evidence").click().run()
    rec = store.load("gates").record("Acme")
    assert rec.cells["founding_year"].status == "accepted"
    assert rec.cells["description"].status == "rejected" and rec.cells["headquarters"].status == "edited"
    at = _open("gates")
    _button(at, "✅ Approve data").click().run()
    assert store.load("gates").stage == "synthesis"


def test_gate3_scores_synthesis_and_export(project):
    p = store.load("gates")
    p.stage = "gate3"
    store.save(p)
    at = _open("gates")
    assert any(s.value == "Cross-competitor insights" for s in at.subheader)
    _button(at, "💾 Save scores").click().run()
    assert not at.exception, [e.value for e in at.exception]
    _button(at, "💾 Save synthesis").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert store.load("gates").record("Acme").swot["strengths"].status == "accepted"
    _button(at, "✅ Approve synthesis").click().run()
    assert store.load("gates").stage == "export"
    at = _open("gates")
    _button(at, "📦 Generate").click().run()
    assert not at.exception, [e.value for e in at.exception]
    labels = [b.label for b in at.get("download_button")]
    assert len(labels) == 3, labels
