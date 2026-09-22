"""What-if simulation — project.md section 14.

Two modes, both free of LLM calls but costing different amounts of compute:

* **weight what-if** re-weights cached dimension scores — instant;
* **parameter what-if** changes advanced settings, so skill proof and the
  dimensions are recomputed and a verdict can flip.

v2.0 described only the first, while presenting the gate threshold in the same
panel.
"""

from app.schemas.enums import DIMENSION_LABELS, DIMENSIONS
from app.schemas.result import MatchResult, WeightConfig
from app.scoring.dimensions import weighted_total


def reweight(result: MatchResult, weights: WeightConfig) -> tuple[float, dict[str, float]]:
    """Recompute one candidate's total under a different matrix."""
    return weighted_total(result.dimension_scores, weights)


def compare_matrices(
    results: list[MatchResult], current: WeightConfig, proposed: WeightConfig
) -> list[dict]:
    """Per-candidate before/after, ordered by the proposed ranking."""
    rows: list[dict] = []
    for result in results:
        new_score, _ = reweight(result, proposed)
        rows.append(
            {
                "profile_id": result.profile_id,
                "display_name": result.display_name,
                "old_score": result.match_score,
                "new_score": round(new_score, 2),
                "delta": round(new_score - result.match_score, 2),
                "verdict": result.verdict,
            }
        )
    old_order = {
        r["profile_id"]: i for i, r in enumerate(sorted(rows, key=lambda r: -r["old_score"]))
    }
    new_order = {
        r["profile_id"]: i for i, r in enumerate(sorted(rows, key=lambda r: -r["new_score"]))
    }
    for row in rows:
        row["rank_change"] = old_order[row["profile_id"]] - new_order[row["profile_id"]]
    rows.sort(key=lambda r: -r["new_score"])
    return rows


def contribution_deltas(
    result: MatchResult, current: WeightConfig, proposed: WeightConfig
) -> list[dict]:
    """Why one candidate's score moved — project.md 14."""
    rows: list[dict] = []
    for dimension in DIMENSIONS:
        score = result.dimension_scores.get(dimension)
        if score is None:
            continue
        before = current.weight_of(dimension)
        after = proposed.weight_of(dimension)
        if before == after:
            continue
        rows.append(
            {
                "dimension": DIMENSION_LABELS.get(dimension, dimension),
                "from": before,
                "to": after,
                "score": round(score, 1),
                "effect": round((after - before) * score / 100, 2),
            }
        )
    rows.sort(key=lambda r: -abs(r["effect"]))
    return rows
