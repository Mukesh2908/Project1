"""Full-matrix stress test: every resume in the corpus against every JD.

8 JDs x 24 resumes = 192 pairings. The point is not volume for its own sake —
a single-JD fixture set cannot surface anything that depends on JD variety,
and several real defects hid there precisely because of that: multi-word skill
names breaking summary validation, overlapping taxonomy aliases inventing
requirements, and the claim-vs-evidence flag never firing on the commonest
phrasing of a claim.

Invariants are asserted over every result rather than eyeballed, so a
regression anywhere in the matrix fails the build.
"""

from pathlib import Path

import pytest

from app.ai.demo_provider import build_mock_provider
from app.schemas.enums import FORBIDDEN_PHRASES
from app.schemas.result import WeightConfig
from app.scoring.weights import weight_config_from_weights
from app.services.explanation_engine import validate_summary
from app.services.jd_analyzer import analyse
from app.services.matching_engine import run_match
from app.services.profile_analyzer import ingest_file
from app.services.skill_engine import EquivalenceStore

CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "corpus"

#: Who should top each JD. This is the product's core claim — a data engineer
#: must win the data JD, not the React one — and it is the assertion most
#: likely to catch a scoring change that quietly breaks cross-lane ranking.
EXPECTED_TOP = {
    "jd_react_senior": "Priya Raghavan",
    "jd_data_engineer": "Kavita Deshpande",
    "jd_java_backend": "Vikram Iyer",
    "jd_fullstack_dual": "Ananya Chatterjee",
    "jd_devops": "Farhan Sheikh",
    "jd_qa_automation": "Lakshmi Narayanan",
    "jd_cert_heavy": "Ramesh Gopalan",
}


@pytest.fixture(scope="module")
def corpus():
    provider = build_mock_provider()
    profiles = [
        ingest_file(path, provider).profile for path in sorted((CORPUS / "resumes").glob("*.txt"))
    ]
    runs = {}
    for jd_path in sorted((CORPUS / "jds").glob("*.txt")):
        jd = analyse(jd_path.read_text(), provider).config
        weights = weight_config_from_weights(jd.derived_weights, WeightConfig())
        runs[jd_path.stem] = (jd, weights, run_match(profiles, jd, weights, EquivalenceStore()))
    return profiles, runs


def test_corpus_is_the_expected_size(corpus):
    profiles, runs = corpus
    assert len(profiles) == 24
    assert len(runs) == 8


# -- per-JD structural invariants -------------------------------------------


def test_every_derived_matrix_totals_100(corpus):
    _profiles, runs = corpus
    for name, (jd, weights, _run) in runs.items():
        assert sum(jd.derived_weights.values()) == 100, name
        assert weights.total() == 100, name


def test_every_score_and_confidence_is_in_range(corpus):
    _profiles, runs = corpus
    for name, (_jd, _w, run) in runs.items():
        for result in run.results:
            assert 0 <= result.match_score <= 100, f"{name}/{result.display_name}"
            assert 0 <= result.analysis_confidence <= 100, f"{name}/{result.display_name}"


def test_no_candidate_is_deployable_without_passing_the_gate(corpus):
    _profiles, runs = corpus
    for name, (_jd, weights, run) in runs.items():
        for result in run.results:
            if result.verdict == "deployable_now":
                assert result.gate_passed, f"{name}/{result.display_name}"
                assert result.match_score >= weights.deployable_threshold * 100 - 1e-6


def test_a_failed_gate_only_ever_yields_trainable_or_not_a_fit(corpus):
    _profiles, runs = corpus
    for name, (_jd, _w, run) in runs.items():
        for result in run.results:
            if not result.gate_passed:
                assert result.verdict in ("trainable", "not_a_fit"), (
                    f"{name}/{result.display_name} -> {result.verdict}"
                )


def test_listed_only_skills_never_exceed_the_cap_anywhere(corpus):
    """project.md G2, checked across all 192 pairings rather than one."""
    _profiles, runs = corpus
    for name, (_jd, weights, run) in runs.items():
        for result in run.results:
            for fit in result.skill_fits:
                if fit.listed_only:
                    assert fit.fit <= weights.listed_only_cap + 1e-9, (
                        f"{name}/{result.display_name}/{fit.skill} = {fit.fit_pct}%"
                    )


def test_every_explanation_reconciles_to_100(corpus):
    _profiles, runs = corpus
    for name, (_jd, _w, run) in runs.items():
        for result in run.results:
            lost = sum(row["lost"] for row in result.explanation.why_not_higher)
            assert result.match_score + lost == pytest.approx(100, abs=1.0), (
                f"{name}/{result.display_name}"
            )


def test_dimension_contributions_sum_to_the_match_score(corpus):
    _profiles, runs = corpus
    for name, (_jd, _w, run) in runs.items():
        for result in run.results:
            total = sum(d["contribution"] for d in result.facts["dimensions"])
            assert total == pytest.approx(result.match_score, abs=0.05), (
                f"{name}/{result.display_name}"
            )


