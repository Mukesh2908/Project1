# Profile Match Engine — JD-driven, evidence-based, user-controlled profile matching

**Status:** plan and architecture. Build phase by phase per §22.
**Version:** 3.0 — v2.0 plus the review findings and the decisions in `decisions.md`.
**One-line principle:** AI interprets. Python calculates. Human decides.

**What changed in 3.0:** Streamlit replaces React and the HTTP API is dropped
(D13) · local models replaced by Gemini / Groq / NVIDIA NIM / OpenAI (D11) ·
privacy rebuilt around a provider allowlist (D12) · weights derived from the JD
instead of chosen from presets (D8) · Core and Secondary score the top 5
requirements only (D10) · dual-primary gate is a per-JD toggle (D5) · manager
corrections enter as verified evidence (D6) · a thin end-to-end slice lands in
week 3 (D7). Full changelog in §26.

## Contents

1. [Product overview](#1-product-overview)
2. [Core principles](#2-core-principles)
3. [Goals and non-goals](#3-goals-and-non-goals)
4. [End-to-end workflow](#4-end-to-end-workflow)
5. [System architecture](#5-system-architecture)
6. [Tech stack](#6-tech-stack)
7. [Pipeline A — profile ingestion](#7-pipeline-a--profile-ingestion)
8. [Pipeline B — JD analysis](#8-pipeline-b--jd-analysis)
9. [JD review, overrides and My Requirements](#9-jd-review-overrides-and-my-requirements)
10. [Skill proof engine](#10-skill-proof-engine)
11. [Scoring matrix](#11-scoring-matrix)
12. [Gate, verdicts, confidence and review](#12-gate-verdicts-confidence-and-review)
13. [Explanations](#13-explanations)
14. [What-if simulator](#14-what-if-simulator)
15. [Results, comparison, search and filters](#15-results-comparison-search-and-filters)
16. [Excel report](#16-excel-report)
17. [UI screens](#17-ui-screens)
18. [Data models, storage and config](#18-data-models-storage-and-config)
19. [LLM layer](#19-llm-layer)
20. [Privacy, security and fairness](#20-privacy-security-and-fairness)
21. [Project structure](#21-project-structure)
22. [Build plan](#22-build-plan)
23. [Testing and evaluation](#23-testing-and-evaluation)
24. [Risks and mitigations](#24-risks-and-mitigations)
25. [Roadmap](#25-roadmap)
26. [Changelog](#26-changelog)

---

## 1. Product overview

**What.** A web app for bench managers. Give it a JD — upload PDF/DOCX/TXT or
paste text — and it works out what the role mainly wants. The user reviews and
edits that reading, confirms a scoring matrix the system suggests from the JD,
and every bench profile is then scored on proof rather than keywords. Output is
a ranked list with detailed reasons and a clean Excel report.

**Why.** Keyword matching fails. "SQL" in a resume is not SQL experience. Was it
used in projects? How deeply? How long ago? A JD listing Python, SQL, Java,
Scala, Angular and React is usually hiring for one main skill.

**Scale.** ~100 profiles now; the design holds to 1,000+.

**Nature.** Decision support, not a hiring decision maker. The human always
decides.

**Runs.** Locally, single user. LLM calls go to configured cloud providers under
the rules in §20.

## 2. Core principles

1. **Main skill first** — detect the JD's main skill and judge every profile on
   it before anything else.
2. **Proof over keywords** — a skill counts by where it was used, how deeply,
   how long, how recently, in production, and by whom.
3. **AI interprets, Python calculates** — LLMs read text and tag evidence; every
   score is plain Python, so the same input gives the same score and every number
   is traceable.
4. **Human decides** — AI suggests, the user can override anything, overrides
   always win.
5. **Parse once, score many** — heavy LLM work runs once per resume; changing
   weights costs zero LLM calls.
6. **No score without evidence** — every point traces back to a quoted resume
   line, or to evidence a manager explicitly added.
7. **Surface uncertainty** — Match Score and Analysis Confidence are separate
   numbers; unclear cases go to a human review queue.
8. **Factual language** — "Evidence found", "No evidence found", "Partial
   evidence", "Requires verification". Never "definitely better" or "will succeed".
9. **Private by policy, enforced in code** — PII is masked before any LLM call
   and the provider allowlist is checked at the call boundary (§20).
10. **Vendor-neutral** — every model sits behind one provider interface.

## 3. Goals and non-goals

### Goals (MVP)

| # | Goal | Measure |
|---|---|---|
| G1 | Find the JD's real focus | Main skill correct on ≥ 9 of the 10 eval JDs (§23.2) |
| G2 | Kill keyword false positives | Skills-list-only skills never exceed 10% fit |
| G3 | User control | Weights editable; re-rank under 1 s for 100 profiles |
| G4 | Explainable | Every dimension shows score, weight, contribution, evidence, gaps, confidence |
| G5 | Low LLM cost | Early deterministic filter, cached parsing, no LLM on weight change |
| G6 | Auditable output | One-click Excel carrying config, versions and evidence |
| G7 | Internally consistent | Top-5 overlap ≥ 70% against the labelled set |

> **On G7.** The labelled set is self-labelled (D1), so this measures
> consistency with your own judgment, not agreement with bench managers
> generally. It is a regression guard — it stops a prompt or taxonomy change
> quietly wrecking the rankings — and it should not be reported as validation.
> Real validation needs a second rater; the cheapest version is one manager
> looking at one ranked list at week 3.

### Non-goals

- Auto-reject or auto-hire anyone without human review.
- Infer or use sensitive attributes — age, gender, religion, caste, race,
  health, politics, marital status, photo.
- Treat keyword occurrence as experience.
- v1: multi-user login, cloud hosting, OCR for scanned PDFs, non-English
  resumes, HRMS/ATS integration.

## 4. End-to-end workflow

```
JD upload / paste
  → JD parsing
  → JD intent — what is this role really about?
  → skill and responsibility extraction
  → focus scores → Primary / Core / Secondary + importance
  → conflict detection + JD confidence
  → AI suggestion screen ──► accept | edit | override | add My Requirements
  → suggested scoring matrix, derived from the JD  ◄── what-if simulator
  → candidate pool, already parsed once into evidence cards
  → stage 1: cheap deterministic filter (primary + close family)
  → stage 2: skill proof per requirement, over stored evidence
  → stage 3: weighted score using the confirmed matrix
  → stage 4: main-skill gate → verdict + confidence + review flags
  → stage 5: explanations — why / why not higher / path to deployable
  → ranked and filtered results · comparison · human review queue
  → Excel report
```

**User steps.** ① upload profiles once → ② add a JD → ③ review the AI's reading
→ ④ confirm the suggested matrix → ⑤ results → ⑥ download Excel.

## 5. System architecture

```
A · Profile ingestion — once per resume
  resumes (PDF/DOCX/TXT)
    → text extract (PyMuPDF · python-docx)
    → PII mask (Presidio + regex)
    → sectioner (summary · skills · employment · projects · certs)
    → Profile Parser Agent — one project at a time, LLM
    → quote verifier (rapidfuzz, against the originating block)
    → evidence engine — evidence cards, quality, years, red flags
    → SQLite/Postgres  +  ChromaDB

  manager-added verified evidence ──────────────► evidence engine (D6)

B · JD analysis — per JD
  JD file or text
    → JD Analyzer Agent — intent + skill signals, LLM
    → focus scorer — tiers, importance, required levels
    → conflict detector + JD confidence
    → review and override — AI suggestion vs My version
    → weight deriver (pure Python, §11.2) → suggested matrix

C · Matching — re-runs instantly on any weight change
    → stage 1 filter (recall-oriented; exclusions always visible)
    → skill mapper — taxonomy, equivalence cache
    → skill proof engine — pure Python, reads evidence + vectors
    → dimension scores + weighted total — pure Python
    → gate · verdict · confidence · review flags

D · Output
    → explanation engine — templates filled from a facts JSON
    → Reason Writer Agent — 2-3 line summary only, grounded + linted
    → Streamlit: results · comparison · detail · review queue
    → Excel report
```

### Components

| Component | Job | LLM? |
|---|---|---|
| Text extractor | PDF/DOCX/TXT → text blocks | No |
| PII masker | Hide name, contact, DOB, gender, photo, address | No |
| Sectioner | Split into summary / skills / employment / projects / certs | Fallback only |
| Profile Parser Agent | One project block → tagged skill evidence | Yes |
| Quote verifier | Reject evidence the LLM cannot point to | No |
| Evidence engine | Build evidence cards, quality, years, flags, lane | No |
| JD Analyzer Agent | JD text → intent + skill signals | Yes |
| Focus scorer | Signals → focus scores, tiers, importance | No |
| Conflict detector | Contradictions in the JD + JD confidence | No |
| Weight deriver | JD config → suggested scoring matrix | No |
| Skill mapper | JD skill → evidence card, via taxonomy | No |
| Equivalence judge | Unknown skill pair → relation | Yes, rare, cached |
| Skill proof engine | Evidence → skill fit | No |
| Dimension scorer | Skill fits → dimension scores → weighted total | No |
| Gate and verdicts | Thresholds, verdicts, confidence, review flags | No |
| Explanation engine | Facts JSON → templated explanations | No |
| Reason Writer Agent | Facts JSON → 2-3 line summary | Yes |
| Excel reporter | 9-sheet XlsxWriter workbook | No |

### LLM call budget

| Trigger | Calls |
|---|---|
| New resume | 1 per project block, once ever |
| Re-upload of an unchanged resume | 0 |
| New JD | 1, cached by text hash |
| Unknown skill pair | 1, then cached forever |
| Candidate summary | 1 per candidate displayed, cached by config hash |
| Weight change or what-if | 0 |

## 6. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| UI | Streamlit | Multipage app; no separate frontend build (D13) |
| Backend | Python 3.11+, Pydantic v2, SQLAlchemy 2.x | Service layer called directly by the UI |
| HTTP API | *none in v1* | Services stay UI-agnostic; FastAPI is a day's work if a second consumer appears |
| Database | SQLite (dev and v1) → PostgreSQL (later) | JSON columns for evidence and facts |
| Migrations | Alembic | Needed from day one given the SQLite → Postgres path |
| Vector store | ChromaDB, local | Project/JD similarity, similar-JD lookup |
| Embeddings | `BAAI/bge-small-en-v1.5` via sentence-transformers | Local, CPU, 130MB; cloud embeddings configurable (D11) |
| Parsing | PyMuPDF, python-docx, plain text | OCR later |
| PII | Microsoft Presidio + regex, spaCy `en_core_web_sm` | Masked before every LLM call |
| LLM access | `AIProvider` over LiteLLM + Instructor | Gemini · Groq · NVIDIA NIM · OpenAI · Mock |
| Agent flow | LangGraph for the two multi-step pipelines | Plain functions everywhere else |
| Matching helpers | rapidfuzz, rank-bm25, dateparser | Quote check, dedupe, date parsing |
| Excel | XlsxWriter + pandas | Richer formatting than openpyxl for write-only reports |
| Background work | `threading` worker + `jobs` table, UI polls via `@st.fragment` | Streamlit re-runs on interaction, so long work stays off the render path |
| Dev tooling | uv, ruff, pytest, Hypothesis, Alembic | |

**On dropping FastAPI.** v2.0 split `frontend/` and `backend/` with seven route
modules. For one local user that is an HTTP hop and a second process buying
nothing. The seam that matters — UI-agnostic services — is preserved by keeping
`app/services/` and `app/scoring/` free of any Streamlit import, which §23.1
asserts as a test.

## 7. Pipeline A — profile ingestion

Runs once per resume. Re-uploading an unchanged file costs zero LLM calls.

### 7.1 Steps

1. **Hash and dedupe** — SHA-256 per file; unchanged files are skipped. Same
   person in two files (matched on an email/phone hash taken *before* masking) →
   keep the newest, mark the older superseded.
2. **Extract text** — PyMuPDF blocks, which preserve two-column reading order;
   python-docx paragraphs and tables. Under 200 characters per page → flag
   `Scanned — needs OCR` and exclude from matching.
3. **Mask PII** — name, email, phone, address, DOB, gender, marital status,
   photo, nationality. Real values go to `pii_map`, which never leaves the
   machine. The UI un-masks for display; LLMs never see them. §20.2 covers the
   recall requirement.
4. **Split sections** — regex headings first, LLM fallback when headings are
   unclear.
5. **Project and employment blocks** — title, client/domain, role, start and end
   dates, tech-stack line, responsibility bullets.
6. **Profile Parser Agent** — one project at a time. For every skill used,
   stated or implied, it returns: `skill`, `action`, `depth` L1–L5, `ownership`
   (self/team/vague), `production` (yes/no/unknown), `usage_context`
   (dev/test/support/analysis), `quote` (the exact line), `stack_line_only`,
   `implied`.
   Implied examples: "wrote stored procedures, CTEs" → SQL · "Delta merges in
   notebooks" → Databricks, PySpark, Delta Lake.
7. **Verify quotes** — a mention survives only if its quote matches the text of
   **the project block it came from** (not the whole document), at
   `token_set_ratio ≥ 90` on normalised text, with a minimum quote length of 25
   characters. Unverified → the mention is dropped. Invented evidence scores zero.
8. **Certifications** — name, issuer, year, active/expired, normalised via
   `certifications.yaml`.
9. **Evidence cards** — one per skill, built in code (§7.3).
10. **Candidate main skill (lane)** — strongest evidence across the latest two
    projects.
11. **Red flags and claim-vs-evidence** — in code (§7.5).
12. **Embed and store** — per-project text to Chroma, everything else to the DB.

> **Change from v2.0 (step 7).** v2.0 checked `partial_ratio ≥ 90` against the
> whole masked document, which false-accepts short quotes — a six-word phrase
> partial-matches a lot of text. Scoping to the originating block plus a length
> floor closes that, and it is the check the entire "no score without evidence"
> principle rests on.

### 7.2 Evidence quality

Not all statements are equal. Quality caps the depth a mention can prove.

| Where the skill appears | Quality | Max depth it can prove |
|---|---|---|
| Skills list, "familiar with" | weak | L1 |
| Project "Tech stack:" line only | weak_plus | L2 |
| Project responsibility bullet | medium | L3 |
| Employment responsibility with a direct action verb | strong | L4 |
| Production ownership or measurable impact ("cut runtime 60%", "live for 2M users") | very_strong | L5 |
| **Manager-added, verified (D6)** | **verified** | **L5, uncapped** |

> **Known confound.** Depth caps key on phrasing, and `ownership_part` (§10.2)
> keys on direct verbs — together roughly 35% of skill fit rides on how the
> resume is written, which tracks English fluency and writing culture rather
> than competence. "We migrated the platform" scores below "I migrated the
> platform" for identical work. §23.3 specifies the style-invariance test that
> bounds this; the `verified` tier gives managers a way to correct it case by
> case.

### 7.3 Evidence card

```json
{
  "React": {
    "mentions": {"skills_list": 1, "summary": 1, "project_lines": 8},
    "projects_used": 3,
    "hands_on_years": 3.5,
    "claimed_years": 4,
    "last_used": "current project",
    "max_depth": 4,
    "best_evidence_quality": "strong",
    "production": true,
    "ownership": "self",
    "usage_context": ["dev"],
    "evidence": [
      {"quote": "Built a component library used by 4 apps",
       "project": "Retail Portal", "quality": "strong", "source": "parsed"},
      {"quote": "Cut page load 40% with memoization and code-splitting",
       "project": "Retail Portal", "quality": "very_strong", "source": "parsed"}
    ]
  }
}
```

### 7.4 Rules computed in code, never by the LLM

- **Hands-on years** = the union of date ranges of projects where the skill was
  used, with overlaps merged. "Present" means today. A missing month is treated
  as mid-year and marked approximate. No dates at all → years unknown (see
  §10.2 for how the scorer handles that).
- **Skill years are not career years** — six years total career with 3.5 years
  of React means React uses 3.5.
- **Distinct lines only** — near-duplicate bullets (`rapidfuzz ≥ 95`) across
  projects count once.

### 7.5 Red flags and claim vs evidence

| Flag | Rule (default, configurable) | Effect |
|---|---|---|
| Claim vs evidence | claimed years − proven years ≥ 2 | Shown as "Claim: 5 yrs React · Evidence: ~2 yrs · Verification recommended"; proven years are used |
| Padding | ≥ 15 skills listed and < 40% proven in projects | Shown; lowers confidence |
| Stack-line only | Skill appears only in tech-stack lines | Depth capped at L2 |
| Wrong context | Used only in test/support while the JD role is dev | Depth capped at L2 |
| Copy-paste | ≥ 3 near-identical bullets across projects | Counted once; shown |
| Stale | Last used more than 4 years ago | Shown; recency rules in §10.3 |
| Undated | No project or employment dates | Confidence low → human review |
| Date conflicts | Overlapping full-time jobs, or end before start | Human review |
| Resume age | File or "last updated" older than 12 months | "Resume may be outdated" |
| Scanned PDF | Too little extracted text | Excluded until OCR (v2) |

### 7.6 Depth ladder

| Level | Name | SQL example |
|---|---|---|
| L1 | Mentioned | Skills list, "knowledge of" |
| L2 | Used | Basic SELECTs for data checks |
| L3 | Built | Joins, views, stored procedures in delivered work |
| L4 | Advanced | Tuned or designed — indexing, window functions |
| L5 | Led | Owned the design, reviewed or mentored others |

### 7.7 Manager-added verified evidence (D6)

A manager can add evidence to any profile from the candidate detail screen —
typically after an interview or from direct knowledge of the person's work.

- Stored in `manual_evidence`, never mutating the parsed record.
- Enters the evidence card as an entry with `quality: verified`,
  `source: manual`, carrying the author and timestamp.
- `max_depth` becomes `max(parsed_depth, verified_depth)`; `hands_on_years`
  takes the verified figure when supplied.
- Both readings are shown side by side in the UI and the Excel Evidence sheet,
  badged `Parsed` and `Verified`.
- Every entry is appended to the eval set as a labelled example.

Rationale for adding rather than overwriting is in `decisions.md` D6.

## 8. Pipeline B — JD analysis

### 8.1 Input

Upload PDF/DOCX/TXT, or paste into a text area and press **Analyze JD**. Stored
with a text hash, so the same JD reuses its cached analysis.

**Similar-JD reuse.** If a new JD is ≥ 85% similar to one configured before, the
UI offers to reuse its overrides and weights — and **shows a diff first**: which
skills, importance levels and weights differ between the two JDs. v2.0 offered a
bare yes/no, which is how a wrong primary skill propagates silently.

### 8.2 JD intent layer

Before any skill reading, the LLM writes the role intent: *"Frontend application
development for customer-facing banking apps"* → role family `frontend_dev`,
seniority, domain. Skills are then read in light of that intent, which is what
stops a 20–30-skill laundry list confusing the main skill.

### 8.3 JD Analyzer output

```json
{
  "job_title": "Senior Software Engineer — React",
  "role_intent": "Build customer-facing React web apps for a banking client",
  "role_family": "frontend_dev",
  "seniority": "senior",
  "domain": "BFSI",
  "responsibilities": ["..."],
  "years_of_experience": {"min": 4, "max": 7},
  "certifications": [{"name": "AWS Certified Developer", "level": "preferred"}],
  "education_requirements": [],
  "skill_signals": [
    {"skill": "React", "in_title": true, "in_opening": true,
     "responsibility_bullets": 4, "extra_mentions": 5,
     "strong_language": true, "optional_language": false,
     "required_years": 4, "depth_words": ["build", "optimize"]}
  ]
}
```

The LLM only tags signals. Focus scores, tiers, importance, confidence and
conflicts are all computed in code.

### 8.4 Focus score (code)

| Signal | Points |
|---|---|
| In job title | +40 |
| In opening lines | +15 |
| Each responsibility bullet requiring it | +8, max +32 |
| Each additional mention | +2, max +10 |
| Strong language — must, required, strong, expert, advanced, N+ years, extensive | +15 |
| Optional language — nice to have, plus, preferred, exposure, good to have | −15 |
| Same skill family as the top skill (`skill_families.yaml`) | +10 |

The UI shows the arithmetic:

```
React        Title +40 · Opening +15 · 4 bullets +32 · "4+ yrs" +15 · mentions +10   = 112
TypeScript   2 bullets +16 · Strong +15 · Same family +10                            =  41
```

### 8.5 Tier

- **Primary** — highest focus score, usually one. A **dual primary** is declared
  only when a second skill from a *different family* scores ≥ 80% of the top
  (React + Node.js full stack). How the gate treats a dual primary is a per-JD
  choice — see §12.1 and D5.
- **Core** — in at least one responsibility bullet, or same family as primary,
  or essential supporting tech. **Competing frameworks are excluded**: a skill
  the taxonomy marks `related` to the primary is a substitute for it, not a
  complement, so Angular on a React role stays Secondary and gets no
  same-family bonus. Read literally, §8.4's family bonus and this rule would
  tier Angular as Core on a React JD, which contradicts §9.1's own worked
  screen showing it Secondary at 0.
- **Secondary** — everything else. Never compensates for a missing primary.

### 8.6 Importance — separate from tier

| Importance | Detected from | Effect |
|---|---|---|
| Mandatory | must, required, "N+ yrs" | Acts as a gate (§12) and weight ×3 within its tier |
| Important | in responsibilities, strong language | Weight ×2 |
| Preferred | preferred, plus, good to have | Weight ×1 |
| Optional | exposure, nice to have | Weight ×0.5 |

Example: React = Primary + Mandatory · TypeScript = Core + Mandatory · Redux =
Core + Important · Python = Secondary + Preferred.

### 8.7 Required level

| JD wording | Required depth |
|---|---|
| exposure, familiar, basic | L2 |
| hands-on, working knowledge, good | L3 |
| strong, expert, advanced, tuning, optimization | L4 |
| lead, architect, own the design, mentor | L5 |

Years come from "N+ yrs"; otherwise from seniority — junior 1 · mid 3 · senior 5
· lead 8. Depth when unstated: junior L2 · mid L3 · senior L4 · lead L5.

### 8.8 JD analysis confidence (0–100, code)

| Evidence | Points |
|---|---|
| Primary in title | 30 |
| Primary in responsibilities | up to 30, 8 per bullet |
| Independent signals agree — title, opening, bullets, years | up to 20 |
| Strong or required language on the primary | 10 |
| Title ↔ responsibilities ↔ intent consistent | 10 |
| Each unresolved conflict | −10 |

≥ 80 High · 60–79 Medium · < 60 Low. Low means the user must confirm the primary
skill before matching can run.

### 8.9 Requirement conflict detector (code)

| Conflict | Example | Suggested action |
|---|---|---|
| Mandatory but low focus | React is primary, but "Java is mandatory" appears once | Confirm Java as Core, not Secondary |
| Two strong primaries, single-focus title | "Senior React Developer" + "must have 5+ yrs Spring Boot" | Dual primary or Core? |
| Years contradiction | "3–5 yrs total" but "7+ yrs React" | Fix years |
| Seniority mismatch | "Junior" title + "lead a team of 6" | Confirm seniority |
| Everything mandatory | More than 8 skills marked must | Pick the top 3 mandatory |

Shown as warning cards; the human resolves each. Unresolved conflicts lower JD
confidence and mark the run for review.

## 9. JD review, overrides and My Requirements

### 9.1 AI suggestion screen

```
JD Analysis                                        Confidence: 94% (High)
Role intent: Build customer-facing React web apps (BFSI)
Suggested primary: [ React ▼ ]
Why React?  ✓ in title  ✓ opening section  ✓ 4 responsibilities  ✓ "4+ years"

PRIMARY    React        112   Mandatory
CORE       TypeScript    41   Mandatory
           Redux         18   Important
           Next.js       16   Preferred
SECONDARY  Angular 0 · Python 0 · Java 0 · Scala 0 · SQL 0

⚠ 1 conflict to review
[ Accept ]  [ Edit skills ]  [ Add my requirements ]
```

### 9.2 Overrides — the user always wins

- Change the primary · move skills between tiers · change importance · add or
  remove skills, with autocomplete and synonyms from the taxonomy.
- Set minimum depth and years per skill · mark mandatory · add notes · override
  JD confidence.
- Two views — **AI suggestion** (read-only original) and **My version** (used for
  scoring) — plus a **Compare** diff.
- A source badge on every item: `AI` · `Edited` · `User-added`, with
  **Reset to AI**.
- Each confirmed version is saved as `jd_config v1, v2 …`, so any result stays
  reproducible.

### 9.3 My Requirements

| Requirement | Category | Importance | Mandatory | Min years | Notes |
|---|---|---|---|---|---|
| React | Skill | Mandatory | yes | 3 | Production React experience |
| TypeScript | Skill | Important | yes | 2 | |
| AWS | Cloud | Preferred | no | — | |
| AWS Certified Developer | Certification | Preferred | no | — | |
| BFSI | Domain | Important | no | — | |

Categories: Skill · Certification · Domain · Education · Experience · Custom note
(free text, shown in reports, never scored).

### 9.4 Resolving defaults at confirm time

When a JD config is confirmed, every requirement is materialised with concrete
values before it can reach the scorer:

- `required_depth` — from §8.7 wording, else the seniority default.
- `required_years` — from "N+ yrs", else the seniority default.
- `importance` — defaults to Preferred when nothing indicates otherwise.

`app/scoring/` therefore never receives `None` for these, which keeps its
functions total and trivially testable. v2.0 allowed `None` in the model and
divided by it in the formula.

## 10. Skill proof engine

### 10.1 Skill mapping

| Match type | Example | Factor |
|---|---|---|
| Exact, including synonyms | ReactJS = React.js = React · ADF = Azure Data Factory | 1.0 |
| Equivalent | Azure Data Factory ≈ AWS Glue | 0.8 |
| Related / close tech | Angular ~ React · Synapse ~ Snowflake | 0.5 |
| Unknown pair | Embedding pre-check → Equivalence Judge (LLM) → cached | — |

The best mapping wins: a direct React card beats an Angular card.

**Equivalence review.** LLM-judged pairs land in `skill_equivalence` with
`source: llm` and are queued for review on the Settings screen. A reviewer can
confirm, edit the relation, or reject. Rejected pairs are remembered so the
judge is not asked again. The cache is invalidated by `prompt_version`.

> **Why this exists.** v2.0 cached judged pairs "forever" with no review path, so
> a single bad call — Java ≈ JavaScript — would silently distort every future run
> with no way to notice or undo it.

### 10.2 Skill fit formula

```python
depth_part      = min(1, shown_depth / required_depth)
years_part      = min(1, hands_on_years / required_years)
projects_part   = 1.0 if distinct_projects >= 2 else 0.5 if distinct_projects == 1 else 0.0
recency_part    = see 10.3
production_part = 1.0 if production evidence else 0.5
ownership_part  = 1.0 if self / direct verbs else 0.5

WEIGHTS = {depth: 0.25, years: 0.20, projects: 0.20,
           recency: 0.15, production: 0.10, ownership: 0.10}

# unknown parts are dropped and the remainder renormalised (see below)
base = sum(WEIGHTS[p] * part[p] for p in known) / sum(WEIGHTS[p] for p in known)

# the listed-only cap applies BEFORE the match factor
if evidence_is_skills_list_only:
    base = min(base, listed_only_cap)        # default 0.10

skill_fit = base * match_factor              # 1.0 exact | 0.8 equivalent | 0.5 related
```

**Order of operations (fix).** v2.0 stated the cap after the formula while its
own worked example required the opposite: a Java developer with Angular listed
once scores "~5%", which is `0.10 × 0.5`, not `min(0.5 × base, 0.10)`. Capping
first, then applying the match factor, is now normative — it reproduces the
example and means related-tech credit can never exceed a direct claim.

**Unknown parts (fix).** When a part cannot be computed — no dates, so
`hands_on_years` is unknown; no `last_used`, so recency is unknown — the part is
**removed** from the formula and the remaining weights are renormalised, so the
candidate is judged on what is actually known. The uncertainty is reflected once,
in Analysis Confidence (§12.2), which already deducts 25 points for missing
dates. v2.0 left this undefined; scoring the part as zero would have penalised
the same gap twice.

Part weights are editable under Advanced settings.

### 10.3 Recency

| Case | Primary skill | Core / Secondary |
|---|---|---|
| Current or latest project | 1.0 | 1.0 |
| Ended ≤ 3 years ago | 0.7 | 0.7 |
| Older | 0.4 | 0.7 floor, unless the JD asks for recent or current use |
| Skills list only | 0 | 0 |

### 10.4 Golden test — SQL

JD: "Strong SQL, performance tuning, 3+ yrs" → required L4, 3 years.

| Candidate | Evidence | Skill fit |
|---|---|---|
| A | Tuning in 3 projects, 3.5 yrs, current, production, self | 100% |
| B | Data-check queries (L2), 1 project, 1 yr, ended 2 yrs ago, production unknown | 54.7% |
| C | Skills list only | 10% |

### 10.5 Golden test — React JD

| Profile | Keyword count | Primary (React) fit | Verdict |
|---|---|---|---|
| Java dev — Python, SQL, Scala listed, Angular listed once, no React | 83% | ~5% (listed-only cap 0.10 × related 0.5) | Not a Fit |
| React dev — L4, 3 projects, 3.5 yrs, current, production | 17% | 97.5% | Deployable Now (86.4%, §13.5) |
| Angular dev — L4, 4 yrs, 3 projects, current, production | 17% | 50% (related tech × 0.5) | Trainable |

Keyword counting ranks the Java developer first. The proof engine ranks them last.

## 11. Scoring matrix

The scoring engine contains no hard-coded final weights.
`final = Σ dimension_score × weight` over enabled dimensions.

### 11.1 Dimension catalog

| Dimension | How it is scored (0–100) |
|---|---|
| Primary skill | Importance-weighted mean of primary skill fits; each primary also shown separately (§11.4) |
| Core skills | Importance-weighted mean of the **top 5** core requirements (§11.4) |
| Secondary skills | Importance-weighted mean of the **top 5** secondary requirements (§11.4) |
| Project experience | Per project: relevance to JD responsibilities (embedding similarity, or a lexical fallback — see below) 40 · uses primary/core 25 · complexity (max depth) 10 · ownership 10 · production 10 · duration 5. Latest ×1.0, older ×0.8; mean of the top 2 projects |
| Relevant experience | `min(1, years in the JD's role family ÷ JD min years)`. Above max + 3 years → "possibly overqualified" flag, no penalty |
| Certification | `(required held × 1 + preferred held × 0.5) ÷ (required + 0.5 × preferred)`; expired counts half |
| Education | Required degree met 1 · related 0.5 · none 0 |
| Role and seniority fit | `0.6 × role-family match (same 1 · adjacent 0.5 · different 0) + 0.4 × seniority band fit` |
| Domain fit | JD domain present in their projects 1 · adjacent domain 0.5 · none 0 |

Recency, ownership, production and depth live *inside* skill proof, never as
separate top-level dimensions — otherwise they would be counted twice.
**Location is a filter, never a score.**

> **Relevance without embeddings.** `sentence-transformers` is an optional
> extra (§6) and may not be configured. When no embedding similarity is
> supplied, `project_experience_score` falls back to
> `default_project_relevance` — a lexical comparison of the project's tagged
> skills and text against the JD's required skills and responsibility bullets
> (`app/scoring/dimensions.py`). This replaced an earlier implementation that
> defaulted every project to a constant 0.5, which gave this 40-point part
> zero ability to distinguish a relevant project from an irrelevant one. The
> fallback is deliberately cruder than a real embedding; wire `app/retrieval`
> and pass a populated `relevance` dict to use it instead.

### 11.2 Weights derived from the JD (D8)

The JD already tells the system what it cares about: §8 computes focus scores,
importance, certifications, domain, seniority and stated years. The matrix is
derived from that, shown to the user with a reason per line, and edited freely.

Derivation is **pure Python over the confirmed JD config** — no LLM — so it is
deterministic, unit-testable and reproducible from the audit record.

#### Points

| Dimension | Points |
|---|---|
| Primary skill | 40, +10 if any primary is Mandatory, +5 if the primary's focus score is ≥ 2× the top score of the next *different* family |
| Core skills | 15, +2 per Mandatory core requirement, max +10 |
| Secondary skills | 5 if the JD has at least one secondary requirement, else 0 |
| Project experience | 10, +5 if ≥ 4 responsibility bullets describe delivery work |
| Relevant experience | 8 if the JD states years of experience, else 0 |
| Certification | 20 if any certification is required · 8 if any is preferred · else 0 |
| Education | 5 if the JD states education requirements, else 0 |
| Role and seniority | 5 |
| Domain fit | 12 if domain experience is required · 5 if a domain is mentioned · else 0 |

#### Normalisation

`weight_i = points_i / Σ points × 100`, converted to integers by the
**largest-remainder method**, with ties broken by the canonical dimension order
above. The result totals exactly 100 by construction.

Then the floor from D9: if Primary lands below **35**, raise it to 35 and
re-normalise the rest proportionally. If Primary is below **40**, show §11.3's
warning.

#### Worked example — the §9.1 React JD

React is primary and Mandatory, and no other family scores above zero.
TypeScript is a Mandatory core skill. There are 4 responsibility bullets, a
stated 4–7 years, a preferred AWS certification, no education requirement, and
BFSI is mentioned but not required.

```
Primary       40 + 10 (mandatory) + 5 (dominates)  = 55
Core          15 + 2  (TypeScript mandatory)       = 17
Secondary     5   (Angular, Python, Java, Scala, SQL present)
Project exp   10 + 5  (4 delivery bullets)         = 15
Relevant exp  8   (4–7 yrs stated)
Certification 8   (AWS Certified Developer, preferred)
Education     0   (none stated)
Role/senior   5
Domain        5   (BFSI mentioned, not required)
                                             total = 118
```

Normalised, with largest-remainder rounding:

| Dimension | Weight | Why (shown in the UI) |
|---|---|---|
| Primary skill | **47%** | React in title, 4 responsibilities, "4+ years", mandatory |
| Core skills | **14%** | 1 mandatory core skill (TypeScript) |
| Project experience | **13%** | 4 delivery-focused responsibilities |
| Relevant experience | **7%** | JD states 4–7 years |
| Certification | **7%** | AWS Certified Developer listed as preferred |
| Secondary skills | **4%** | 5 secondary skills present |
| Role and seniority | **4%** | Senior, frontend_dev |
| Domain fit | **4%** | BFSI mentioned |
| Education | **0%** | No education requirement in the JD |
| **Total** | **100%** | |

Primary at 47% clears the 35% floor and the 40% warning threshold.

#### What this replaces

v2.0 offered five fixed presets, none of which summed to the 100% that §11.3
required — 90, 90, 95, 95 and 80 — because the preset table omitted the *Role and
seniority* and *Domain fit* columns, and "Domain-critical" carried no domain
weight at all. Deriving and normalising removes that whole class of bug. A unit
test asserts every shipped and derived matrix totals exactly 100.

Presets remain as **starting points** and as saved user matrices
(`weight_presets.yaml`), selectable at any time to replace the derived matrix.

### 11.3 Rules

- Live total. **Run** is disabled until the total is exactly 100% —
  "Weights must total 100%. Current total: 95%." **Normalize** rescales
  automatically. The derived matrix always starts valid.
- Warning if Primary is under 20%: "Results will drift toward keyword matching."
  Under D9 the deriver also warns below 40% and floors at 35%.
- **N/A dimensions** — enabled but with no JD data are skipped and their weight
  spread proportionally, noted in the UI and Excel. This now rarely fires,
  because the deriver already assigns 0 to dimensions the JD is silent about.
- Every run stores its weights and their hash, so the result is reproducible.

### 11.4 How many skills a tier scores (D10)

Core and Secondary score the **top 5 requirements** in their tier, not every
skill the JD lists.

- Selection is **per JD**, computed once when the config is confirmed and stored
  in `jd_config`. It is never per candidate — otherwise candidates face different
  tests and the comparison table becomes meaningless.
- All **Mandatory** requirements in the tier are included regardless of the cap;
  remaining slots fill by focus score, ties broken alphabetically. If more than
  five are mandatory, all are kept — and §8.9's "everything mandatory" conflict
  will already have asked the user to trim.
- Requirements beyond the cap still appear in the evidence table, in gaps and in
  the Excel report, marked **not scored**.
- The **Primary** dimension is never capped, and each primary is displayed
  separately so a mean cannot hide a zero behind a strong sibling.
- Cap is configurable as `tier_skill_cap`, default 5.

> **The defect this fixes.** Averaging over every listed skill let zeros from
> unmentioned skills drag the mean down, so the score moved with JD verbosity.
> From §13.5's own numbers, Secondary = `(80.5 + 10 + 0 + 0 + 0) / 5 = 18.1%`;
> with only SQL and Python listed, the identical candidate scores 45.3% and their
> total rises from 86.4% to 89.1%. Ranking within one JD was unaffected, but the
> absolute thresholds — 80% for Deployable Now, 60% for the gate — silently
> changed meaning between JDs. The main-skill gate was never affected: it reads a
> single skill's fit, with no averaging.

### 11.5 Advanced settings

| Setting | Default |
|---|---|
| Skill proof parts — depth / years / projects / recency / production / ownership | 25 / 20 / 20 / 15 / 10 / 10 |
| Main-skill gate on/off · threshold | On · 60% |
| Dual-primary mode (§12.1) | `all` — must prove both |
| Trainable threshold (primary or close tech) | 25% |
| Deployable-now threshold | 80% |
| Listed-only cap | 10% |
| Match factors — exact / equivalent / related | 1.0 / 0.8 / 0.5 |
| Importance multipliers — mandatory / important / preferred / optional | 3 / 2 / 1 / 0.5 |
| Borderline band → human review | ± 3 points |
| Tier skill cap (§11.4) | 5 |
| Primary weight floor / warning (§11.2) | 35% / 40% |
| Allow certification to offset a missing primary | Off |

## 12. Gate, verdicts, confidence and review

### 12.1 Gate logic

```python
passed = [p for p in primaries if fit(p) >= gate_threshold]

if dual_primary_mode == "all":
    gate_ok = len(passed) == len(primaries)
else:                      # "any"
    gate_ok = len(passed) >= 1

if gate_ok:
    verdict = "deployable_now" if (all_mandatory_met and match_score >= 80) \
              else "needs_ramp_up"
else:
    verdict = "trainable" if max_primary_or_close_tech_fit >= 25 else "not_a_fit"

# a human-review flag is added on top of any verdict when §12.3 triggers
```

**Mandatory met** = skill fit ≥ gate threshold, required certification held, and
any **user-set minimum years** met. Secondary skills and certifications cannot
lift anyone past a failed gate.

> **Which "years" gates (corrected).** Only a floor the user sets explicitly in
> My Requirements (§9.3) gates the verdict. The JD's *inferred* `required_years`
> does not: it is already inside `years_part` of the fit score, so checking it
> again both double-counts the same gap and fails a 97.5% candidate over half a
> year. v2.0 conflated the two, which made its own §13.5 example impossible —
> C-014 is shown as Deployable Now with 3.5 years against a 4-year requirement.

> **Dual primary and the mandatory check.** When `dual_primary_mode` is `any`,
> a primary the gate let through must also be excused from the mandatory check.
> Otherwise the mode is inert: the gate passes on one primary and the other
> immediately blocks the verdict, so no candidate could reach Deployable Now on
> an either/or JD.

**Dual primary (D5).** `dual_primary_mode` lives on the JD config and is
surfaced on the JD Review screen whenever a second primary is detected:
*"This JD has two primary skills. Must a candidate prove both, or is either
acceptable?"* It defaults to `all`, so the strict reading applies unless someone
deliberately relaxes it. When the mode is `all` and a primary fails, that primary
is forced to the top of "why not higher", so the score and the verdict never tell
different stories.

v2.0 said both primaries "face the gate" without saying whether both had to pass
— the difference between `Not a Fit` and `Deployable Now` for a strong-React,
no-Node candidate on a full-stack JD.

### 12.2 Two separate numbers

|  | Meaning |
|---|---|
| **Match Score** (0–100%) | How well the proven profile fits the configured JD |
| **Analysis Confidence** (0–100%) | How sure the system is about that reading |

Candidate confidence, in code: start at 100 · −25 no dates · −15 per
claim-vs-evidence gap, max −30 · −15 primary proven by a single line · −10
primary only implied · −10 parse issues · −10 padding.
High ≥ 80 · Medium 60–79 · Low < 60.

Two candidates can both score 86% — one at 94% confidence, one at 51%. The
second goes to human review.

### 12.3 Human review triggers

- JD confidence Low, or unresolved JD conflicts.
- Candidate confidence below 60%.
- Claim-vs-evidence gap, overlapping jobs, or undated history.
- Unusual career transition — lane changed in the last two projects.
- Borderline — within ±3 points of the gate (60%) or the deployable threshold (80%).
- Parsing problems — missing sections, scanned pages.

The queue shows the reason for each item. The manager can **Confirm**,
**Change verdict** (with a note), or **Dismiss** — all logged for audit and fed
into the eval set.

### 12.4 Stage 1 filtering is visible

The cheap pre-filter (primary skill plus close family) is deliberately
recall-oriented: it is meant to skip obvious non-starters, not to make decisions.
Every run reports how many profiles it excluded, and the excluded list is
inspectable with the reason. v2.0 left this silent, so a candidate whose React
evidence was implied through Next.js could disappear with no trace.

### 12.5 Naming

Show **Match Score + Verdict** — "84% Match · Deployable Now" — never "Rank #1".
Sorting by score is fine; ranks are not implied decisions.

## 13. Explanations

### 13.1 Every dimension block shows

Score · Weight · Contribution · Evidence · Gaps · Confidence.

### 13.2 How explanations are built

1. Code builds a **facts JSON** per candidate — every number, level, quote, gap
   and flag.
2. All sections below are **templates filled from facts**, so they are consistent
   and exact.
3. Only the 2–3 line summary is written by the Reason Writer Agent, from the
   facts JSON alone.
4. **Validation.** Any skill or number not present in the facts → regenerate
   once → otherwise fall back to a template summary. The validator also runs a
   **forbidden-phrase lint** — "definitely", "will succeed", "best candidate",
   "better than", "guaranteed" — enforcing §2.8, which v2.0 stated as a rule but
   never checked.
5. **Wording.** Evidence found · No evidence found · Partial evidence · Requires
   verification.

### 13.3 Why not higher

Lost points per dimension = `weight × (1 − score)`, sorted largest first, each
with its evidence gap.

### 13.4 What would make this candidate deployable

Lists the missing evidence, closest gaps first, plus the points needed to reach
the gate and 80%. **No training-time predictions** — the system states what
evidence is missing, never how long learning would take.

### 13.5 Example — Deployable Now

C-014, scored with the matrix derived in §11.2.

```
C-014 · 83.4% Match · DEPLOYABLE NOW · Analysis confidence 92% (High)
JD primary: React   ·   Candidate primary: React   ·   Lane: Same

Summary: Evidence found of advanced React work in 3 projects including the
current one, with production impact. TypeScript evidence is strong. Redux
evidence is partial.

Dimension              Weight   Score    Contribution
Primary — React          47%    97.5%       45.83
Core skills              14%    84.9%       11.89
Project experience       13%    85.0%       11.05
Relevant experience       7%    87.5%        6.13
Certification             7%     0.0%        0.00
Secondary                 4%    18.1%        0.72
Role & seniority          4%    95.0%        3.80
Domain (BFSI)             4%   100.0%        4.00
Education                 0%      n/a           —
Total                                        83.41
```

Skill evidence:

```
React       Primary  needs L4·4y  found L4·3.5y  3 projects  current    97.5%
  "Built a component library used by 4 apps"
  "Cut page load 40% with memoization and code-splitting"
TypeScript  Core     needs L3·2y  found L3·2.5y  2 projects  current   100.0%
  "Migrated 120 components from JavaScript to TypeScript"
Redux       Core     needs L3·2y  found L2·1y    1 project   2 yrs ago  62.2%
  "Used Redux for cart state"
SQL         Second.  needs L2·1y  found L2·1y    1 project   2 yrs ago  80.5%
```

Why not higher, points lost:

```
↓ Certification 7.0 — AWS Certified Developer: no evidence found
↓ Secondary     3.3 — Angular, Java, Scala: no evidence found; Python: skills list only
↓ Core          2.1 — Redux: partial evidence (L2 vs L3, 1 yr vs 2)
↓ Project exp   2.0 — 2 of 3 projects only partly relevant to the JD responsibilities
↓ Primary       1.2 — React 3.5 yrs vs 4 required
↓ Relevant exp  0.9 — 4.5 yrs in frontend_dev vs 4 required, below the top of the band
↓ Role          0.2 — senior band, slightly under the JD midpoint
```

```
Red flags & notes:       Python listed but not used in any project
Requires verification:   specifics behind "40% faster page load"
                         a Redux state design walkthrough
```

> **Two things worth noticing, and one to tune.**
>
> The same candidate scored **86.4%** under v2.0's fixed Skills-first matrix and
> **83.4%** under the derived one, because the derived matrix spends 27 points on
> project experience, years and certification that Skills-first ignored entirely.
> Both are defensible; which is *right* is exactly what D9's tuning pass settles.
>
> The top score-limiting factor is now a **preferred** certification the
> candidate does not hold, costing 7 points — more than their Redux gap and their
> React shortfall combined. That looks wrong: a nice-to-have certification should
> not be the biggest single thing standing between a strong React developer and a
> higher score. The 8-point allocation for a preferred certification in §11.2 is
> the first thing to revisit when we run the deriver across your real JDs.

### 13.6 Example — Trainable

```
C-027 · TRAINABLE · Primary (React) 50% — gate 60% not met
Candidate primary: Angular (4 yrs, L4, 3 projects, current)   ·   Lane: Adjacent

Missing evidence, closest first:
  1. Any direct React project evidence (related-tech credit is capped at 50%)
  2. Redux or other React state management
  3. React in production

Gate status: not met — direct React evidence is needed to pass.
```

## 14. What-if simulator

Two modes, both costing **zero LLM calls**, but with different compute:

| Mode | What changes | Cost |
|---|---|---|
| **Weight what-if** | Dimension weights only | Re-weighted sum over cached dimension scores — instant |
| **Parameter what-if** | Advanced settings — skill proof parts, match factors, gate and deployable thresholds, tier cap | Re-runs skill proof and dimension scoring in pure Python; can change verdicts |

v2.0 described only the first. Separating them matters because changing the gate
threshold is presented in the same panel but re-computes far more, and can flip a
verdict rather than just a number.

Split view: current matrix versus proposed, recomputed live. Per candidate:
old score → new score, rank movement, verdict changes highlighted.

**Why rankings changed** — per-dimension contribution deltas. C-014 moving from
the derived matrix to v2.0's Skills-first shape:

| Change | Effect on C-014 |
|---|---|
| Primary 47 → 55 | +7.80 |
| Core 14 → 25 | +9.34 |
| Secondary 4 → 10 | +1.09 |
| Project experience 13 → 0 | −11.05 |
| Relevant experience 7 → 0 | −6.13 |
| Certification 7 → 0 | 0.00 |
| Role & seniority 4 → 5 | +0.95 |
| Domain 4 → 5 | +1.00 |
| **Net** | **83.41% → 86.41% (+3.00)** |

**Apply** makes the proposal current; **Save as preset** stores it in
`weight_presets.yaml`.

## 15. Results, comparison, search and filters

- **Tabs** — Deployable Now · Needs Ramp-up · Trainable · Not a Fit · ⚠ Human
  Review, each with a count. Plus an **Excluded by filter** count (§12.4).
- **Comparison table** with a column chooser: Candidate · Match Score · Verdict ·
  Confidence · Candidate Primary · Primary Score · Core · Projects · Experience ·
  Certification · Domain · Main Strength · Main Gap · Flags.
- **Filters** — primary skill · primary score · match score · verdict ·
  confidence · years · certification · project experience · domain · core skill ·
  location.
- **Search box** — "React 3+ years AWS certified Deployable Now" parsed into
  filters.
- **Skill search across the pool**, no JD needed: skill + minimum depth +
  minimum years + used within N years. E.g. Kafka ≥ L3, ≥ 2 yrs, last 2 years.
- **Side-by-side compare** — pick 2–4 candidates for dimension bars and evidence
  per skill.
- **Candidate detail** — overview · lane · skill evidence (parsed and verified) ·
  project evidence · certifications · score breakdown · why / why not / path ·
  flags · review actions · **add verified evidence** (§7.7).

## 16. Excel report

XlsxWriter. File: `ProfileMatch_<JD-title>_<YYYY-MM-DD_HHMM>.xlsx`.

Export options: all candidates or the current filter · real names or candidate
IDs · include evidence quotes on or off.

| # | Sheet | Contents |
|---|---|---|
| 1 | Summary | JD title, role intent, primary skill, JD confidence, run date, matrix and weights, count per verdict, review count, top 5, bar chart of the top 10 |
| 2 | Comparison | One row per candidate — all §15 columns |
| 3 | Score Breakdown | Candidate × dimension: weight, score, contribution; N/A notes |
| 4 | Skill Matrix | Candidates × JD skills heatmap (fit %), header groups Primary / Core / Secondary, with **not scored** marks for requirements beyond the tier cap |
| 5 | Evidence | Candidate × skill: needed vs found depth and years, projects, last used, production, ownership, evidence quality, quotes, and `Parsed`/`Verified` source badges |
| 6 | Gaps & Paths | Why-not-higher factors, missing evidence, path to deployable, requires-verification items |
| 7 | Human Review | Flagged candidates, trigger, manager action and note |
| 8 | JD & Config | Final JD config with source badges, conflicts and resolutions, My Requirements, derived vs final weights with the reason per line, advanced settings |
| 9 | Audit | Run ID, JD config version, weights hash, **taxonomy version, equivalence version**, models, prompt versions, app version, timestamp |

**Formatting.** Bold frozen header row; autofilter on every table; wrapped text
for reasons; set column widths. Verdict fills — Deployable mint · Ramp-up sky ·
Trainable amber · Not a Fit soft grey · Review coral outline — each paired with a
text label and symbol, never colour alone. Match Score with data bars; dimension
columns on a 3-colour scale; `0.0%` number formats. Candidate cells in Comparison
hyperlink to their rows in Evidence. Print landscape, fit to width, repeat header
row.

**Check.** Opens cleanly in Excel and LibreOffice, and every value equals the UI,
because both read the same facts JSON.

## 17. UI screens

Streamlit multipage app (D13). One process, no build step, no HTTP layer.

### 17.1 Screens

| Page | Contents |
|---|---|
| `Home.py` | Pool summary, recent JDs, recent runs, provider and privacy-mode banner |
| `1_Profile_Pool.py` | Bulk upload, parse progress, profile list (lane, years, skills proven, flags, confidence), re-parse, evidence cards |
| `2_JD_Input.py` | Upload or paste → Analyze JD; recent JDs; similar-JD reuse with a diff |
| `3_JD_Review.py` | Intent, primary with its focus calculation, tiers and importance, conflicts, AI vs My version, Compare, My Requirements, dual-primary toggle, Confirm |
| `4_Scoring_Matrix.py` | Derived matrix with a reason per line, sliders with a live total, Normalize, presets, Advanced, What-if |
| `5_Results.py` | Verdict tabs, comparison table, filters, search, skill search, compare, Download Excel |
| `6_Candidate_Detail.py` | Full breakdown per §15, review actions, add verified evidence |
| `7_Settings.py` | Provider and model per agent, privacy mode, thresholds, taxonomy and certification YAML viewer, equivalence review queue, retention |

### 17.2 Streamlit mapping

| Need | Widget |
|---|---|
| Comparison table, sortable, column chooser | `st.dataframe` with `column_config` + `st.multiselect` |
| Verdict colouring | `pandas.Styler` background per verdict, plus a text label column |
| Weight sliders with a live total | `st.slider` per dimension in `st.columns`, total in `st.metric`, Run gated on `total == 100` |
| What-if split view | Two `st.columns`, current versus proposed, `st.metric` deltas |
| Requirement editing | `st.data_editor` over the requirements table |
| Candidate detail | `st.tabs` + `st.expander` per dimension |
| Ingestion progress | `@st.fragment(run_every=2)` polling the `jobs` table |
| Evidence quotes | `st.code` blocks so quoting stays verbatim and copyable |
| Navigation state | `st.session_state` holds `jd_id`, `jd_version`, `run_id` only — never scores |

### 17.3 Visual style

Off-white background with soft mint, amber and sky accents, via
`.streamlit/config.toml`:

```toml
[theme]
base = "light"
primaryColor = "#5BA88E"
backgroundColor = "#FBFAF7"
secondaryBackgroundColor = "#F2F0EA"
textColor = "#2F3A36"
font = "sans serif"
```

Verdict colours stay consistent between the UI and the Excel report, and are
**always paired with a text label and a symbol** — never colour alone, so the
verdict survives a colourblind reader and a greyscale print.

> **Honest limitation.** v2.0 specified a "light, airy" custom design with
> Quicksand. Streamlit theming covers base colours and a font family; anything
> beyond that needs CSS injection with limited control and no stability
> guarantee across Streamlit versions. Layout, tables, sliders and the what-if
> view map cleanly. Pixel-level design does not. That trade bought roughly a week
> of the build back (D13).

### 17.4 Running it

```bash
streamlit run app/ui/Home.py \
  --server.address=127.0.0.1 \
  --server.headless=true \
  --browser.gatherUsageStats=false
```

Bound to loopback deliberately — see §20.3.

## 18. Data models, storage and config

### 18.1 Core Pydantic models — `app/schemas/`

```python
class ProjectSkill(BaseModel):
    skill: str                       # normalized
    raw_name: str
    action: str                      # what they did
    depth: int = Field(ge=1, le=5)
    ownership: Literal["self", "team", "vague"]
    production: Literal["yes", "no", "unknown"]
    usage_context: Literal["dev", "test", "support", "analysis", "other"]
    evidence_quality: Literal["weak", "weak_plus", "medium",
                              "strong", "very_strong", "verified"]
    quote: str                       # exact resume line, verified against its block
    stack_line_only: bool = False
    implied: bool = False
    source: Literal["parsed", "manual"] = "parsed"


class Project(BaseModel):
    project_id: str
    title: str
    domain: str | None
    role: str | None
    role_family: str | None          # frontend_dev, data_engineer, tester…
    start: date | None
    end: date | None                 # None = present
    dates_approx: bool = False
    skills: list[ProjectSkill]


class EvidenceCard(BaseModel):
    skill: str
    mentions: dict[str, int]         # skills_list, summary, project_lines
    projects_used: int
    hands_on_years: float | None     # None → part dropped and renormalised (§10.2)
    claimed_years: float | None
    last_used: date | None           # None → recency part dropped
    is_current: bool
    max_depth: int
    best_evidence_quality: str
    production: bool
    ownership: Literal["self", "team", "vague"]
    evidence: list[EvidenceQuote]    # each carries source: parsed | manual


class Requirement(BaseModel):
    skill: str
    category: Literal["skill", "certification", "domain",
                      "education", "experience", "note"]
    tier: Literal["primary", "core", "secondary"] | None
    importance: Literal["mandatory", "important", "preferred", "optional"]
    required_depth: int = Field(ge=1, le=5)      # resolved at confirm time (§9.4)
    required_years: float                        # resolved at confirm time
    focus_score: float | None = None
    focus_breakdown: dict[str, float] = {}
    scored: bool = True                          # False when beyond the tier cap (§11.4)
    source: Literal["ai", "edited", "user"]
    why: str | None = None
    notes: str | None = None


class JDConfig(BaseModel):
    jd_id: str
    version: int
    job_title: str
    role_intent: str
    role_family: str
    seniority: Literal["junior", "mid", "senior", "lead"]
    domain: str | None
    experience_min: float | None
    experience_max: float | None
    requirements: list[Requirement]
    conflicts: list[Conflict]                    # with resolution status
    confidence: int                              # 0–100
    dual_primary_mode: Literal["all", "any"] = "all"      # D5
    derived_weights: dict[str, int] = {}                  # D8, before user edits
    derived_weight_reasons: dict[str, str] = {}           # shown per line in the UI


class WeightConfig(BaseModel):
    dimensions: dict[str, DimensionWeight]       # name -> {enabled, weight}
    skill_proof_parts: dict[str, float]
    gate_enabled: bool = True
    gate_threshold: float = 0.60
    trainable_threshold: float = 0.25
    deployable_threshold: float = 0.80
    listed_only_cap: float = 0.10
    borderline_band: float = 3.0
    tier_skill_cap: int = 5                      # D10
    primary_weight_floor: int = 35               # D9
    primary_weight_warn: int = 40


class MatchResult(BaseModel):
    run_id: str
    profile_id: str
    jd_id: str
    jd_version: int
    weights_hash: str
    taxonomy_version: str                        # hash of skill_families.yaml
    equivalence_version: str                     # hash of the equivalence table
    match_score: float
    dimension_scores: dict[str, float | None]    # None = N/A
    skill_fits: list[SkillFit]
    verdict: Literal["deployable_now", "needs_ramp_up", "trainable", "not_a_fit"]
    analysis_confidence: int
    review_flags: list[str]
    facts: dict                                  # grounded facts for explanations
    explanation: Explanation
```

### 18.2 Tables

| Table | Key columns |
|---|---|
| `profiles` | profile_id, file_hash, file_name, lane, total_exp, status, parsed_at, parser_model, prompt_version, retain_until, data JSON |
| `pii_map` | profile_id, name, email, phone, location — local only, never sent to an LLM |
| `projects` | project_id, profile_id, title, domain, role_family, start, end, data JSON |
| `evidence_cards` | profile_id, skill, max_depth, hands_on_years, projects_used, last_used, data JSON |
| `manual_evidence` | id, profile_id, skill, depth, years, ownership, production, note, author, created_at — **D6** |
| `certifications` | profile_id, name, issuer, year, status |
| `jds` | jd_id, title, source_type, text_hash, created_at |
| `jd_configs` | jd_id, version, ai_suggestion JSON, final JSON, derived_weights JSON, confirmed_at |
| `weight_presets` | preset_id, name, weights JSON, is_default |
| `match_runs` | run_id, jd_id, jd_version, weights JSON, weights_hash, taxonomy_version, equivalence_version, models, created_at |
| `match_results` | run_id, profile_id, match_score, verdict, confidence, flags, facts JSON, explanation JSON |
| `review_actions` | run_id, profile_id, action, new_verdict, note, reviewer, at |
| `skill_equivalence` | skill_a, skill_b, relation, factor, source (taxonomy/llm), review_status, prompt_version |
| `llm_cache` | key = hash(model + prompt_version + input), response JSON |
| `jobs` | job_id, type, status, progress, error |
| `deletions` | profile_id, deleted_at, reason, actor — audit of §20.4 purges |

Schema changes go through **Alembic** (`migrations/`), which v2.0 omitted despite
planning a SQLite → PostgreSQL move.

**Reproducibility.** `taxonomy_version` and `equivalence_version` are SHA-256
hashes of `skill_families.yaml` and of the equivalence rows. Without them,
editing a YAML file silently changed the scores of every past run with no way to
detect it.

### 18.3 Config files

```yaml
# app/data/skill_families.yaml
skills:
  React:        {group: frontend, synonyms: [ReactJS, React.js]}
  Next.js:      {group: frontend, synonyms: [NextJS]}
  TypeScript:   {group: frontend, synonyms: [TS]}
  Redux:        {group: frontend, synonyms: [Redux Toolkit, RTK]}
  Angular:      {group: frontend, synonyms: [AngularJS, Angular 2+]}
  Java:         {group: backend_java}
  Spring Boot:  {group: backend_java, synonyms: [Spring]}
  SQL:          {group: data, synonyms: [T-SQL, PL/SQL],
                 implied_by: [stored procedure, CTE, window function]}
  Azure Data Factory: {group: data_engineering, synonyms: [ADF]}
  AWS Glue:     {group: data_engineering}

relations:                                      # close tech → partial credit
  - [React, Angular, related]                   # 0.5
  - [React, Vue, related]
  - [Azure Data Factory, AWS Glue, equivalent]  # 0.8
  - [Azure Synapse, Snowflake, related]
```

Also `certifications.yaml` (aliases, issuers, equivalents), `weight_presets.yaml`
(starting points, §11.2) and `settings.yaml` (§19).

## 19. LLM layer

### 19.1 Provider interface

```
AIProvider   — extract(schema, prompt) -> validated Pydantic object
 ├── LiteLLMProvider → Gemini · Groq · NVIDIA NIM · OpenAI
 └── MockProvider    → fixtures for tests and offline development
```

Temperature 0 · Pydantic-validated JSON via Instructor · 3 retries with backoff ·
per-provider rate limiter · cache keyed on `(model, prompt_version, input hash)` ·
**allowlist check before every call** (§20.1).

Every stored LLM output carries its `model` and `prompt_version`, so a prompt
change re-runs only what it affects.

> **Determinism, stated honestly.** `temperature: 0` is not a guarantee of
> identical output across provider-side model updates. What §2.3 actually
> promises is that *scoring* is deterministic given a parse — every number in
> `app/scoring/` is pure Python over stored evidence. Re-parsing with a different
> model or prompt version can change the evidence, which is why both are recorded
> per profile and a re-parse produces a diff report rather than a silent update.

### 19.2 Agents

| Agent | Input | Output | Calls |
|---|---|---|---|
| Profile Parser | One masked project block | `list[ProjectSkill]` + project meta | Per project, once |
| JD Analyzer | JD text | Intent + skill signals + certs/domain/seniority/years | Once per JD |
| Equivalence Judge | Skill pair + short definitions | exact / equivalent / related / none + reason | Rare, cached, reviewable |
| Reason Writer | Facts JSON only | 2–3 line factual summary | Per candidate displayed |

**Prompt rules.** Rubric — depth ladder, evidence quality, ownership — plus 2–3
few-shot examples · quote the exact line · return null if not stated · Reason
Writer uses only the supplied facts.

### 19.3 Model plan

No local models (D11). All four providers reach LiteLLM through the same
interface, so switching is a `settings.yaml` edit.

```yaml
# app/settings.yaml
privacy:
  mode: dummy_data_only          # dummy_data_only | approved_cloud
  mask_pii: true
  approved_providers: []         # populated once the company approves (D3/D12)

llm:
  profile_parser:    groq/llama-3.3-70b-versatile
  jd_analyzer:       gemini/gemini-2.5-flash
  equivalence_judge: gemini/gemini-2.5-flash
  reason_writer:     groq/llama-3.3-70b-versatile
  fallbacks:
    - nvidia_nim/meta/llama-3.3-70b-instruct
    - openai/gpt-4o-mini

embeddings:
  provider: local                # local | gemini | openai
  model: BAAI/bge-small-en-v1.5
```

| Provider | Good for | Watch out for |
|---|---|---|
| **Groq** | Fastest structured extraction; strong free tier | Low free-tier rate limits — the rate limiter and backoff matter |
| **Gemini** | Large context, cheap Flash tier, good JSON adherence | **Free tier may use prompts to improve models** — dummy data only |
| **NVIDIA NIM** | Open-weight models behind an OpenAI-compatible API | Availability and model naming vary; keep it as a fallback |
| **OpenAI** | Best structured-output reliability; API traffic not used for training by default | Cost per token is the highest of the four |

**Throughput.** Cloud plus parallel requests turns v2.0's "overnight for 100
resumes" into minutes. Parallelism is capped per provider by the rate limiter.

**Cost.** A full ingest of 100 resumes is roughly 400 structured calls — about
1.2M input and 200k output tokens. Cents on Gemini Flash or GPT-4o-mini; free on
Groq within its limits. Per-run budget is shown in Settings.

**What was lost by dropping local.** v2.0 could process real resumes with nothing
leaving the machine. That guarantee is gone, and §20 is rebuilt around that fact.

## 20. Privacy, security and fairness

> **This section was rebuilt in v3.0.** v2.0's design was *local-first*:
> `privacy.mode: local_only`, real resumes never leaving the machine, cloud
> providers blocked for real data. With no local model (D11) that guarantee is
> not available. Every resume's project text now goes to a third party, so the
> controls move from "don't send it" to "control what is sent, and to whom".

### 20.1 Provider allowlist — enforced in code

| Mode | Providers permitted | Use for |
|---|---|---|
| `dummy_data_only` | Any configured provider, free tiers included | Synthetic fixtures — the entire build phase (D2) |
| `approved_cloud` | Only providers listed in `privacy.approved_providers` | Real employee profiles |

The check runs at the provider boundary, before the request is built. A blocked
provider **raises**; it is not a warning, and there is no override flag in the
UI. Switching a profile's source from fixture to real data therefore cannot
silently widen where its text goes.

**Free tiers are not equivalent to paid tiers here.** Gemini's free tier may use
submitted prompts to improve Google's models; Groq's free tier carries its own
terms. Paid OpenAI and paid Gemini API traffic is not used for training by
default. `approved_providers` must be populated from what your company actually
approves — this is part of the D3 conversation and must not be guessed at.

### 20.2 PII masking is now the primary control

Masked before any LLM call: name, email, phone, address, DOB, gender, marital
status, photo, nationality. Real values live in `pii_map`, which never leaves the
machine. The UI un-masks for display. College names are stripped from LLM input.

Because masking is no longer backed by a local-only guarantee, **masking recall
is a required test** (§23.1), not an aspiration:

- A fixture set with names representative of your actual bench — `en_core_web_sm`
  NER is notably weak on Indian names, and it was carrying the whole guarantee.
- Deterministic masking of the contact block and a name gazetteer **in addition
  to** NER, not NER alone.
- The test asserts a recall floor and fails the build below it.
- Raw resume text is never logged, at any log level.

### 20.3 Local surface

- Files, database, vectors and reports live under `storage/`, which is
  git-ignored.
- Streamlit binds to `127.0.0.1` and runs headless (§17.4). It must not be bound
  to `0.0.0.0`: there is no authentication in v1, and the app reads employee PII.
- API keys come from `.env`, never from the repo.

### 20.4 Retention and deletion

v2.0 had no retention policy and no way to delete a candidate — an omission for a
tool holding employee data.

- `retention_months` in `settings.yaml`, default 12. Profiles past it are listed
  for review on the Settings page.
- **Delete candidate** purges the source file, `profiles`, `projects`,
  `evidence_cards`, `manual_evidence`, `certifications`, `pii_map` rows and the
  Chroma vectors, and writes a row to `deletions`.
- Past `match_results` keep the candidate ID for audit integrity but no longer
  resolve to a person.
- Deletion is logged, and the log is exportable.

### 20.5 Fairness

- Name, gender, age, photo, marital status, nationality, religion and caste never
  reach the LLM or the scorer.
- No protected attribute is a scoring input, directly or as a proxy.
- **The known confound is writing style, not demography** (§7.2). Depth caps key
  on phrasing and `ownership_part` keys on direct verbs, so roughly 35% of skill
  fit moves with how a resume is written — which correlates with English fluency
  and writing culture rather than competence. §23.3's style-invariance test bounds
  it, and §7.7's verified-evidence path lets a manager correct it case by case.
- **Measured, not asserted.** §23.4 reports outcome disparities on the eval set
  in `eval/results.md`. v2.0 claimed fairness without ever checking the output.

### 20.6 Audit

Every result stores its JD config version, weights, taxonomy and equivalence
versions, models, prompt versions and review actions. Excel export supports
candidate IDs instead of names for sharing outside the team.

## 21. Project structure

```
Project1/
├── project.md                  # this file — source of truth
├── decisions.md                # why the spec says what it says
├── CLAUDE.md                   # rules for Claude Code sessions
├── README.md
├── .env.example
├── .gitignore                  # storage/, .env, *.sqlite
├── pyproject.toml
├── .streamlit/config.toml
│
├── app/
│   ├── settings.yaml
│   ├── config.py
│   ├── cli.py                  # bulk ingest, re-parse, eval runs
│   │
│   ├── ui/                     # Streamlit — the ONLY place Streamlit is imported
│   │   ├── Home.py
│   │   ├── pages/
│   │   │   ├── 1_Profile_Pool.py
│   │   │   ├── 2_JD_Input.py
│   │   │   ├── 3_JD_Review.py
│   │   │   ├── 4_Scoring_Matrix.py
│   │   │   ├── 5_Results.py
│   │   │   ├── 6_Candidate_Detail.py
│   │   │   └── 7_Settings.py
│   │   └── components/         # verdict_badge, focus_calc, weight_sliders,
│   │                           # whatif_panel, comparison_table, evidence_list
│   │
│   ├── schemas/                # Pydantic models (§18.1)
│   ├── models/                 # SQLAlchemy tables (§18.2)
│   │
│   ├── services/               # UI-agnostic; no Streamlit import
│   │   ├── document_parser.py
│   │   ├── pii_masker.py
│   │   ├── sectioner.py
│   │   ├── profile_analyzer.py
│   │   ├── evidence_engine.py
│   │   ├── jd_analyzer.py
│   │   ├── skill_engine.py
│   │   ├── matching_engine.py
│   │   ├── explanation_engine.py
│   │   ├── review_service.py
│   │   ├── retention_service.py
│   │   ├── job_runner.py       # worker thread + jobs table
│   │   └── excel_report.py
│   │
│   ├── scoring/                # PURE functions — no I/O, no LLM, no Streamlit
│   │   ├── focus.py
│   │   ├── jd_confidence.py
│   │   ├── conflicts.py
│   │   ├── skill_proof.py
│   │   ├── dimensions.py
│   │   ├── weights.py          # incl. the JD weight deriver (§11.2)
│   │   ├── gate.py
│   │   ├── confidence.py
│   │   └── whatif.py
│   │
│   ├── ai/
│   │   ├── provider.py         # AIProvider, LiteLLMProvider, MockProvider, allowlist
│   │   ├── graphs/             # profile_parser.py, jd_analyzer.py (LangGraph)
│   │   └── prompts/            # versioned: profile_parser_v1.md …
│   │
│   ├── retrieval/              # embeddings.py, vector_store.py, bm25.py
│   └── data/                   # skill_families.yaml, certifications.yaml,
│                               # weight_presets.yaml
│
├── migrations/                 # Alembic
├── tests/
│   ├── scoring/                # unit + property tests
│   ├── services/
│   ├── fixtures/               # adversarial dummy resumes and JDs (§23.2)
│   └── e2e/
├── eval/
│   ├── labeled/
│   ├── run_eval.py
│   └── results.md
└── storage/                    # git-ignored: resumes/, jds/, reports/, db/, chroma/
```

Single Python package — v2.0's `frontend/` and `backend/` split is gone with the
HTTP API (D13). The seam that matters is preserved by keeping Streamlit imports
out of `services/` and `scoring/`, which §23.1 asserts as a test.

## 22. Build plan

**Pace:** 15–25 hrs/week, evenings and weekends → roughly 11 weeks to an
evaluated MVP. Streamlit gives back about a week against v2.0's React plan;
the thin slice (D7) spends part of it up front.

### 22.1 Phases

| Phase | Weeks | Deliverables | Done when |
|---|---|---|---|
| **0 · Setup + depth spike** | 0.5 | Repo, uv, provider smoke tests across all four, 10 **adversarial** dummy resumes + 5 dummy JDs, CLAUDE.md | `pytest` green; each provider returns valid JSON; **depth spike run** (§22.2) |
| **1 · Thin slice** | 2.5 | One JD end-to-end: minimal ingest → evidence cards → JD analysis → Primary/Core/Secondary scoring → Streamlit results table → Excel | A real ranked list exists for one JD, in the browser, with a downloadable report |
| **2 · Ingestion depth** | 1.5 | Full parser, PII masking, quote verification, red flags, lane, dedupe, embeddings, background jobs, verified evidence (§7.7) | 10 resumes → evidence cards hand-checked; re-upload costs 0 LLM calls; masking recall test passes |
| **3 · JD depth** | 1.0 | Intent layer, focus scorer, tiers, importance, required levels, JD confidence, conflict detector, versioned configs, **weight deriver** | Primary correct on all dummy JDs; conflicts caught on seeded cases; every derived matrix totals 100 |
| **4 · Scoring depth** | 1.5 | Skill mapper, full skill proof, all 9 dimensions, tier cap, gate + dual-primary mode, verdicts, confidence, review triggers, what-if | Golden tests §10.4, §10.5, §13.5, §14 pass; 100 profiles scored under 1 s |
| **5 · UI depth** | 1.0 | All 7 screens, filters, search, compare, candidate detail, settings | Full flow works in the browser |
| **6 · Explanations + review** | 1.0 | Facts JSON, templates, why-not-higher, path to deployable, Reason Writer + validation + lint, review queue | Every number traces to facts; no invented skills; lint catches forbidden phrasing |
| **7 · Excel** | 0.5 | 9-sheet report + export options | Opens cleanly in Excel and LibreOffice; equals the UI |
| **8 · Eval + tuning** | 1.0 | Labelled set complete, deriver tuned against real JDs (D9), prompts tuned | §23.5 targets met or gaps documented |
| **9 · Hardening** | 0.5 | Error handling, one-command start, provider swap test, retention | Fresh clone runs with one command; provider swap is a config edit only |

The eval harness is **not** confined to Phase 8 — it runs from the end of Phase 1
onward, so a prompt or taxonomy change that wrecks the rankings is caught the
week it happens rather than at the end.

### 22.2 The Phase 0 depth spike

v2.0's largest stated risk was models misjudging depth, and it was only testable
at the end. Run it first, in half a day:

1. Take 5 fixture resumes and hand-label depth L1–L5 for ~20 skills.
2. Run the Profile Parser prompt against Groq Llama 3.3 70B, Gemini Flash and
   GPT-4o-mini.
3. Report agreement with your labels per model.

Depth carries the largest weight in skill fit (0.25), so if agreement is poor the
rubric or the few-shot examples need work before anything is built on top. D11
makes a good outcome much more likely than v2.0's 8B local plan, but it is still
cheaper to find out in week 0 than in week 9.

### 22.3 Milestones

- **M1 — week 3:** thin slice running end-to-end; show one ranked list to a bench
  manager (D1).
- **M2 — week 4.5:** resumes → verified evidence cards.
- **M3 — week 5.5:** JD → confirmed, versioned config + derived matrix.
- **M4 — week 7:** full scoring, gate, verdicts, what-if.
- **M5 — week 9:** full UI with explanations and review queue.
- **M6 — week 11:** Excel report + evaluated, tuned MVP.

### 22.4 Claude Code prompts

One phase per session:

1. "Read project.md and decisions.md. Plan Phase 0 as a checklist, wait for my OK, then build it."
2. "Run the Phase 0 depth spike per §22.2 and report agreement per model."
3. "Build Phase 1, the thin slice per §22.1. Cut anything not needed for one JD end-to-end."
4. "Build Phase 2 per §7 and §18. Start with schemas and tests for date merging, quote verification and evidence quality."
5. "Build Phase 3 per §8, §9 and §11.2. Write the weight-deriver tests first, including the §11.2 worked example."
6. "Build Phase 4 per §10 to §12 and §14. Write the golden tests first, then the scoring code in app/scoring as pure functions."
7. "Build Phase 5 per §15 and §17 — Streamlit only, against the existing services."
8. "Build Phase 6 per §13, then Phase 7 per §16."
9. "Extend the eval harness per §23 and report the metrics."

Session rules live in `CLAUDE.md`.

## 23. Testing and evaluation

### 23.1 Tests

**Unit — `app/scoring/`:** golden examples · weight validation, normalisation and
N/A redistribution · the §11.2 weight-deriver worked example · tier cap selection
· gate and verdict edges, both dual-primary modes · borderline band · focus score
· JD confidence · conflicts · date-range merging · what-if deltas · unknown-part
renormalisation (§10.2) · cap-before-match-factor ordering (§10.2).

**Property tests (Hypothesis)** — `app/scoring/` is pure functions, which makes
these cheap and high-value:

- every score lands in `[0, 100]`;
- adding a project never lowers `skill_fit`;
- raising `required_years` or `required_depth` never raises `skill_fit`;
- the listed-only cap is never exceeded after the match factor is applied;
- N/A redistribution preserves a total of exactly 100;
- every derived matrix totals exactly 100, for any JD config;
- `dual_primary_mode = "all"` is never more permissive than `"any"`.

**Architecture:** no module under `services/` or `scoring/` imports Streamlit —
asserted as a test, since it is the only thing preserving the seam after D13.

**Masking recall (§20.2):** a required test with a floor, over a fixture set of
names representative of your bench. Fails the build below the floor.

**Parser snapshots:** fixtures → expected JSON, tolerant on LLM-judged fields.

**LLM contract:** MockProvider responses validate; malformed JSON exercises the
retry path; a blocked provider raises under `approved_cloud` (§20.1).

**Services:** ingestion, JD config versioning, overrides, verified evidence,
retention and deletion.

**E2E:** fixtures → run → Excel → check sheets, row counts and values against the
UI's facts JSON.

### 23.2 Fixtures must be adversarial (D2)

You write the test resumes, so they will be tidier and more uniform than real
ones. §24's risk list is the specification for the fixture set — build one
fixture per risk, deliberately:

| Fixture | Exercises |
|---|---|
| Two-column layout | PyMuPDF block ordering |
| No dates anywhere | Unknown-years renormalisation, confidence penalty, review trigger |
| Overlapping full-time jobs | Date-conflict flag |
| 18-skill list, 3 proven | Padding flag, listed-only cap |
| Same 4 bullets across 3 projects | Copy-paste dedupe |
| Skills only in "Tech stack:" lines | L2 depth cap |
| "We built / was involved in" throughout | Ownership 0.5 path, style-invariance test |
| Claims 6 yrs React, 2 yrs evidenced | Claim-vs-evidence gap |
| Near-empty scanned PDF | Scanned detection and exclusion |
| Laundry-list JD, 15 skills, 9 mandatory | Tier cap, "everything mandatory" conflict |

**Eval set size, defined once:** **10 JDs × 20 profiles.** v2.0 stated this three
different ways — G1 said 10 JDs, §23.2 said 5, Phase 2 said 5. G1's ≥ 9/10 is the
binding figure.

### 23.3 Style-invariance test

Directly targets the confound in §7.2 and §20.5, and needs no second rater:

1. Take each fixture's underlying facts.
2. Write a second copy in a different voice — team phrasing ("we migrated 120
   components"), indirect verbs ("was involved in", "assisted with"), and a
   non-native-English register.
3. Score both against the same JD.
4. **Assert the match scores land within a defined tolerance**, and that neither
   crosses a verdict boundary the other does not.

A failure here means the engine is scoring prose rather than proof. Start the
tolerance generous, measure what it actually is, then tighten it — the first run
is a measurement, not a pass/fail.

**Measured on the shipped fixtures: 8.3 points.** A matched pair with identical
facts, dates and projects, differing only in voice ("Built a component library"
versus "We built a component library"), scores 91.5% and 83.2%. Both still reach
the same verdict, so the effect is real but not currently decision-changing on
this pair. The test holds the tolerance at 12 points; tighten it as the parser
improves, and never loosen it to make a build pass.

### 23.4 Adverse-impact check

§20.5 claims no protected attribute affects scoring. This measures it rather
than asserting it: on the eval set, report score and verdict distributions across
the fixture groups that differ only in writing style and resume structure, and
log the result in `eval/results.md` each run. A widening gap is a regression.

### 23.5 Evaluation harness

- **Labelled set:** 10 JDs × 20 dummy profiles, ranked with verdicts — labelled
  by you (D1).
- **Metrics and targets:** primary-skill detection ≥ 90% · top-5 overlap ≥ 70% ·
  NDCG@10 · verdict agreement ≥ 75% · review-queue precision.
- Re-run after **every** prompt, taxonomy, deriver or default-weight change; log
  in `eval/results.md`.
- Review-queue actions and manager-added verified evidence (§7.7) feed new
  labelled cases.

> **What these numbers do and do not mean (D1).** The labels are yours, so the
> targets measure whether the engine stays consistent with your judgment — a
> regression guard, and a good one. They are not evidence that the engine agrees
> with bench managers generally. Reporting them as validation would overstate
> what was tested. The first genuinely external signal is one manager looking at
> the week-3 ranked list.

## 24. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Models misjudge depth | One project per call, rubric + few-shot, quote verification, **the Phase 0 spike**, eval set. Much reduced by D11 — 70B-class models replace an 8B local model |
| Real employee data reaching a training corpus | Provider allowlist enforced in code (§20.1); free tiers restricted to dummy data; PII masked with a tested recall floor |
| Provider outage, rate limit or model deprecation | Four providers behind one interface, ordered fallbacks, per-provider rate limiter, retries with backoff |
| Cost growth as the pool grows | Parse once, cache by input hash, zero LLM calls on weight change, per-run budget shown in Settings |
| Messy layouts — tables, two columns | PyMuPDF block order, DOCX tables, LLM sectioner fallback, parse-issue flag, adversarial fixtures |
| Scanned PDFs | Detected and flagged; OCR in v2 |
| Missing or ambiguous dates | Employment-date fallback, approximate flag, part renormalisation (§10.2), lower confidence, review queue |
| Laundry-list JDs | Intent layer, focus score, conflict detector, **tier cap (§11.4)**, mandatory confirmation on low confidence |
| Keyword stuffing | Evidence quality, listed-only cap, stack-line cap, copy-paste dedupe, padding flag |
| **Closed validation loop** — self-written fixtures, self-labelled eval, tuned by the same person | Adversarial fixtures (§23.2), style-invariance test (§23.3), property tests, and one external look at the week-3 ranked list. **The honest residual risk of this project** |
| Scoring writing quality rather than competence | §23.3 style-invariance test; verified-evidence correction path (§7.7) |
| Over-trust in a single number | Verdict + confidence + review queue + factual wording + forbidden-phrase lint |
| Silent score drift from a YAML edit | Taxonomy and equivalence versions in every run and on the Audit sheet |
| Bias | Sensitive-attribute masking, no protected attributes in scoring, measured adverse impact (§23.4), audit trail |
| Streamlit limits on design and interactivity | Accepted (D13); verdict clarity carried by labels and symbols rather than layout |

## 25. Roadmap

- **v1.1** — OCR for scanned PDFs · one-page PDF per candidate · taxonomy editor
  UI · cloud embedding option.
- **v1.2 — bench data** — availability date, location, bench aging and grade as
  filters and dimensions (D4) · assessment results as verified evidence.
- **v2** — PostgreSQL + multi-user login/SSO · SharePoint or Teams resume sync ·
  shortlist sharing with delivery managers · FastAPI layer if a second consumer
  appears (D13).
- **v2 — learning loop** — manager decisions suggest weight and threshold
  adjustments, approved by a human.
- **Model upgrades** — stronger equivalence judging and summaries; optional
  per-requirement double-check for the top 10 candidates.

## 26. Changelog

### v3.0 — this revision

**Stack**

- Streamlit replaces React + TypeScript + Vite + Tailwind + shadcn/ui (D13).
- FastAPI and the HTTP API dropped for v1; Streamlit calls services directly.
- `frontend/` + `backend/` collapsed into one `app/` package.
- Local models removed; Gemini, Groq, NVIDIA NIM and OpenAI behind the existing
  provider interface (D11). Embeddings stay local.
- Alembic added.

**Privacy**

- §20 rebuilt around a provider allowlist enforced in code, replacing
  `local_only` (D12).
- PII masking promoted to the primary control, with a required recall test.
- Retention policy and a real delete path added (§20.4).
- Streamlit pinned to loopback.

**Scoring**

- Weights derived from the JD and edited by the user, replacing five fixed
  presets — none of which totalled the required 100% (D8).
- Core and Secondary score the top 5 requirements per tier, so JD verbosity no
  longer moves absolute thresholds (D10).
- Listed-only cap applies **before** the match factor, matching §10.5's own
  worked example (was undefined).
- Unknown parts are dropped and renormalised instead of scoring zero, so a
  missing date is not penalised twice (was undefined).
- `required_depth` and `required_years` resolved at confirm time; `scoring/`
  never sees `None`.
- Dual-primary gate is an explicit per-JD toggle, defaulting to "must prove
  both" (was ambiguous) (D5).

**Evidence and review**

- Manager-added verified evidence, alongside the parse rather than overwriting it
  (D6).
- Quote verification scoped to the originating project block, with a length floor
  and `token_set_ratio`.
- Equivalence review queue; the LLM-judged cache is no longer permanent and
  unreviewable.
- Stage 1 filter exclusions always visible.

**Process and testing**

- Thin end-to-end slice at week 3; eval harness runs from Phase 1, not Phase 8
  (D7).
- Phase 0 depth spike added.
- Property tests, architecture test, masking-recall test, style-invariance test,
  adverse-impact check.
- Fixtures specified as adversarial, one per risk in §24.
- Eval set size defined once: 10 JDs × 20 profiles.
- G7 restated as a consistency guard rather than external validation (D1).

**Reproducibility and reporting**

- Taxonomy and equivalence versions stored per run and printed on the Audit
  sheet.
- Forbidden-phrase lint on Reason Writer output.
- Verdicts carry a label and symbol, never colour alone.
- Similar-JD reuse shows a diff before applying.

### v2.0 — carried forward unchanged

Main-skill-first, focus score rules, tiers, the 100% weight rule, the gate and
four verdicts, candidate lane, evidence-first explanations, the multi-stage
pipeline, factual wording, editable YAML taxonomy, evidence cards, the depth
ladder, one-project-at-a-time parsing, implied skills, hands-on years merged in
code, the listed-only cap, red flags, match factors, parse-once/score-many, the
golden tests, the JD intent layer, importance separate from tier, the conflict
detector, claim-vs-evidence, why-not-higher, path-to-deployable, the what-if
simulator, Match Score ≠ Rank, the human review queue, and Analysis Confidence
separate from Match Score.
