"""Datadvise Competitive Analysis — analyst app.

Run:  python app.py        (or: streamlit run app.py)

The AI produces; the analyst approves. Three gates mirror the Datadvise process checkpoints:
Gate 1 scope · Gate 2 data · Gate 3 scores/SWOT/insights.
"""
from __future__ import annotations

import sys

if __name__ == "__main__" and "streamlit" not in sys.modules:
    import subprocess
    sys.exit(subprocess.call([sys.executable, "-m", "streamlit", "run", __file__, *sys.argv[1:]]))

import logging

import pandas as pd
import streamlit as st

from ca_tool import config, store
from ca_tool.knowledge.scoring import guide_text
from ca_tool.knowledge.template import ALL_METRICS, PRICING, SWOT_QUESTIONS
from ca_tool.llm import LLMError, get_llm
from ca_tool.models import Candidate, Cell, FeatureDef, Intake, Project
from ca_tool.pipeline import collect as collect_mod
from ca_tool.pipeline import runner

logging.getLogger("google_genai").setLevel(logging.ERROR)
st.set_page_config(page_title="Datadvise CA Tool", page_icon="🕵️", layout="wide")

CONF_BADGE = {"high": "🟢 high", "medium": "🟡 medium", "low": "🟠 low", "unavailable": "⚪ unavailable"}
STAGES = ["intake", "gate1", "collection", "gate2", "synthesis", "gate3", "export"]


@st.cache_resource
def llm():
    return get_llm()


def save(p: Project) -> None:
    store.save(p)
    st.session_state.project = p


def cite_md(cites) -> str:
    return "\n".join(f"- {'✅' if c.verified else '⚠️ unverified'} [{c.source_id}]({c.url}) “{c.quote}”" for c in cites) or "_no citation_"


def run_step(label: str, fn, p: Project, **kw) -> None:
    try:
        with st.status(label, expanded=True) as s:
            fn(p, llm(), progress=s.write, **kw)
            s.update(label=f"{label} — done", state="complete")
        save(p)
        st.rerun()
    except LLMError as e:
        st.error(f"AI engine error: {e}")


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🕵️ Datadvise CA Tool")
    st.caption("The AI produces; the analyst approves.")
    ids = store.list_ids()
    choice = st.selectbox("Project", ["➕ New project"] + ids,
                          index=(ids.index(st.session_state.project.id) + 1) if "project" in st.session_state and st.session_state.project.id in ids else 0)
    if choice != "➕ New project":
        if "project" not in st.session_state or st.session_state.project.id != choice:
            loaded = store.load(choice)
            if runner.reverify(loaded):
                store.save(loaded)
            st.session_state.project = loaded
    else:
        st.session_state.pop("project", None)
    p: Project | None = st.session_state.get("project")
    if p:
        st.progress((STAGES.index(p.stage) + 1) / len(STAGES), text=f"Stage: {p.stage}")
    st.divider()
    st.caption(f"Engine: Gemini · models {', '.join(config.GEMINI_MODELS)}")
    if not config.GEMINI_API_KEY:
        st.error("GEMINI_API_KEY missing in .env")
    st.caption("⚠️ Client-confidential data only on a paid-tier key.")

# ---------------------------------------------------------------- intake
if not p:
    st.header("New engagement · Client intake")
    st.caption("Inputs from the Datadvise Competitive Intelligence Process §2 (confirm with the client before research).")
    with st.form("intake"):
        c1, c2 = st.columns(2)
        client = c1.text_input("Client name *")
        product = c2.text_input("Client product / service *", placeholder="e.g. 3D event diagramming software for venues")
        positioning = st.text_area("Client positioning")
        c1, c2 = st.columns(2)
        markets = c1.text_input("Target markets & customer segments")
        geo = c2.text_input("Geographies")
        known = st.text_input("Known or suspected competitors (comma-separated)")
        dims = st.text_input("Competitive dimensions of interest", placeholder="pricing, features, marketing, sales channels")
        goals = st.text_input("Business goals for the intelligence", placeholder="differentiation, messaging, GTM, pricing")
        notes = st.text_area("Other notes")
        if st.form_submit_button("Create project", type="primary"):
            if not client or not product:
                st.error("Client name and product are required.")
            else:
                np_ = store.create(Intake(client_name=client, product=product, positioning=positioning, target_markets=markets,
                                         geographies=geo, known_competitors=[k.strip() for k in known.split(",") if k.strip()],
                                         dimensions=dims, business_goals=goals, notes=notes))
                st.session_state.project = np_
                st.rerun()
    st.stop()

