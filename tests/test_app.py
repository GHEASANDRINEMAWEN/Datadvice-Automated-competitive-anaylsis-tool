"""Headless UI test of the analyst app (no network: only steps that don't call the AI)."""
from streamlit.testing.v1 import AppTest

from ca_tool import config, store
from ca_tool.models import Candidate, FeatureDef


def test_intake_and_gate1(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    at = AppTest.from_file("../app.py", default_timeout=60).run()
    assert not at.exception
    at.text_input[0].input("Acme Client")
    at.text_input[1].input("3D venue software")
    at.button[0].click().run()   # form submit
    assert not at.exception
    assert store.list_ids() == ["acme-client"]

    # simulate discovery output, then approve at Gate 1 through the UI
    p = store.load("acme-client")
    p.candidates = [Candidate(name="Beta", status="accepted"), Candidate(name="Gamma", status="rejected")]
    p.features = [FeatureDef(category="Design", name="3D floor plans")]
    p.stage = "gate1"
    store.save(p)
    at = AppTest.from_file("../app.py", default_timeout=60).run()
    at.sidebar.selectbox[0].select("acme-client").run()
    approve = next(b for b in at.button if b.label.startswith("✅ Approve scope"))
    assert "(1 competitors)" in approve.label
    approve.click().run()
    assert not at.exception
    assert store.load("acme-client").stage == "collection"
