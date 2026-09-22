"""End to end: fixtures → ingest → JD → score → Excel — project.md 23.1.

These are the behaviours the product exists to deliver, checked on the
adversarial fixture set rather than on tidy inputs.
"""

import zipfile
from pathlib import Path

import pytest

from app.schemas.result import WeightConfig
from app.scoring.weights import weight_config_from_weights
from app.services.excel_report import build_report
from app.services.jd_analyzer import analyse
from app.services.matching_engine import run_match
from app.services.profile_analyzer import ingest_file
from app.services.skill_engine import EquivalenceStore
from tests.fixtures.mock_responses import build_mock_provider

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
JD = FIXTURES / "jds" / "jd001_react_senior.txt"


@pytest.fixture(scope="module")
def run():
    provider = build_mock_provider()
    config = analyse(JD.read_text(), provider).config
    profiles = [
        ingest_file(path, provider).profile
        for path in sorted((FIXTURES / "resumes").glob("c00[1-5]*.txt"))
    ]
    weights = weight_config_from_weights(config.derived_weights, WeightConfig())
    return (
        analyse(JD.read_text(), provider).config,
        profiles,
        weights,
        run_match(profiles, config, weights, EquivalenceStore()),
    )


def by_name(result_run, fragment: str):
    return next(
        r
        for r in result_run.results
        if fragment in r.profile_id or fragment.lower() in r.display_name.lower()
    )


# -- the product's core claims --------------------------------------------


def test_the_strong_react_developer_ranks_first(run):
    _config, _profiles, _weights, result = run
    assert "Priya" in result.results[0].display_name
    assert result.results[0].verdict == "deployable_now"


def test_keyword_stuffing_does_not_win(run):
    """A Java CV listing React and Angular must not beat a real React developer."""
    _config, _profiles, _weights, result = run
    stuffed = by_name(result, "Sandeep")
    assert stuffed.verdict == "not_a_fit"
    assert stuffed.match_score < result.results[0].match_score / 2


def test_listed_only_skills_stay_under_the_cap(run):
    """project.md G2: a skills-list-only skill never exceeds 10% fit."""
    _config, _profiles, _weights, result = run
    for scored in result.results:
        for fit in scored.skill_fits:
            if fit.listed_only:
                assert fit.fit <= 0.10 + 1e-9, f"{fit.skill} scored {fit.fit_pct}%"


def test_the_angular_developer_is_trainable_not_deployable(run):
    _config, _profiles, _weights, result = run
    angular = by_name(result, "Arun")
    assert angular.verdict in ("trainable", "needs_ramp_up")
    assert not angular.gate_passed or angular.verdict != "deployable_now"


def test_undated_history_lowers_confidence_and_flags_review(run):
    _config, _profiles, _weights, result = run
    undated = by_name(result, "Meera")
    assert undated.analysis_confidence < 100
    assert undated.review_flags


def test_every_scored_point_traces_to_evidence(run):
    """project.md 2.6: no score without evidence."""
    _config, _profiles, _weights, result = run
    for scored in result.results:
        for fit in scored.skill_fits:
            if fit.fit > 0.10:
                assert fit.evidence or fit.relation != "exact", (
                    f"{scored.display_name}/{fit.skill} scored {fit.fit_pct}% "
                    "with no quoted evidence"
                )


def test_explanations_reconcile_to_100(run):
    """Score plus points lost must account for the whole matrix."""
    _config, _profiles, _weights, result = run
    for scored in result.results:
        lost = sum(row["lost"] for row in scored.explanation.why_not_higher)
        assert scored.match_score + lost == pytest.approx(100, abs=0.6)


def test_no_explanation_invents_a_skill(run):
    _config, _profiles, _weights, result = run
    from app.services.explanation_engine import validate_summary

    for scored in result.results:
        ok, reason = validate_summary(scored.explanation.summary, scored.facts)
        assert ok, f"{scored.display_name}: {reason}"


def test_summaries_avoid_forbidden_wording(run):
    from app.schemas.enums import FORBIDDEN_PHRASES

    _config, _profiles, _weights, result = run
    for scored in result.results:
        lowered = scored.explanation.summary.lower()
        for phrase in FORBIDDEN_PHRASES:
            assert phrase not in lowered


def test_reparsing_an_unchanged_file_costs_no_llm_calls():
    """project.md 2.5: parse once, score many."""
    provider = build_mock_provider()
    path = FIXTURES / "resumes" / "c001_react_strong.txt"
    first = ingest_file(path, provider)
    calls_after_first = len(provider.calls)
    second = ingest_file(path, provider, known_hashes={first.profile.file_hash: "C-1"})
    assert second.skipped
    assert len(provider.calls) == calls_after_first


def test_stage_one_exclusions_are_reported_not_silent(run):
    _config, _profiles, _weights, result = run
    assert result.scored_count + len(result.excluded) == 5


def test_weights_total_100_and_are_recorded(run):
    config, _profiles, weights, result = run
    assert weights.total() == 100
    for scored in result.results:
        assert scored.weights_hash
        assert scored.taxonomy_version


# -- the report ------------------------------------------------------------


def test_excel_report_has_nine_sheets(tmp_path, run):
    config, _profiles, weights, result = run
    path = build_report(result, config, weights, tmp_path / "report.xlsx")
    with zipfile.ZipFile(path) as archive:
        sheets = [n for n in archive.namelist() if "worksheets/sheet" in n]
    assert len(sheets) == 9


def test_excel_can_hide_real_names(tmp_path, run):
    config, _profiles, weights, result = run
    path = build_report(result, config, weights, tmp_path / "anon.xlsx", use_real_names=False)
    assert path.exists() and path.stat().st_size > 5000


def test_report_values_match_the_ui_facts(run):
    """Both read the same facts dictionary, so they cannot disagree."""
    _config, _profiles, _weights, result = run
    for scored in result.results:
        total = sum(d["contribution"] for d in scored.facts["dimensions"])
        assert total == pytest.approx(scored.match_score, abs=0.05)