st.header(f"{p.intake.client_name} — competitive analysis")
st.caption(f"{p.intake.product} · {p.intake.target_markets}")
tab0, tab1, tab2, tab3, tab4, tab5 = st.tabs(["Overview", "1 · Scope (Gate 1)", "2 · Data (Gate 2)", "3 · Synthesis (Gate 3)", "4 · Export", "Log"])

# ---------------------------------------------------------------- overview
with tab0:
    labels = {"intake": "Intake", "gate1": "Gate 1 · Scope", "collection": "Research", "gate2": "Gate 2 · Data",
              "synthesis": "Synthesis", "gate3": "Gate 3 · Review", "export": "Export"}
    cur = STAGES.index(p.stage)
    st.markdown("  →  ".join(f"**{labels[s]}**" if i == cur else (f"✅ {labels[s]}" if i < cur else labels[s])
                             for i, s in enumerate(STAGES)))
    next_step = {"intake": "Go to **1 · Scope** and click *Find competitors*.",
                 "gate1": "Review the candidates and features in **1 · Scope**, then approve the scope.",
                 "collection": "Go to **2 · Data** and click *Research competitors*.",
                 "gate2": "Review each competitor's fields in **2 · Data**, then approve the data.",
                 "synthesis": "Go to **3 · Synthesis**: score features, then generate SWOT & insights.",
                 "gate3": "Adjudicate scores and SWOTs in **3 · Synthesis**, then approve.",
                 "export": "Download the deliverables in **4 · Export**."}[p.stage]
    st.info(f"Next step: {next_step}")
    ok = runner.approved(p)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Candidates", len(p.candidates), f"{len(ok)} approved", delta_color="off")
    c2.metric("Features to compare", len(p.features))
    allcells = [c for r in p.competitors for c in {**r.cells, **r.pricing}.values()]
    allcites = [x for c in allcells for x in c.citations]
    c3.metric("Quotes verified", f"{sum(x.verified for x in allcites)}/{len(allcites)}" if allcites else "—")
    c4.metric("Fields awaiting review", sum(1 for c in allcells if c.status == "proposed"))
    if p.competitors:
        rows = []
        for r in p.competitors:
            cells = {**r.cells, **r.pricing}
            cs = [x for c in cells.values() for x in c.citations]
            scored = [f for f in r.features if f.score is not None]
            rows.append({"competitor": r.name, "website": r.website, "sources read": len(r.sources),
                         "quotes verified": f"{sum(x.verified for x in cs)}/{len(cs)}",
                         "⚠️ low confidence": sum(1 for c in cells.values() if c.confidence == "low"),
                         "unavailable": sum(1 for c in cells.values() if c.confidence == "unavailable"),
                         "to review": sum(1 for c in cells.values() if c.status == "proposed"),
                         "rejected": sum(1 for c in cells.values() if c.status == "rejected"),
                         "features scored": f"{len(scored)}/{len(r.features)}" if r.features else "—",
                         "avg score": round(sum(f.score for f in scored) / len(scored), 1) if scored else None,
                         "SWOT": "✓" if r.swot else "—", "customer quotes": len(r.voc)})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     column_config={"website": st.column_config.LinkColumn()})
        st.caption("⚠️ low confidence = the AI's quote was not found on the cited page (or no evidence was given) — check these first.")
    else:
        st.caption("No competitors researched yet.")

