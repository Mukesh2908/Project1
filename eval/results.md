# Evaluation results

> The labelled set is self-authored (decision D1). These numbers measure
> consistency with its author's judgment — a regression guard — not
> agreement with bench managers generally.

Run: 2026-09-22T16:19:47  
Taxonomy version: `9f5c4831660efcf2`  
Cases: 1

| Metric | Result | Target | Status |
|---|---|---|---|
| primary detection | 100.0% | 90% | pass |
| top5 overlap | 100.0% | 70% | pass |
| ndcg at 10 | 100.0% | — | — |
| verdict agreement | 100.0% | 75% | pass |
| review precision | 0.0% | — | — |

## Adverse impact (project.md 23.4)

Score spread across fixtures differing only in writing style is
measured by `tests/test_style_invariance.py`; a widening gap there is
a regression in fairness, not just in accuracy.
