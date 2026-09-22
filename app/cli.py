"""Command line entry points for bulk work — project.md section 21.

Anything long-running belongs here rather than on Streamlit's render path.

    python -m app.cli ingest tests/fixtures/resumes --mock
    python -m app.cli match tests/fixtures/jds/jd001_react_senior.txt --mock
    python -m app.cli report RUN-XXXX
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.ai.provider import AIProvider, LiteLLMProvider
from app.config import STORAGE_DIR, load_settings, text_hash
from app.models.store import Store
from app.schemas.enums import DIMENSIONS, VERDICT_LABELS
from app.schemas.result import WeightConfig
from app.scoring.weights import weight_config_from_weights
from app.services.excel_report import build_report
from app.services.jd_analyzer import analyse
from app.services.matching_engine import RunResult, run_match
from app.services.profile_analyzer import ingest_file
from app.services.skill_engine import EquivalenceStore

RESUME_SUFFIXES = {".pdf", ".docx", ".txt"}


def _provider(use_mock: bool) -> tuple[AIProvider, str]:
    if use_mock:
        from app.ai.demo_provider import build_mock_provider

        return build_mock_provider(), "mock/fixture"
    return LiteLLMProvider(), ""


def cmd_ingest(args: argparse.Namespace) -> int:
    store = Store()
    provider, mock_model = _provider(args.mock)
    model = mock_model or load_settings()["llm"]["profile_parser"]

    root = Path(args.path)
    paths = (
        sorted(p for p in root.rglob("*") if p.suffix.lower() in RESUME_SUFFIXES)
        if root.is_dir()
        else [root]
    )
    if not paths:
        print(f"No resumes found under {root}")
        return 1

    known = store.known_hashes()
    parsed = skipped = 0
    for path in paths:
        result = ingest_file(
            path, provider, model=model, known_hashes=known, real_data=args.real_data
        )
        if result.skipped:
            skipped += 1
            print(f"  = {path.name} unchanged, 0 LLM calls")
            continue
        store.save_profile(
            result.profile, result.pii_map, model=model, prompt_version="profile_parser_v1"
        )
        known[result.profile.file_hash] = result.profile.profile_id
        parsed += 1
        flags = f", {len(result.profile.red_flags)} flags" if result.profile.red_flags else ""
        print(
            f"  + {path.name} -> {result.profile.profile_id} "
            f"({len(result.profile.evidence_cards)} skills, "
            f"{len(result.profile.projects)} projects{flags})"
        )
    print(f"\n{parsed} parsed, {skipped} unchanged.")
    return 0


def cmd_match(args: argparse.Namespace) -> int:
    store = Store()
    provider, mock_model = _provider(args.mock)
    model = mock_model or load_settings()["llm"]["jd_analyzer"]

    jd_text = Path(args.jd).read_text()
    result = analyse(jd_text, provider, model=model, real_data=args.real_data)
    config = result.config
    store.save_jd(config.jd_id, config.job_title, jd_text, text_hash(jd_text))
    store.save_jd_config(config, ai_suggestion=config)

    print(f"JD {config.jd_id}: {config.job_title}")
    print(f"  intent     : {config.role_intent}")
    print(f"  primary    : {', '.join(p.skill for p in config.primaries) or 'none'}")
    print(f"  confidence : {config.confidence}% ({config.confidence_band})")
    if config.conflicts:
        print(f"  conflicts  : {len(config.conflicts)}")
    print("  weights    :")
    for dimension in DIMENSIONS:
        weight = config.derived_weights.get(dimension, 0)
        if weight:
            print(
                f"      {dimension:22} {weight:3}%   {config.derived_weight_reasons.get(dimension, '')}"
            )
    print(f"      {'TOTAL':22} {sum(config.derived_weights.values()):3}%")

    profiles = store.load_profiles()
    if not profiles:
        print("\nNo profiles in the pool. Run 'ingest' first.")
        return 1

    weights = weight_config_from_weights(config.derived_weights, WeightConfig())
    run = run_match(profiles, config, weights, EquivalenceStore())
    store.save_run(run, config, weights, dict(load_settings().get("llm", {})))

    print(f"\nRun {run.run_id} — {run.scored_count} scored, {len(run.excluded)} excluded\n")
    for result_row in run.results:
        print(
            f"  {result_row.display_name:24} {result_row.match_score:6.2f}%  "
            f"{VERDICT_LABELS[result_row.verdict]:16} "
            f"confidence {result_row.analysis_confidence:3}%"
            + ("  [review]" if result_row.review_flags else "")
        )
        print(f"  {'':24} {result_row.explanation.score_reason}")
    for exclusion in run.excluded:
        print(f"  {exclusion.display_name:24} excluded — {exclusion.reason}")

    if args.report:
        path = STORAGE_DIR / "reports" / f"{run.run_id}.xlsx"
        build_report(run, config, weights, path, models=dict(load_settings().get("llm", {})))
        print(f"\nReport: {path}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    store = Store()
    results = store.load_results(args.run_id)
    if not results:
        print(f"No results for {args.run_id}")
        return 1
    config = store.load_jd_config(results[0].jd_id, results[0].jd_version)
    if config is None:
        print("JD config missing for this run.")
        return 1
    weights = weight_config_from_weights(config.derived_weights, WeightConfig())
    path = STORAGE_DIR / "reports" / f"{args.run_id}.xlsx"
    build_report(
        RunResult(run_id=args.run_id, results=results),
        config,
        weights,
        path,
        models=dict(load_settings().get("llm", {})),
    )
    print(f"Report: {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Parse resumes into the pool")
    ingest.add_argument("path")
    ingest.add_argument("--mock", action="store_true", help="Use fixture responses")
    ingest.add_argument(
        "--real-data",
        action="store_true",
        help="Assert this is real profile data (enforces the allowlist)",
    )
    ingest.set_defaults(func=cmd_ingest)

    match = sub.add_parser("match", help="Analyse a JD and score the pool")
    match.add_argument("jd")
    match.add_argument("--mock", action="store_true")
    match.add_argument("--real-data", action="store_true")
    match.add_argument("--report", action="store_true", help="Also write the Excel report")
    match.set_defaults(func=cmd_match)

    report = sub.add_parser("report", help="Rebuild the Excel report for a run")
    report.add_argument("run_id")
    report.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