# ---------------------------------------------------------------- gate 1
with tab1:
    st.subheader("Competitor discovery")
    st.caption("AI proposes 8–20 cited candidates. Accept, edit or reject; re-run with feedback instead of fixing by hand.")
    c1, c2 = st.columns([3, 1])
    fb1 = c1.text_input("Feedback for a re-run (optional)", key="fb1", placeholder="e.g. focus on European mid-market players")
    if c2.button("🔎 Find competitors" if not p.candidates else "🔁 Re-run discovery", type="primary"):
        run_step("Discovering competitors", runner.discover, p, feedback=fb1)
    if p.candidates:
        df = pd.DataFrame([{"status": c.status, "name": c.name, "website": c.website, "type": c.type, "segment": c.segment,
                            "size group": c.size_group, "geography": c.geography, "justification": c.justification,
                            "verified cites": f"{sum(x.verified for x in c.citations)}/{len(c.citations)}",
                            "analyst note": c.analyst_note} for c in p.candidates])
        edited = st.data_editor(df, hide_index=True, width="stretch", num_rows="dynamic", key="cand_ed",
                                column_config={"status": st.column_config.SelectboxColumn(options=["proposed", "accepted", "edited", "rejected"]),
                                               "type": st.column_config.SelectboxColumn(options=["direct", "indirect", "substitute"]),
                                               "verified cites": st.column_config.TextColumn(disabled=True)})
        with st.expander("Evidence for each candidate"):
            for c in p.candidates:
                st.markdown(f"**{c.name}** — {c.justification}\n{cite_md(c.citations)}")
        st.subheader("Comparison features (dimensions)")
        st.caption("Confirm with the client (PDD step 4). These become the Feature Comparison rows.")
        fdf = pd.DataFrame([f.model_dump() for f in p.features] or [{"category": "", "name": "", "description": ""}])
        fed = st.data_editor(fdf, hide_index=True, width="stretch", num_rows="dynamic", key="feat_ed")
        c1, c2 = st.columns(2)
        if c1.button("💾 Save scope"):
            old = {c.name: c for c in p.candidates}
            new = []
            for r in edited.to_dict("records"):
                if not r.get("name"):
                    continue
                c = old.get(r["name"]) or Candidate(name=r["name"], status="accepted")
                changed = any(str(r[k] or "") != str(v or "") for k, v in
                              [("website", c.website), ("type", c.type), ("justification", c.justification)])
                c.website, c.type, c.size_group = r["website"] or "", r["type"] or "direct", r["size group"] or ""
                c.segment = r.get("segment") or ""
                c.geography, c.justification, c.analyst_note = r["geography"] or "", r["justification"] or "", r["analyst note"] or ""
                c.status = "edited" if changed and r["status"] in ("proposed", "accepted") else r["status"]
                new.append(c)
            p.candidates = new
            p.features = [FeatureDef(**{k: (r[k] or "") for k in ("category", "name", "description")})
                          for r in fed.to_dict("records") if r.get("name")]
            p.add_log("gate1: scope saved")
            save(p)
            st.success("Saved.")
        n_ok = len(runner.approved(p))
        if c2.button(f"✅ Approve scope ({n_ok} competitors) → Gate 1 complete", disabled=n_ok == 0 or not p.features):
            p.stage = "collection"
            p.add_log(f"GATE 1 approved: {[c.name for c in runner.approved(p)]}")
            save(p)
            st.rerun()

