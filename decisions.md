# Decision record

Decisions taken after the review of `project.md` v2.0, with the reasoning behind
each one. `project.md` v3.0 is the source of truth; this file explains *why* it
says what it says, so a decision is not silently reversed later.

Status key: **Settled** — decided, reflected in the spec · **Assumed** — chosen
on your behalf, flagged for you to overturn · **Open** — still needs an answer.

---

## D1 · The evaluation set is self-labelled — **Settled**

No bench manager is available to rank profiles, so you label the eval set
yourself.

**Consequence.** G7 ("agrees with humans") is no longer external validation — it
is a self-consistency check, and the spec now says so. Tuning the engine until
it matches your own rankings proves the engine is consistent, not that it is
right. The weight moves onto the golden tests (§10.4, §10.5, §13.5), the
invariant tests (§23.1) and the style-invariance test (§23.3), all of which hold
without a second rater.

**Mitigation.** At week 3 the thin slice produces one real ranked list. Ask one
bench manager a single question — *does this order look right?* That is 30
minutes of someone else's time, not 3 hours, and it is the cheapest external
signal available.

---

## D2 · Test resumes are synthetic, written by you — **Settled**

**Consequence 1 — the fixtures must be hostile.** Resumes you write will be
tidier than real ones and written in one voice: yours. §24's risk list is
therefore the specification for the fixture set — undated projects, two-column
layouts, 15-skill padding, copy-paste bullets, "we built" phrasing, stack-line-only
skills. A clean fixture set would leave every one of those risks invisible until
real data arrives. See §23.2.

**Consequence 2 — free cloud tiers are usable throughout development.** No real
PII is in play, so Gemini and Groq free tiers are fair game for the whole build.
This is what makes D11 (no local models) viable at zero cost until real profiles
arrive.

---

## D3 · This is an internal tool your team will use — **Settled**

Not a portfolio project, not a prototype.

**Consequence.** Approval to process real employee resumes is the longest-lead
item in the plan, and after D11 it now includes *which providers* may see that
data. Start that conversation in week 0, in parallel with building — it gates
the only validation that will ever count, and no amount of engineering shortens
it. Everything built on synthetic data is scaffolding that must be re-validated
against real resumes before the tool is trusted.

---

## D4 · Availability, grade and location stay in v1.2 — **Settled**

Skill fit alone is actionable; availability is handled elsewhere. §25 is
unchanged and the results screen carries no bench-data columns in v1.

---

## D5 · Dual primary is a per-JD toggle — **Settled**

v2.0 said both primaries "face the gate" without saying whether a candidate must
pass both or either — the difference between `Not a Fit` and `Deployable Now`
for a strong-React/no-Node candidate on a full-stack JD.

**Decision.** `dual_primary_mode` on the JD config, surfaced on the JD Review
screen whenever a second primary is detected. Defaults to `all` (must prove
both), so the strict reading applies when nobody touches it.

**Knock-on.** The Primary *dimension* remains a mean across primaries, which can
hide a zero behind a strong sibling. The UI and Excel therefore show each primary
separately, and when `mode = all` a failing primary is forced to the top of
"why not higher". See §11.4 and §12.1.

---

## D6 · Manager corrections are added as evidence, never overwrites — **Settled**

v2.0 let the user override everything about a JD and nothing about a candidate —
asymmetric with "human decides", and it discarded the best source of labelled
data.

