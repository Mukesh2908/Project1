# Profile Match Engine — rules for Claude Code

## Sources of truth

- `project.md` is the specification. Build only the phase asked for; plan first,
  then code.
- `decisions.md` explains why the spec says what it says. Before changing
  anything it covers, read the entry — several decisions look arbitrary until you
  see what they fix.

## Principles

- **AI interprets, Python calculates, human decides.**
- `app/scoring/` is pure functions: no I/O, no LLM, no database, no Streamlit,
  fully unit-tested. There is a test asserting this.
- `app/services/` must not import Streamlit either. It is the only thing keeping
  the services reusable now that the HTTP API is gone.
- Streamlit belongs in `app/ui/` and nowhere else.

## LLM calls

- Every call goes through `app/ai/provider.py` — temperature 0, Pydantic schemas,
  retries, cache.
- Check the provider allowlist before the call, never after. A blocked provider
  raises; do not add an override flag.
- Mask PII before any call. Never log raw resume text, at any level.
- Store `model` and `prompt_version` with every stored output.
- Real profile data goes only to providers in `privacy.approved_providers`. Free
  tiers are for fixtures only.

## Scoring

- Never hard-code final weights. They are derived from the JD (§11.2) and edited
  by the user.
- Any matrix — derived, preset or user-edited — must total exactly 100. There is
  a property test for this; do not weaken it.
- The listed-only cap applies **before** the match factor (§10.2).
- An unknown part is dropped and the remaining weights renormalised. Never score
  an unknown as zero — the uncertainty already costs Analysis Confidence.
- `app/scoring/` never receives `None` for `required_depth` or `required_years`;
  those are resolved when the JD config is confirmed.

## Evidence

- No score without evidence. Every point traces to a verified quote or to
  manager-added verified evidence.
- A quote is verified against the project block it came from, not the whole
  document.
- Manager corrections are **added** as verified evidence. Never mutate the parsed
  record.

## Explanations

- Factual wording only: "Evidence found", "No evidence found", "Partial
  evidence", "Requires verification".
- No predictions, no comparatives, no "definitely" or "will succeed". The
  forbidden-phrase lint enforces this — do not bypass it.
- The Reason Writer sees the facts JSON and nothing else.

## Before calling anything done

- `ruff check` and `ruff format` clean.
- `pytest` green, including the property tests and the architecture test.
- If you touched scoring, prompts, the taxonomy or the deriver, run
  `eval/run_eval.py` and append to `eval/results.md`. A ranking regression is a
  failure, not a surprise.
- Test data comes from `tests/fixtures/` only. Never commit anything under
  `storage/`.

## Things that are easy to get wrong here

- The five presets in the original v2.0 spec did not total 100%. If you find
  yourself reintroducing fixed presets as the primary mechanism, re-read D8.
- Core and Secondary score the **top 5** requirements per tier, selected per JD
  and stored on the config — never per candidate.
- `dual_primary_mode` defaults to `all`. Do not quietly relax it.
- The eval set is self-labelled. Passing it means the engine is consistent, not
  that it is correct — do not describe eval results as validation.