# ---------------------------------------------------------------- gate 2
with tab2:
    ok = runner.approved(p)
    if p.stage in ("intake", "gate1"):
        st.info("Approve the scope at Gate 1 first.")
    else:
        missing = [c.name for c in ok if not (p.record(c.name) and p.record(c.name).cells)]
        c1, c2 = st.columns([3, 1])
        c1.write(f"{len(ok)} approved competitors · {len(ok) - len(missing)} researched")
        if missing and c2.button(f"🔎 Research {len(missing)} competitor(s)", type="primary"):
            run_step("Collecting data", runner.collect, p)
        if p.competitors:
            name = st.selectbox("Competitor", [r.name for r in p.competitors], key="g2comp")
            rec = p.record(name)
            cells = {**rec.cells, **rec.pricing}
            allc = [c for cell in cells.values() for c in cell.citations]
            st.caption(f"{len(rec.sources)} sources · {sum(c.verified for c in allc)}/{len(allc)} quotes verified · "
                       f"{sum(1 for c in cells.values() if c.confidence == 'unavailable')} unavailable")
            if st.button("Accept all cells with verified evidence"):
                for cell in cells.values():
                    if cell.status == "proposed" and cell.verified:
                        cell.status = "accepted"
                save(p)
                st.rerun()
            show = st.radio("Show", ["All fields", "Needs attention (low confidence / unavailable)"], horizontal=True, key=f"show_{name}")
            with st.form(f"g2_{name}"):
                decisions = {}
                for m in ALL_METRICS + PRICING:
                    cell = cells.get(m.key) or Cell()
                    if show != "All fields" and cell.confidence not in ("low", "unavailable"):
                        continue
                    st.markdown(f"**{m.label}** · {CONF_BADGE[cell.confidence]} · _{cell.status}_  \n<small>{m.question}</small>",
                                unsafe_allow_html=True)
                    c1, c2 = st.columns([3, 1])
                    val = c1.text_area(m.label, cell.value, key=f"v_{name}_{m.key}", label_visibility="collapsed", height=90)
                    status = c2.radio("Decision", ["proposed", "accepted", "rejected"], key=f"s_{name}_{m.key}", horizontal=False,
                                      index=["proposed", "accepted", "rejected"].index(cell.status if cell.status != "edited" else "accepted"))
                    rerun = c2.checkbox("Send back", key=f"r_{name}_{m.key}")
                    with st.expander("Evidence" + (f" · note: {cell.note}" if cell.note else "")):
                        st.markdown(cite_md(cell.citations))
                    decisions[m.key] = (val, status, rerun)
                fb2 = st.text_input("Feedback for cells sent back", key=f"fb2_{name}")
                a, b = st.columns(2)
                save_clicked = a.form_submit_button("💾 Save decisions", type="primary")
                rerun_clicked = b.form_submit_button("🔁 Re-run cells marked 'Send back'")
            if save_clicked or rerun_clicked:
                for k, (val, status, _) in decisions.items():
                    target = rec.pricing if k in collect_mod.PRICING_BY_KEY else rec.cells
                    cell = target.setdefault(k, Cell())
                    if val != cell.value:
                        cell.value, cell.status = val, "edited"
                    elif cell.status != "edited" or status == "rejected":
                        cell.status = status
                save(p)
                keys = [k for k, (_, _, r) in decisions.items() if r]
                if rerun_clicked and keys:
                    with st.spinner(f"Re-running {len(keys)} cell(s)…"):
                        collect_mod.rerun(rec, p.intake, keys, fb2, llm())
                    p.add_log(f"gate2: re-ran {keys} for {name}: {fb2}")
                    save(p)
                st.rerun()
            with st.expander(f"All {len(rec.sources)} sources"):
                st.markdown("\n".join(f"- [{s.id}] ({s.kind}) [{s.title[:90]}]({s.url})" for s in rec.sources if not s.url.startswith("search://")))
            if st.button("🔁 Re-research this competitor from scratch"):
                run_step(f"Re-collecting {name}", runner.collect, p, names=[name])
        if p.competitors and not missing:
            pending = sum(1 for r in p.competitors for c in {**r.cells, **r.pricing}.values() if c.status == "proposed")
            if st.button(f"✅ Approve data → Gate 2 complete ({pending} cells still unreviewed)"):
                p.stage = "synthesis"
                p.add_log(f"GATE 2 approved ({pending} cells unreviewed)")
                save(p)
                st.rerun()

