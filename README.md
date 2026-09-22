# Profile Match Engine

JD-driven, evidence-based, user-controlled profile matching for bench managers.

Give it a job description. It works out what the role actually wants, lets you
correct that reading, suggests a scoring matrix derived from the JD, and then
scores every bench profile on **proof** rather than keyword hits — with a quoted
line behind every point, and an Excel report you can hand to someone else.

> **AI interprets. Python calculates. Human decides.**

## Status

Working end to end against fixtures: ingestion, JD analysis, scoring, gate and
verdicts, explanations, the Streamlit UI, the 9-sheet Excel report and the eval
harness. Live model calls need provider keys; everything runs offline with
`--mock`.

| Document | What it is |
|---|---|
| [`project.md`](project.md) | The specification — the source of truth |
| [`decisions.md`](decisions.md) | Why the spec says what it says |
| [`CLAUDE.md`](CLAUDE.md) | Rules for Claude Code sessions |
| [`eval/results.md`](eval/results.md) | Latest evaluation run |

## Why not keyword matching

"SQL" appearing in a resume is not SQL experience. The engine asks where a skill
was used, how deeply, for how long, how recently, whether it reached production,
and whether the person did it or watched it happen.

On a React JD, a Java developer whose resume mentions Angular once scores 83% by
keyword count and about 5% here.

## Stack

Streamlit UI · Python 3.11+ · Pydantic v2 · SQLAlchemy + Alembic · SQLite →
PostgreSQL · ChromaDB · LangGraph for the two multi-step pipelines · XlsxWriter.

LLMs via LiteLLM behind one provider interface: **Gemini · Groq · NVIDIA NIM ·
OpenAI**. Embeddings run locally on CPU.

## Getting started

```bash
pip install -e ".[dev]"          # add [llm,parsing,pii,vectors] for live runs
cp .env.example .env             # keys for the providers you use
```

Try it offline, with no API keys, against the bundled fixtures:

```bash
python -m app.cli ingest tests/fixtures/resumes --mock
python -m app.cli match tests/fixtures/jds/jd001_react_senior.txt --mock --report
streamlit run app/ui/Home.py --server.address=127.0.0.1
```

The second command prints the derived weight matrix with the reason for each
line, then the ranked pool. On the bundled fixtures a keyword-stuffed Java CV
claiming "6 years of React experience" scores **14.4% · Not a Fit**, while the
developer with actual React project evidence scores **91.5% · Deployable Now**.

Run the checks the way CI would:

```bash
ruff check app tests eval && pytest -q
python eval/run_eval.py --mock
```

## Privacy

This app processes employee resumes and calls third-party model APIs, so two
rules are enforced in code rather than left to discipline:

- **PII is masked before any LLM call.** Real values stay in a local map that is
  never sent anywhere.
- **A provider allowlist gates every call.** Free model tiers may use submitted
  prompts for training, so they are restricted to synthetic fixtures. Real
  profiles go only to providers explicitly approved for employee data.

The app binds to `127.0.0.1` and has no authentication. Do not expose it on a
network interface.

`storage/` — resumes, database, vectors, reports — is git-ignored and must stay
that way.
