"""Evaluation harness — project.md section 23.5.

Run after any prompt, taxonomy, deriver or default-weight change:

    python eval/run_eval.py --mock

What these numbers mean: the labels are self-authored (decision D1), so this
measures whether the engine stays consistent with its author's judgment. It is
a regression guard, and a good one. It is not evidence that the engine agrees
with bench managers generally, and it should not be reported as validation.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.result import WeightConfig  # noqa: E402
from app.scoring.weights import weight_config_from_weights  # noqa: E402
from app.services.jd_analyzer import analyse  # noqa: E402
from app.services.matching_engine import run_match  # noqa: E402
from app.services.profile_analyzer import ingest_file  # noqa: E402
from app.services.skill_engine import EquivalenceStore  # noqa: E402

LABELS_PATH = Path(__file__).parent / "labeled" / "labels.json"
RESULTS_PATH = Path(__file__).parent / "results.md"


def ndcg_at_k(ranked_ids: list[str], relevance: dict[str, float], k: int = 10) -> float:
    def dcg(ids: list[str]) -> float:
        return sum(
            relevance.get(pid, 0.0) / math.log2(index + 2) for index, pid in enumerate(ids[:k])
        )

    ideal = sorted(relevance, key=lambda pid: -relevance[pid])
    best = dcg(ideal)
    return dcg(ranked_ids) / best if best else 0.0


def evaluate(labels: dict, use_mock: bool) -> dict:
    if use_mock:
        from tests.fixtures.mock_responses import build_mock_provider

        provider, model = build_mock_provider(), "mock/fixture"
    else:
        from app.ai.provider import LiteLLMProvider
        from app.config import load_settings

        provider, model = LiteLLMProvider(), load_settings()["llm"]["jd_analyzer"]

    primary_hits = primary_total = 0
    overlaps: list[float] = []
    ndcgs: list[float] = []
    verdict_hits = verdict_total = 0
    review_flagged = review_correct = 0

    for case in labels["cases"]:
        jd_text = Path(case["jd"]).read_text()
        result = analyse(jd_text, provider, model=model)
        config = result.config

        primary_total += 1
        found = {p.skill for p in config.primaries}
        if case["expected_primary"] in found:
            primary_hits += 1

        profiles = [
            ingest_file(Path(path), provider, model=model).profile for path in case["profiles"]
        ]
        weights = weight_config_from_weights(config.derived_weights, WeightConfig())
        run = run_match(profiles, config, weights, EquivalenceStore())

        ranked = [r.profile_id for r in run.results]
        by_name = {p.file_name: p.profile_id for p in profiles}
        expected_order = [by_name[n] for n in case["expected_order"] if n in by_name]

        top_k = min(5, len(expected_order))
        if top_k:
            overlaps.append(len(set(ranked[:top_k]) & set(expected_order[:top_k])) / top_k)
        relevance = {
            pid: float(len(expected_order) - index) for index, pid in enumerate(expected_order)
        }
        ndcgs.append(ndcg_at_k(ranked, relevance))

        expected_verdicts = {
            by_name[name]: verdict
            for name, verdict in case.get("expected_verdicts", {}).items()
            if name in by_name
        }
        for scored in run.results:
            expected = expected_verdicts.get(scored.profile_id)
            if expected is None:
                continue
            verdict_total += 1
            if scored.verdict == expected:
                verdict_hits += 1
            if scored.review_flags:
                review_flagged += 1
                if scored.verdict != expected:
                    review_correct += 1

    return {
        "primary_detection": primary_hits / primary_total if primary_total else 0.0,
        "top5_overlap": sum(overlaps) / len(overlaps) if overlaps else 0.0,
        "ndcg_at_10": sum(ndcgs) / len(ndcgs) if ndcgs else 0.0,
        "verdict_agreement": verdict_hits / verdict_total if verdict_total else 0.0,
        "review_precision": review_correct / review_flagged if review_flagged else 0.0,
        "cases": primary_total,
    }


TARGETS = {
    "primary_detection": 0.90,
    "top5_overlap": 0.70,
    "verdict_agreement": 0.75,
}


def write_results(metrics: dict, taxonomy: str) -> None:
    lines = [
        "# Evaluation results",
        "",
        "> The labelled set is self-authored (decision D1). These numbers measure",
        "> consistency with its author's judgment — a regression guard — not",
        "> agreement with bench managers generally.",
        "",
        f"Run: {datetime.now().isoformat(timespec='seconds')}  ",
        f"Taxonomy version: `{taxonomy}`  ",
        f"Cases: {metrics['cases']}",
        "",
        "| Metric | Result | Target | Status |",
        "|---|---|---|---|",
    ]
    for key, value in metrics.items():
        if key == "cases":
            continue
        target = TARGETS.get(key)
        status = "—" if target is None else ("pass" if value >= target else "BELOW TARGET")
        target_text = f"{target:.0%}" if target is not None else "—"
        lines.append(f"| {key.replace('_', ' ')} | {value:.1%} | {target_text} | {status} |")
    lines += [
        "",
        "## Adverse impact (project.md 23.4)",
        "",
        "Score spread across fixtures differing only in writing style is",
        "measured by `tests/test_style_invariance.py`; a widening gap there is",
        "a regression in fairness, not just in accuracy.",
        "",
    ]
    RESULTS_PATH.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Use fixture responses")
    args = parser.parse_args()

    if not LABELS_PATH.exists():
        print(f"No labelled set at {LABELS_PATH}")
        return 1
    labels = json.loads(LABELS_PATH.read_text())
    metrics = evaluate(labels, args.mock)

    from app.config import taxonomy_version

    write_results(metrics, taxonomy_version())
    for key, value in metrics.items():
        if key == "cases":
            continue
        target = TARGETS.get(key)
        flag = "" if target is None else ("  ok" if value >= target else "  BELOW TARGET")
        print(f"  {key:20} {value:6.1%}{flag}")
    print(f"\nWritten to {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