def test_no_summary_invents_a_skill_or_number(corpus):
    """Regression guard for multi-word skill names.

    "Azure Data Factory" and "Spring Boot" were rejected as hallucinated
    because the validator compared single word tokens against whole skill
    names. Every affected summary was silently discarded in favour of the
    template. A React-only corpus could never have caught this.
    """
    _profiles, runs = corpus
    for name, (_jd, _w, run) in runs.items():
        for result in run.results:
            ok, why = validate_summary(result.explanation.summary, result.facts)
            assert ok, f"{name}/{result.display_name}: {why}"


def test_no_summary_uses_forbidden_wording(corpus):
    _profiles, runs = corpus
    for name, (_jd, _w, run) in runs.items():
        for result in run.results:
            lowered = result.explanation.summary.lower()
            for phrase in FORBIDDEN_PHRASES:
                assert phrase not in lowered, f"{name}/{result.display_name}: {phrase}"


# -- cross-lane ranking, the product's core claim ---------------------------


@pytest.mark.parametrize("jd_name,expected", sorted(EXPECTED_TOP.items()))
def test_the_right_specialist_tops_each_jd(corpus, jd_name, expected):
    _profiles, runs = corpus
    _jd, _w, run = runs[jd_name]
    assert run.results, f"{jd_name} scored nobody"
    assert run.results[0].display_name == expected, (
        f"{jd_name} ranked {run.results[0].display_name} above {expected}"
    )


def test_the_keyword_stuffed_resume_never_tops_any_jd(corpus):
    """23 skills listed, 3 evidenced. It must not win anywhere."""
    _profiles, runs = corpus
    for name, (_jd, _w, run) in runs.items():
        if run.results:
            assert run.results[0].display_name != "Sandeep Kulkarni", name


def test_a_specialist_does_not_win_an_unrelated_jd(corpus):
    """The React lead must not out-rank the data engineer on the data JD."""
    _profiles, runs = corpus
    _jd, _w, data_run = runs["jd_data_engineer"]
    names = [r.display_name for r in data_run.results]
    if "Priya Raghavan" in names and "Kavita Deshpande" in names:
        assert names.index("Kavita Deshpande") < names.index("Priya Raghavan")


# -- dual primary, decision D5 ----------------------------------------------


def test_dual_primary_is_detected_on_the_fullstack_jd(corpus):
    _profiles, runs = corpus
    jd, _w, _run = runs["jd_fullstack_dual"]
    assert {r.skill for r in jd.primaries} == {"React", "Node.js"}
    assert jd.dual_primary_mode == "all"


def test_any_mode_is_strictly_more_permissive_than_all(corpus):
    """A React-only candidate clears an either/or gate but not a both gate."""
    profiles, runs = corpus
    jd, _w, _run = runs["jd_fullstack_dual"]
    passed = {}
    for mode in ("all", "any"):
        variant = jd.model_copy(deep=True)
        variant.dual_primary_mode = mode
        weights = weight_config_from_weights(variant.derived_weights, WeightConfig())
        run = run_match(profiles, variant, weights, EquivalenceStore())
        passed[mode] = {r.profile_id for r in run.results if r.gate_passed}
    assert passed["all"] <= passed["any"]
    assert passed["any"] > passed["all"], "any mode should admit at least one more"


# -- determinism ------------------------------------------------------------


def test_scoring_is_reproducible(corpus):
    """Same inputs, same outputs — the claim section 2.3 rests on."""
    profiles, runs = corpus
    for name, (jd, weights, first) in runs.items():
        second = run_match(profiles, jd, weights, EquivalenceStore())
        assert [(r.profile_id, r.match_score, r.verdict) for r in first.results] == [
            (r.profile_id, r.match_score, r.verdict) for r in second.results
        ], name


def test_jd_analysis_is_reproducible():
    provider = build_mock_provider()
    path = CORPUS / "jds" / "jd_data_engineer.txt"
    first = analyse(path.read_text(), provider).config
    second = analyse(path.read_text(), provider).config
    assert first.derived_weights == second.derived_weights
    assert [r.skill for r in first.primaries] == [r.skill for r in second.primaries]


# -- scale, project.md G3 ---------------------------------------------------


def test_rerank_of_120_profiles_is_well_under_a_second(corpus):
    import time

    from app.scoring.whatif import compare_matrices

    profiles, runs = corpus
    jd, weights, _run = runs["jd_react_senior"]
    big = []
    for index in range(5):
        for profile in profiles:
            clone = profile.model_copy(deep=True)
            clone.profile_id = f"{profile.profile_id}-{index}"
            big.append(clone)

    run = run_match(big, jd, weights, EquivalenceStore())
    start = time.perf_counter()
    compare_matrices(run.results, weights, weights)
    assert time.perf_counter() - start < 1.0
