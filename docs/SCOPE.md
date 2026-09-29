# Scope & Task Plan

This tool automates the Datadvise Competitive Intelligence process as documented in
`Competitive Intelligence Process.docx` and the PDD (09/22/2025), and produces outputs in the
format of the Prismm reference deliverables (`Prismm Comp Analysis v1.xlsx`,
`Prismm Research - Client Approved.pptx`).

## In scope (v1)

| Process step (PDD) | Tool module | Output |
|---|---|---|
| 1 · Client discovery & intake | `ca_tool/models.py::Intake`, app "Intake" tab | Intake record |
| 2–3 · Define competitive scope (8–20 candidates, grouped by size/geo) | `pipeline/discover.py` | Candidate list with justification + citations |
| 4 · Client confirms companies & dimensions | **Gate 1** (app) | Approved competitor list + feature dimensions |
| 5–9 · Data collection (website, LinkedIn, press, reviews, funding, positioning) | `research/*`, `pipeline/collect.py` | Company Analysis metrics + Overview fields, one citation per cell |
| Data unavailable → proxy + documented assumption | `Cell.confidence = "unavailable"`, `Cell.note` | Flagged cells |
| Internal check after data gathering | **Gate 2** (app) | Accepted / edited / re-run cells |
| 10 · SWOT per competitor, feature comparison scored 0–5 with the Datadvise scoring guide | `pipeline/score.py`, `pipeline/synthesize.py` | Scores + evidence, SWOTs, VoC, narratives |
| 11 · Strategic insight extraction (white space, trends, implications) | `pipeline/synthesize.py::insights` | Insight summary |
| Internal check before delivery ("strategic, not descriptive") | **Gate 3** (app) | Adjudicated scores/SWOTs |
| 12–14 · Company Overview page, SWOT page, Voice of Customer | `export/pptx.py` | Insight deck + battlecards |
| Populated Competitive Analysis template | `export/excel.py` | Excel workbook (Company Analysis, Feature Comparison, Scoring Guide, Sources) |

## Out of scope (v1)
Market sizing (TAM/SAM/SOM), industry evaluation, pricing proposals, market-map visual,
Blue Ocean / SOAR frameworks, paid data tools (Crunchbase/PitchBook/SEMrush APIs). These appear
in the Prismm workbook/deck but are separate services; the architecture leaves room for them
(PDD §5: modular design).

## Design principles
1. **AI proposes, analyst approves.** Every AI value is a `Cell` with status
   `proposed → accepted | edited | rejected`. Nothing is exported unreviewed without being marked as such.
2. **Citation per cell, verified.** The AI only sees pages our own search/scrape layer fetched.
   It must quote evidence; the tool checks each quote against the fetched page text
   (`research/verify.py`). Unverified quotes are flagged in the review screens.
3. **Vendor-independent.** All model calls go through `ca_tool/llm/base.py::LLM`. Gemini is the
   current engine; swapping means adding one class.
4. **Confidentiality.** Project data lives in `projects/` (git-ignored). Client-confidential
   engagements must use a paid-tier key.

## Engine notes (verified 2026-09-28 on the current key)
- Gemini Google Search grounding returns 429 (no quota on this key/tier) → the tool uses its own
  search layer (DuckDuckGo via `ddgs`) + page fetching. This is also the more controllable design.
- Larger models intermittently return 503 (high demand) → the client retries with backoff and
  falls back down a model list (`GEMINI_MODELS` in `.env`).

## Known limitations (found while cross-checking the first runs)
- **JavaScript-rendered sites** (e.g. pricing pages that load prices client-side) return little
  text. Mitigated by trying standard paths (`/pricing`, `/about`, `/careers`…) and third-party
  sources; a headless browser (Playwright) is the next step if this proves common.
- **LinkedIn / Crunchbase / G2 often block scrapers** (login walls). Their search snippets are still
  used; values sourced only from snippets tend to be low confidence.
- **The model sometimes answers from background knowledge** despite instructions (e.g. a founding
  year not present on the cited page). The quote check catches this: such cells are marked
  unverified / low confidence for the analyst. Treat ⚠️ cells as "needs checking", not as wrong.
- **Product vs parent company**: for product-line competitors (e.g. "Cvent Event Diagramming",
  formerly Social Tables) overview facts may describe either; the analyst should name the
  competitor precisely at Gate 1.
- **Free-tier engine availability**: larger Gemini models intermittently return 503/429; the
  client falls back to `gemini-3.1-flash-lite`. Quality of synthesis will improve on a paid tier.
- Search runs through DuckDuckGo's `ddgs` metasearch, which can rate-limit under heavy use.

## Task list