# ---------------------------------------------------------------- gate 3
with tab3:
    if p.stage not in ("synthesis", "gate3", "export"):
        st.info("Approve the data at Gate 2 first.")
    else:
        c1, c2, c3 = st.columns([2, 1, 1])
        fb3 = c1.text_input("Feedback for re-score / re-synthesis (optional)", key="fb3")
        if c2.button("🧮 Score features", type="primary"):
            run_step("Scoring features", runner.score, p, feedback=fb3)
        if c3.button("🧠 SWOT, VoC & insights", type="primary"):
            run_step("Synthesising", runner.synthesize, p, feedback=fb3)
        with st.expander("Datadvise Feature Scoring Guide"):
            st.text(guide_text())
        if p.competitors:
            name = st.selectbox("Competitor", [r.name for r in p.competitors], key="g3comp")
            rec = p.record(name)
            if rec.features:
                st.markdown("**Feature scores** — edit score/notes, set status; '?' = insufficient evidence")
                needs = [f for f in rec.features if f.score is None or not any(c.verified for c in f.citations)]
                st.caption(f"Check these {len(needs)} first: in the pilot, scores backed by a verified quote agreed with "
                           "the analysts' scores 79% of the time (within 1 point); scores without one only 39%.")
                only = st.checkbox(f"Show only the {len(needs)} scores that need checking", key=f"needs_{name}")
                shown = needs if only else rec.features
                fdf = pd.DataFrame([{"status": f.status, "category": f.category, "feature": f.feature,
                                     "score": f.score, "standard": f.standard, "premium": f.premium, "enterprise": f.enterprise,
                                     "confidence": f.confidence, "context note": f.rationale,
                                     "evidence": " | ".join(f"{'✓' if c.verified else '⚠'} {c.quote}" for c in f.citations)}
                                    for f in shown] or [{"status": "", "feature": "(none)"}])
                fe = st.data_editor(fdf, hide_index=True, width="stretch", key=f"fs_{name}",
                                    column_config={"status": st.column_config.SelectboxColumn(options=["proposed", "accepted", "edited", "rejected"]),
                                                   "score": st.column_config.NumberColumn(min_value=0, max_value=5, step=0.5),
                                                   "evidence": st.column_config.TextColumn(disabled=True, width="large"),
                                                   "confidence": st.column_config.TextColumn(disabled=True)})
                c1, c2 = st.columns(2)
                if c1.button("💾 Save scores", key=f"savefs_{name}"):
                    for f, r in zip(shown, fe.to_dict("records")):
                        new_score = None if pd.isna(r["score"]) else float(r["score"])
                        if new_score != f.score or (r["context note"] or "") != f.rationale:
                            f.score, f.rationale, f.status = new_score, r["context note"] or "", "edited"
                        else:
                            f.status = r["status"]
                    save(p)
                    st.success("Saved.")
                if c2.button("🔁 Re-score this competitor with feedback", key=f"rs_{name}"):
                    run_step(f"Re-scoring {name}", runner.score, p, names=[name], feedback=fb3)
            if rec.swot:
                with st.form(f"swot_{name}"):
                    st.markdown("**SWOT**")
                    cols = st.columns(2)
                    new_swot = {k: cols[i % 2].text_area(k.title(), rec.swot[k].value, height=180, help=SWOT_QUESTIONS[k])
                                for i, k in enumerate(SWOT_QUESTIONS) if k in rec.swot}
                    narrative = st.text_area("Strategic narrative (“X is winning in Y due to Z”)", rec.narrative.value)
                    battle = st.text_area("Battlecard — how the client wins", rec.battlecard.value, height=140)
                    if st.form_submit_button("💾 Save synthesis"):
                        for k, v in new_swot.items():
                            if v != rec.swot[k].value:
                                rec.swot[k].value, rec.swot[k].status = v, "edited"
                            else:
                                rec.swot[k].status = "accepted"
                        rec.narrative.value, rec.battlecard.value = narrative, battle
                        save(p)
                        st.success("Saved.")
                st.markdown("**Voice of the Customer** (verbatim, verified quotes only)")
                for q in rec.voc:
                    st.markdown(f"{'👍' if q.sentiment == 'positive' else '👎'} “{q.text}” — [{q.citation.url[:60]}]({q.citation.url})")
        if p.insights.executive_summary.value:
            st.subheader("Cross-competitor insights")
            st.caption("Checkpoint: insights must be strategic, not just descriptive.")
            with st.form("insights"):
                fields = {"executive_summary": "Executive summary", "white_space": "White space & gaps",
                          "trends": "Trends across competitors", "implications": f"Implications for {p.intake.client_name}"}
                vals = {k: st.text_area(lab, getattr(p.insights, k).value, height=160) for k, lab in fields.items()}
                if st.form_submit_button("💾 Save insights"):
                    for k, v in vals.items():
                        getattr(p.insights, k).value = v
                    save(p)
            if st.button("✅ Approve synthesis → Gate 3 complete"):
                p.stage = "export"
                p.add_log("GATE 3 approved")
                save(p)
                st.rerun()

# ---------------------------------------------------------------- export
with tab4:
    if p.stage != "export":
        st.info("Complete Gate 3 to export client deliverables. (A draft export is available below for internal review.)")
    if st.button("📦 Generate Excel · Insight deck · Battlecards", type="primary"):
        stage = p.stage
        paths = runner.export(p)
        if stage != "export":
            p.stage = stage  # a draft export does not advance the workflow
        save(p)
        st.session_state.exports = [str(x) for x in paths]
    for path in st.session_state.get("exports", []):
        with open(path, "rb") as fh:
            st.download_button(f"⬇️ {path.split(chr(92))[-1].split('/')[-1]}", fh.read(), file_name=path.split(chr(92))[-1].split("/")[-1])

with tab5:
    st.code("\n".join(reversed(p.log)) or "(empty)")
