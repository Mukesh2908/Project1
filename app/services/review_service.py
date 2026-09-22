"""Human review queue — project.md 12.3.

Every action is logged for audit and becomes a labelled example for the eval
set, which matters more than usual while the labels are self-authored (D1).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.models.store import Store
from app.schemas.result import MatchResult

ACTIONS = ("confirm", "change_verdict", "dismiss")


def record(
    store: Store,
    result: MatchResult,
    action: str,
    new_verdict: str = "",
    note: str = "",
    reviewer: str = "",
    eval_path: Path | str = "eval/labeled/review_actions.jsonl",
) -> None:
    if action not in ACTIONS:
        raise ValueError(f"Unknown review action: {action}")
    store.add_review_action(result.run_id, result.profile_id, action, new_verdict, note, reviewer)
    _append_label(result, action, new_verdict, note, reviewer, Path(eval_path))


def _append_label(
    result: MatchResult,
    action: str,
    new_verdict: str,
    note: str,
    reviewer: str,
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "run_id": result.run_id,
        "profile_id": result.profile_id,
        "jd_id": result.jd_id,
        "system_verdict": result.verdict,
        "system_score": result.match_score,
        "human_action": action,
        "human_verdict": new_verdict or result.verdict,
        "note": note,
        "reviewer": reviewer,
    }
    with path.open("a") as handle:
        handle.write(json.dumps(row) + "\n")
