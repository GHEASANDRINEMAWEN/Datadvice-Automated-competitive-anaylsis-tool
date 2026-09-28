# Competitive Analysis Automation

An AI-enabled tool that automates the Datadvise competitive intelligence process end to end — competitor identification, cited data collection, feature scoring, SWOT drafting, and generation of the final deliverables (populated Excel template, battlecards, and client insight deck) — with a **human in the loop** at every critical step.

The AI produces; the analyst approves.

## How it works

The workflow runs through three human approval gates that mirror the client checkpoints already used in the manual process:

```
Client intake
     │
     ▼
AI finds competitors (8–20 cited candidates)
     │
     ▼
GATE 1 — Analyst approves scope ──► client confirms list
     │
     ▼
AI collects data (websites, reviews, press, jobs — citation per cell)
     │
     ▼
GATE 2 — Analyst reviews data ──► send back for re-run
     │
     ▼
AI drafts scores (0–5), SWOTs, profiles, deck slides
     │
     ▼
GATE 3 — Analyst adjudicates ──► send back for rescore
     │
     ▼
Auto-generated outputs: Excel · battlecards · insight deck (PPTX)
```

At every gate the analyst can **accept, edit, or reject** — and bounce weak work back to the AI for a re-run instead of fixing it by hand. Every AI-proposed value carries a citation, so review takes seconds, not hours.

## Key features

- **Competitor discovery** — proposes a preliminary list of 8–20 candidates with one-line justifications and sources
- **Cited data collection** — populates the Competitive Analysis template with a citation for every cell and confidence flags where data was unavailable
- **Feature scoring** — applies the proprietary 0–5 scoring guide with evidence quotes attached to every score
- **Draft synthesis** — SWOTs, competitor profile pages, and voice-of-customer summaries
- **Output generation** — exports the populated Excel workbook, battlecards, and the client insight deck (PPTX) in the house format

## Architecture

The tool is vendor-independent by design. All business logic lives above an AI abstraction layer; the model underneath is a swappable engine.

| Layer | Contents | Owner |
|---|---|---|
| Analyst app | Intake form, 3 approval gates, review screens, export | Datadvise IP |
| Workflow engine | Encoded scoring guide, credible-sources list, templates, search & scrape layer | Datadvise IP |
| AI abstraction layer | One internal interface, any model behind it | Datadvise IP |
| Engine | Gemini API (current) · Claude / GPT / local models (swap-in) | Replaceable supplier |

**Current engine: Google Gemini API.** The free tier is used for development with dummy/public data only. Client-confidential data runs on the paid tier, where data is not used for model training.

## Getting started

```bash
# clone the repo
git clone <repo-url>
cd competitive-analysis-automation

# install dependencies
pip install -r requirements.txt

# configure environment
cp .env.example .env
# then edit .env and add your key:
# GEMINI_API_KEY=your_key_here

# run
python app.py
```

> **Note:** never commit your `.env` file or API keys. Make sure `.gitignore` excludes it.

## Project status & roadmap

Built at ~2 hrs/day over a 9-week plan:

- [ ] **Weeks 1–2 · Foundation** — template schema locked, scoring guide + source list encoded, intake and competitor-finder
- [ ] **Weeks 3–5 · Data engine** — cited research passes, template population, confidence flags, Gate 2 review screen
- [ ] **Weeks 6–7 · Synthesis** — draft scores with evidence, SWOTs, profiles, Gate 3 adjudication view
- [ ] **Weeks 8–9 · Outputs & pilot** — Excel/PPTX export, side-by-side pilot run vs the manual process

**First demo target (week 3):** one competitor fully researched and filled into the template automatically.

## Success measures

- Turnaround per engagement: from 7–9 business days toward 2–3
- Analyst hours per engagement: down sharply
- Sources consulted per competitor: up
- Analyst acceptance of AI-drafted scores: 80%+ accepted with light edits by end of pilot

## Confidentiality

This repository relates to Datadvise's proprietary competitive intelligence methodology. Client engagement data must never be committed to the repo or processed through free-tier AI services.

---

*Maintained by Ghea · Datadvise*