**Decision.** A manager adds a `verified` evidence entry ("interviewed them —
L4 React, led the rebuild"). It sits alongside the parsed evidence, which is
never mutated. §7.2 already reserved a `Verified` quality tier for exactly this.

**Why not a direct override.** Editing the parsed depth silently turns "proof
over keywords" into "proof, or whoever edited last", and breaks the audit trail
that §12 and the Excel report depend on. Adding evidence keeps both readings on
the record and makes every correction a labelled example for tuning.

---

## D7 · Thin vertical slice end-to-end by week 3 — **Settled**

v2.0 was backend-first with the first end-to-end run at week 8 — roughly 150
hours before anyone could look at an actual ranked list.

**Decision.** Week 3 delivers one JD → scored profiles → results table → Excel,
with Primary/Core/Secondary only and one weight matrix. Rough, but real.
Every later phase deepens something that already runs. See §22.

This matters more than usual because of D1: with a self-labelled eval set, the
sooner someone other than you sees a ranked list, the sooner you find out whether
the scores match anyone else's intuition.

---

## D8 · Weights are derived from the JD, then edited by the user — **Settled**

**Your call, and it replaces the preset menu.** §8 already computes focus scores,
importance, certifications, domain and seniority — so the system already knows
whether certifications matter for a role. Asking the user to pick
"Certification-led" from a menu was asking them to restate what the JD said.

**It also dissolves a real bug.** None of v2.0's five presets totalled the 100%
that §11.3 required — they summed to 90, 90, 95, 95 and 80, because the preset
table was missing the *Role & seniority* and *Domain fit* columns. "Domain-critical"
had no domain weight at all. The deriver normalises to exactly 100 by
construction (largest-remainder rounding), so the class of bug cannot recur.

**Bonus.** Dimensions the JD says nothing about receive 0 automatically, which
makes §11.3's "N/A redistribution" rule largely unnecessary.

Presets survive as starting points and as saved user matrices. The derivation is
pure Python over the confirmed JD config — no LLM — so it stays deterministic,
testable and traceable, per §2.3. See §11.2.

---

## D9 · Derivation policy: responsive, with a floor and a warning — **Assumed**

You asked me to choose and then show you the results on real JDs.

**Starting policy.** Let the JD lead, but never let Primary fall below **35%**,
and surface §11.3's existing warning whenever derived Primary lands under **40%**
("Results will drift toward keyword matching"). The failure mode is visible
rather than silent.

**To be tuned empirically.** During the week-3 slice we run the deriver across
your dummy JDs, look at the matrices it produces, and adjust the points table
in §11.2 against what looks right to you. Treat the numbers there as a first
draft, not settled doctrine.

---

## D10 · Core and Secondary score the top 5 requirements only — **Settled**

**The defect.** Those dimensions averaged fit across every skill the JD listed,
so zeros from unmentioned skills dragged the average down. From §13.5's own
numbers: Secondary = `(80.5 + 10 + 0 + 0 + 0) / 5 = 18.1%`. Had the JD listed
only SQL and Python, the identical candidate scores `(80.5 + 10) / 2 = 45.3%`
and their total rises from 86.4% to 89.1%. Same person, same resume, same job —
a wordier recruiter.

Ranking within one JD was unaffected (everyone shares the denominator). The
damage was to the *thresholds*: `80%` for Deployable Now and `60%` for the gate
are absolute, so on a 15-skill laundry-list JD verdicts tracked JD verbosity
rather than candidate quality.

**Decision.** Score Core and Secondary on the top 5 requirements per tier,
selected **per JD** (never per candidate — otherwise candidates face different
tests and comparison breaks). All Mandatory requirements are included
regardless of the cap; remaining slots fill by focus score. Skills beyond the
cap still appear in the evidence table and in gaps — they just cannot move the
score.

The main-skill gate was never affected: it reads a single primary skill's fit,
with no averaging.

---

## D11 · No local models — Gemini, Groq, NVIDIA NIM and OpenAI — **Settled**

Ollama and Qwen3 are removed. All four providers sit behind the existing
`AIProvider` interface (§19.1), which survives unchanged — only the model strings
differ.

**Upside.** v2.0's single largest risk was "small local models misjudge depth"
(§24), with an 8B model doing L1–L5 judgments. Llama 3.3 70B and Gemini Flash
are substantially stronger at that, and cloud latency with parallel requests
turns v2.0's "overnight for 100 resumes" into minutes. The Phase 0 depth spike
is still worth running, but it now starts from a much better place.

**Cost.** No longer zero. A full ingest of 100 resumes is roughly 400 structured
calls, ~1.2M input and ~200k output tokens — cents on Gemini Flash or GPT-4o-mini,
free on Groq's free tier within its rate limits. Budget per run is shown in
Settings.

**Embeddings remain local — Assumed.** `BAAI/bge-small-en-v1.5` via
sentence-transformers is a 130MB CPU model, not an LLM: no GPU, no ops burden,
no API cost, and project text never leaves the machine to be embedded. Cloud
embeddings are configurable if you'd rather not ship any local model at all —
say so and I'll flip the default.

---

## D12 · Privacy rebuilt around a provider allowlist — **Settled, needs your input**

**This is the significant consequence of D11.** v2.0's §20 was built on
`privacy.mode: local_only` — real resumes never leaving the machine. With no
local model, every resume's project text goes to a third party, and the free
tiers of Gemini and Groq may use submitted prompts to improve their models.

**Replacement design.**

| Mode | Providers permitted | Use for |
|---|---|---|
| `dummy_data_only` | any configured provider, free tiers included | synthetic fixtures (the whole build) |
| `approved_cloud` | only providers on the allowlist, which must carry no-training terms | real employee profiles |

Enforced in code at the provider boundary — a blocked provider raises, it is not
a warning. PII masking is promoted from defence-in-depth to the **primary**
control, which makes masking-recall a required test (§23.1), not a nice-to-have.

**Open for you (D3):** which providers your company will approve for employee
data. Paid OpenAI and paid Gemini both carry no-training terms for API traffic;
free tiers generally do not. That list belongs in the same approval conversation
as D3 and should not be guessed at.

---

## D13 · Streamlit UI, no HTTP API — **Assumed**

React + TypeScript + Vite + Tailwind + shadcn/ui is replaced by Streamlit, and
FastAPI is dropped for v1.

**Why drop the API.** For a single-user internal tool, Streamlit calling the
service layer directly removes an HTTP hop, a second process and seven route
modules. Services stay UI-agnostic — that is enforced by module boundaries, not
by HTTP — so wrapping them in FastAPI later is about a day's work if a second
consumer ever appears.

**What you give up.** §17's "light, airy, Quicksand" visual design is only
partly reachable in Streamlit; theming covers base colours and font, and the rest
needs CSS injection with limited control. Verdict colours, weight sliders with a
live total, the what-if split view and the comparison table all map cleanly.
Fine-grained layout does not.

**What you gain.** Phase 4 drops from roughly two weeks to under one, which is
most of what funds D7's thin slice.

**Background work.** Streamlit re-runs the script on every interaction, so
ingestion runs in a worker thread writing progress to the `jobs` table, with the
UI polling via `@st.fragment(run_every=2)`. A `cli.py` covers bulk operations
outside the UI entirely.

---

## Carried over from the review — fixed in v3.0 without needing a decision

| Issue | Fix |
|---|---|
| §10.2 cap vs match-factor ordering undefined; the doc's own ~5% example implied one order, the formula text the other | Cap applied **before** `match_factor`, stated explicitly in §10.2 |
| `None` years/recency double-penalised (score *and* confidence) | Unknown parts are dropped and their weight redistributed across known parts; uncertainty shows up once, in Analysis Confidence (§10.2) |
| `required_depth` / `required_years` nullable in the model but divided by in the scorer | Defaults resolved at JD-confirm time; `scoring/` never receives `None` (§9.4) |
| Editing a YAML taxonomy silently changed old scores | `taxonomy_version` and `equivalence_version` hashes stored per run and printed on the Audit sheet (§18.2) |
| LLM-judged skill equivalences cached forever with no review path | Equivalence review queue, editable, invalidated by `prompt_version` (§10.1) |
| No retention or deletion policy for employee data | Configurable retention, plus a delete action that purges files, rows, `pii_map` and vectors (§20.4) |
| No DB migration tool despite a SQLite → Postgres plan | Alembic, `migrations/` (§21) |
| Quote verification `partial_ratio ≥ 90` over the whole document false-accepts short quotes | Verify against the originating project block, minimum quote length, `token_set_ratio` on normalised text (§7.1) |
| Nothing stopped the app binding to all interfaces | Streamlit pinned to `127.0.0.1`, headless, documented (§20.3) |
| ~35% of skill fit keys on resume phrasing (depth caps by verb, `ownership_part` by direct verbs) — a writing-quality confound that also disadvantages non-native English writers | Style-invariance test asserting the same facts in two phrasings score within tolerance (§23.3) |
| Fairness asserted but never measured | Adverse-impact check reported in `eval/results.md` (§23.4) |
| Eval-set size stated three different ways (G1: 10 JDs, §23.2: 5, Phase 2: 5) | Single number, defined once (§23.2) |
| Stage 1 filter could silently drop candidates | Filter is recall-oriented; excluded count always shown and inspectable (§12.4) |
| Verdicts signalled by colour alone | Icon + text label alongside colour, in UI and Excel (§17.3) |
| Reason Writer had no check against §2.8's factual-language rule | Forbidden-phrase lint in the validator (§13.2) |
| Similar-JD reuse applied past overrides with a yes/no prompt | Shows a diff of what differs before applying (§8.1) |