### Weeks 1–2 · Foundation
- [x] Repo hygiene: `.gitignore`, `.env.example`, `requirements.txt`
- [x] AI abstraction layer + Gemini engine (retry, fallback, JSON-schema output)
- [x] Data model: Intake, Candidate, Cell/Citation, CompetitorRecord, FeatureScore, Project
- [x] Encode scoring guide (0–5), Company Analysis metrics ("What it means?" prompts), Overview fields
- [x] Credible-sources list (from process doc) – **replace with the official Datadvise list when provided**
- [x] Search & scrape layer with source registry
- [x] Competitor finder (Gate 1 input)
- [x] Streamlit analyst app: intake + Gate 1

### Weeks 3–5 · Data engine
- [x] Per-competitor research pass (site crawl of key pages + targeted searches)
- [x] Template population with citation + confidence per cell, quote verification
- [x] Gate 2 review screen with accept/edit/reject and re-run with feedback
- [ ] Official credible-sources list prioritisation (blocked: list not provided)

### Weeks 6–7 · Synthesis
- [x] Feature dimension proposal (analyst-editable), 0–5 scoring with evidence
- [x] SWOT, Voice of Customer, strategic narratives, cross-competitor insights
- [x] Gate 3 adjudication view

### Weeks 8–9 · Outputs & pilot
- [x] Excel export in the Competitive Analysis template layout
- [x] Insight deck + battlecards (PPTX), using the reference deck's theme colours/fonts
- [ ] Apply the house PPTX master/logo (needs a clean, non-confidential template file)
- [x] Side-by-side pilot vs the manual process; track ROI variables (PDD appendix) — see results below
- [x] Market-map slide (competitive landscape by segment)

### Verification status (2026-09-28)
- 22 offline tests pass (`python -m pytest tests`), incl. headless app tests of intake → Gate 1,
  and Gate 2 / Gate 3 / export (edit, reject, bulk-accept, save scores/SWOT, approve, download).
- App now has an Overview tab (stage, next step, per-competitor status, what needs review) and a
  live activity feed during runs (searches, pages read, AI step, quote-check result).
- Research layer: browser-like fetching reads review/directory sites that block scripts
  (e.g. Software Advice, SourceForge); G2/Capterra/Trustpilot/Crunchbase still block → snippets only.
- Engine: 5-model fallback list plus a wait-and-retry round when all models are busy (seen live:
  all five overloaded at once, run still completed).
- Live end-to-end run on a dummy client (3 competitors) produced all three deliverables; slides
  rendered and reviewed. Matterport feature scores agree with the Prismm analysts' manual scores
  on 6 of 8 comparable features (others within 1–2 points).
- Gate 2/3 screens render without errors but have only been exercised headlessly, not clicked
  through by an analyst on real data yet — first thing to do in the pilot.

### Pilot vs a completed manual engagement (2026-09-29)
Run with public inputs only (client's public website; no names or content from the confidential
deliverables sent to the AI). Comparison done locally by `python -m ca_tool.pilot`; the detailed report
stays in the git-ignored `projects/<id>/outputs/`.

| Measure | Result |
|---|---|
| Competitor discovery recall | 5 of 15 manual competitors in one run (1 before segment-aware discovery); 8 of the 9 core competitors found across runs. The 6 misses outside the core were new-vertical/corporate players the analysts added from client context |
| Overview facts (year, HQ, geographies, headcount) | 11 of 16 agree; every disagreement had a verified quote (product-vs-parent company, sources disagreeing, headcount at a different date) |
| Feature scores on the analysts' own 43 features | 119 compared: 39% exact, 70% within 1 point → 74% after the unsupported-zero rule |
| … with a verified evidence quote | **79% within 1 point, no bias** (mean gap 0.84) |
| … without one | 39% within 1 point, 1.8 points too low |
| Quotes verified | 96% (131/137) |
| Turnaround, 5 competitors | 25 min machine time (16 of it discovery, inflated by free-tier congestion) vs 56–72 working hours manually |

Changes made because of the pilot: segment-aware discovery; a second "alternatives to X" and
completeness pass; client's former names excluded; search-result sources no longer truncated;
a 0 score without verified evidence becomes "?" (not found ≠ absent); Gate 3 surfaces the scores
that need checking first. Still weak: run-to-run variation in discovery; vendors never found by
search (fix: analyst adds them at Gate 1, or a paid search API); thin-evidence competitors.

### Next up
- Headless browser fetch for JS-rendered pricing pages (biggest data gap seen so far)
- Official Datadvise credible-sources list; house template/logo
- Run a pilot on a past, completed engagement and compare against the manual deliverable
