# Reference patterns (what the tool is modelled on)

This file keeps the *patterns* learned from the Datadvise reference material so the design intent
survives without the original files. It contains no client data.

The originals are kept **locally only** in `reference_private/` (git-ignored, never commit):

| File | What it is | Used for |
|---|---|---|
| `Competitive Intelligence Process.docx` | Datadvise SOP | Phases, inputs, checkpoints, deliverables, timings |
| `Datadvise Competitive Analysis PDD Draft 09222025 (3).docx` | Process Definition Document (as-is manual process) | Step-by-step flow, Overview page fields, exceptions, ROI variables |
| `Prismm Comp Analysis v1 (1).xlsx` | A real client workbook (confidential) | Template layout, metric rows, feature matrix, scoring guide |
| `Prismm Research - Client Approved.pptx` | A real client deck (confidential) | Deck structure, per-competitor slide pattern, theme |

---

## 1. The process (SOP + PDD)

**Inputs (intake):** client product/service and positioning · target markets and segments ·
known/suspected competitors · competitive dimensions of interest (pricing, features, marketing,
channels) · business goals (differentiation, messaging, GTM, pricing). Inputs may need preliminary
research and are **confirmed by the client before research starts**.

**Phases**
1. **Define scope** – Google "top competitors in the X space", prioritise credible sources; list
   direct, indirect and substitute competitors. Preliminary list is typically **8–10, up to 20+**,
   grouped by size (revenue, headcount) and geography. **Client confirms the list and the
   dimensions/metrics** before data collection.
2. **Data collection** (most tedious step) – hyperlink each company; scrape website (overview,
   About, explainer videos, case studies); LinkedIn About for description/positioning; Google latest
   press releases; reviews (G2, Capterra, Reddit, Trustpilot); job listings (priorities, hiring);
   news/funding (Crunchbase, PitchBook); social/content (LinkedIn, YouTube, blogs, SEO tools);
   sentiment (forums, Glassdoor); SimilarWeb, BuiltWith, Wayback Machine. An LLM with verifiable
   sources may be used for brand positioning.
3. **Synthesis** – SWOT (or SOAR) per competitor; feature comparison scored with the proprietary
   Feature Scoring Guide; strategic narratives: *"Competitor X is winning in Y due to Z"*.
4. **Strategic insight extraction** – white space and gaps; trends across competitors (e.g.
   "everyone shifting to X pricing"); implications for the client (opportunities + threats).
   Future wish: market-map visual, Blue Ocean / consulting-style frameworks.

**Internal checkpoints:** after defining the competitive universe · after data for the top 3
competitors · before delivery (insights must be **strategic, not descriptive**).
→ Implemented as Gate 1 / Gate 2 / Gate 3.

**Exception:** data unavailable → use proxies and document assumptions.
→ Implemented as `confidence = "unavailable"` + `note`.

**Deliverables:** competitor profiles (1 page each) · competitor matrix (features, pricing,
positioning) · battlecards · strategic insight summary (threats, opportunities, gaps, risks) ·
optional recorded walkthrough.

**Manual timing (3–5 competitors):** scope 1 day · collection 3–4 days · synthesis 2–3 days ·
packaging 1 day → **7–9 business days**. PDD ROI estimate: ~1,920 manual hours/year.
ROI variables to track: hours saved per project, turnaround (manual vs AI), inputs per project,
number of sources.

**Good-practice rules for analysts (onboarding notes):** avoid confirmation bias and reliance on a
single source; know the strategic-vs-descriptive difference.

## 2. Workbook template (Competitive Analysis .xlsx)

Colour-coded sections: comp analysis = green.

**Company Analysis sheet** – columns: Section | Metric | *What it means?* | one column per
competitor. Rows (the "What it means?" text is reused as the AI's research question — see
`ca_tool/knowledge/template.py`):
Description · Brand Position · Number of <domain units> (e.g. venues) · Deployment Speed ·
Max User Capacity · Services · USVP · Customer Focus · Positive Reviews · Negative Reviews ·
Innovation · Customer Service · Relationships & Partnerships · Marketing Channels ·
SWOT (4 rows) · Tech Stack · Funding/Capitalization · Additional Links.
Note: some rows are **industry-specific** (e.g. "number of venues") and should be configurable per
engagement.

**Feature Comparison sheet**
- Terminology: Standard = basic plan with core features · Premium = basic + advanced ·
  Enterprise = full suite, unlimited access + support.
- Roadmap key: available today · on roadmap (≤12 months) · not on roadmap.
- Top rows: company description, pricing tiers, standard recurring fees, trial period, rationale.
- Per competitor a 5-column block: **Standard | Premium | Enterprise (True/False) | Score | Context Notes**.
- Features grouped by category (reference had ~50 features in: Design & Visualisation,
  Planning & Management, Analytics, Support, Integration Types). The client's own product is
  column one.
- A roll-up sheet shows **category averages** per competitor; unknown = "?".

**Feature Scoring Guide (0–5)** — each level judged on Presence, Quality, Maturity:
0 Absent · 1 Basic · 2 Developing · 3 Competent · 4 Advanced · 5 Leading.
Application: comprehensive research (trials, demos, user feedback, reports) · objective scoring
without bias toward the client · contextual analysis (quality can offset presence depending on
strategic importance). Full text: `ca_tool/knowledge/scoring.py`.

The reference workbook also held market sizing (TAM/SAM/SOM), industry evaluation and financial
projection sheets — separate services, out of scope for v1.

## 3. Client deck (Insight Deck .pptx)

- 16:9, Arial. Theme: dark plum `#3D304F`, off-white `#FAFAFA`, accents lavender `#CCB0E5`,
  mint `#8AE3D1`, sky `#6ED1FC`, amber `#FAC259`, orange `#F58F4D`, grey `#DADADA`.
- Every content slide has a **"Source: …"** footer and a page number; confidentiality notice.
- Order: title → executive summary (trends) → agenda (repeated as section dividers) → market trends
  → market insights / sizing → demand drivers → **competitor analysis + Voice of Customer** →
  growth opportunities / new verticals → per-competitor pages → AI/tech trends → links → pricing
  proposal (optional) → thank you.
- **Per competitor, 3–4 slides:**
  1. *"<Company> Overview"* – Foundation (year), Headquarter, Geographies, # of employees, target
     market, primary use cases, deployment, brand positioning, USP, auxiliary services,
     innovation, partnerships.
  2. SWOT – four quadrants.
  3. Voice of the Customer (+ve) and (-ve) – verbatim review quotes.
- Also used: segmentation of competitors by client focus, market landscape/categorisation slides,
  "customers cited N key differentiators" slides with quotes.
→ Implemented in `ca_tool/export/pptx.py` (title, summary, insights, matrix, per-competitor pages,
  battlecards). Market sizing/trend slides are not generated yet.

## 4. Design decisions that follow from these patterns
- Human-in-the-loop at the three SOP checkpoints; the analyst can send work back instead of fixing it.
- Citation per cell, verified against the fetched page; unverified = low confidence.
- Unknown is shown as "Undisclosed"/"?" rather than guessed (matches the reference workbook).
- Industry-specific rows and the feature list are proposed per engagement and confirmed at Gate 1.
