# Profile Match Engine

JD-driven, evidence-based, user-controlled profile matching for bench managers.

Give it a job description. It works out what the role actually wants, lets you
correct that reading, suggests a scoring matrix derived from the JD, and then
scores every bench profile on **proof** rather than keyword hits — with a quoted
line behind every point, and an Excel report you can hand to someone else.

> **AI interprets. Python calculates. Human decides.**

## Status

Plan and architecture. No application code yet — the build starts at §22 Phase 0.

| Document | What it is |
|---|---|
| [`project.md`](project.md) | The specification — the source of truth |
| [`decisions.md`](decisions.md) | Why the spec says what it says |
| [`CLAUDE.md`](CLAUDE.md) | Rules for Claude Code sessions |

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

Nothing to run yet. When Phase 0 lands:

```bash
uv sync
cp .env.example .env          # add keys for the providers you use
alembic upgrade head
streamlit run app/ui/Home.py --server.address=127.0.0.1
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
