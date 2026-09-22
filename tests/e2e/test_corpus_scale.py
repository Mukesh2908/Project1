"""Scale test: 20 JDs x 120 profiles = 2,400 pairings.

The hand-written corpus encodes specific risks and is worth reading. This one
exists for breadth — enough JDs that every one has a real pool to rank, and
enough profiles that ranking quality can be measured rather than eyeballed.
It found a defect the smaller corpus could not: the summary validator rejected
the engine's own text whenever a skill was matched through a related
technology.

The corpus is generated from a fixed seed, so a failure here is reproducible
from the seed rather than intermittent.
"""

import tempfile
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
from tests.fixtures.corpus_gen import build_corpus

#: Lanes whose skills legitimately transfer, so a neighbour appearing in a
#: top 10 is a correct result rather than a ranking error.
NEIGHBOURS = {
    "react": {"angular", "node"},
    "angular": {"react"},
    "node": {"react"},
    "data": {"data_aws"},
    "data_aws": {"data"},
    "devops": {"cloud"},
    "cloud": {"devops"},
    "java": set(),
    "python": set(),
    "qa": set(),
}


@pytest.fixture(scope="module")
def scaled():
    jd_texts, generated = build_corpus()
    provider = build_mock_provider()
    tmp = Path(tempfile.mkdtemp())

    profiles = []
    lane_of: dict[str, tuple[str, str]] = {}
    for index, item in enumerate(generated):
        path = tmp / f"{index:03d}.txt"
        path.write_text(item.text)
        profile = ingest_file(path, provider).profile
        profiles.append(profile)
        lane_of[profile.profile_id] = (item.lane, item.seniority)

    runs = {}
    for name, text in jd_texts.items():
        jd = analyse(text, provider).config
        weights = weight_config_from_weights(jd.derived_weights, WeightConfig())
        runs[name] = (jd, weights, run_match(profiles, jd, weights, EquivalenceStore()))
    return profiles, runs, lane_of


def lane_of_jd(name: str) -> str:
    return name[3:].rsplit("_", 1)[0]


def test_the_corpus_is_the_expected_shape(scaled):
    profiles, runs, _ = scaled
    assert len(profiles) == 120
    assert len(runs) == 20


def test_every_jd_ranks_at_least_ten_profiles(scaled):
    """A JD that survives stage 1 with fewer than ten candidates is not
    really being ranked, and would not exercise ordering at all."""
    _profiles, runs, _ = scaled
    thin = {
        name: run.scored_count for name, (_jd, _w, run) in runs.items() if run.scored_count < 10
    }
    assert not thin, f"JDs scoring fewer than 10: {thin}"


def test_all_2400_pairings_hold_the_core_invariants(scaled):
    _profiles, runs, _ = scaled
    for name, (jd, weights, run) in runs.items():
        assert sum(jd.derived_weights.values()) == 100, name
        for result in run.results:
            tag = f"{name}/{result.display_name}"
            assert 0 <= result.match_score <= 100, tag
            assert 0 <= result.analysis_confidence <= 100, tag
            if result.verdict == "deployable_now":
                assert result.gate_passed, tag
                assert result.match_score >= weights.deployable_threshold * 100 - 1e-6, tag
            if not result.gate_passed:
                assert result.verdict in ("trainable", "not_a_fit"), tag
            for fit in result.skill_fits:
                assert 0 <= fit.fit <= 1, f"{tag}/{fit.skill}"
                if fit.listed_only:
                    assert fit.fit <= weights.listed_only_cap + 1e-9, f"{tag}/{fit.skill}"
            lost = sum(row["lost"] for row in result.explanation.why_not_higher)
            assert result.match_score + lost == pytest.approx(100, abs=1.0), tag
            total = sum(d["contribution"] for d in result.facts["dimensions"])
            assert total == pytest.approx(result.match_score, abs=0.05), tag


def test_no_summary_is_rejected_by_its_own_validator(scaled):
    """Regression guard for related-technology credit.

    template_summary writes "related technology (Angular), credit capped at
    50%" straight from the facts, and validate_summary then called it
    hallucinated because matched_skill was missing from the allowed set. The
    engine was rejecting its own output on every candidate matched through a
    neighbouring technology.
    """
    _profiles, runs, _ = scaled
    for name, (_jd, _w, run) in runs.items():
        for result in run.results:
            ok, why = validate_summary(result.explanation.summary, result.facts)
            assert ok, f"{name}/{result.display_name}: {why}"


def test_no_summary_uses_forbidden_wording(scaled):
    _profiles, runs, _ = scaled
    for name, (_jd, _w, run) in runs.items():
        for result in run.results:
            lowered = result.explanation.summary.lower()
            for phrase in FORBIDDEN_PHRASES:
                assert phrase not in lowered, f"{name}/{result.display_name}"


# -- ranking quality --------------------------------------------------------


def test_every_jd_is_topped_by_its_own_lane(scaled):
    _profiles, runs, lane_of = scaled
    for name, (_jd, _w, run) in runs.items():
        assert run.results, name
        top_lane = lane_of[run.results[0].profile_id][0]
        assert top_lane == lane_of_jd(name), f"{name} topped by {top_lane}"


def test_lane_precision_at_10_stays_high(scaled):
    """Across 20 JDs, the top 10 should be dominated by the matching lane."""
    _profiles, runs, lane_of = scaled
    exact = neighbour = 0
    for name, (_jd, _w, run) in runs.items():
        lane = lane_of_jd(name)
        for result in run.results[:10]:
            found = lane_of[result.profile_id][0]
            if found == lane:
                exact += 1
            elif found in NEIGHBOURS.get(lane, set()):
                neighbour += 1
    total = len(runs) * 10
    assert exact / total >= 0.90, f"lane precision@10 = {exact / total:.0%}"
    assert (exact + neighbour) / total >= 0.99


def test_juniors_do_not_outrank_leads_on_senior_roles(scaled):
    """Within the matching lane, the top of a senior JD must not be junior."""
    _profiles, runs, lane_of = scaled
    for name, (_jd, _w, run) in runs.items():
        if not name.endswith("_senior"):
            continue
        lane = lane_of_jd(name)
        same_lane = [r for r in run.results if lane_of[r.profile_id][0] == lane]
        if len(same_lane) >= 4:
            bands = [lane_of[r.profile_id][1] for r in same_lane[:3]]
            assert "junior" not in bands, f"{name}: junior in top 3 ({bands})"


def test_a_mid_level_jd_admits_more_candidates_than_its_senior_twin(scaled):
    """The same lane at a lower bar must not be stricter."""
    _profiles, runs, _ = scaled
    for name, (_jd, _w, run) in runs.items():
        if not name.endswith("_mid"):
            continue
        senior = name.replace("_mid", "_senior")
        if senior not in runs:
            continue
        mid_ok = len(run.by_verdict("deployable_now"))
        senior_ok = len(runs[senior][2].by_verdict("deployable_now"))
        assert mid_ok >= senior_ok, f"{name} ({mid_ok}) < {senior} ({senior_ok})"


def test_the_generated_corpus_is_deterministic():
    first_jds, first_profiles = build_corpus()
    second_jds, second_profiles = build_corpus()
    assert first_jds == second_jds
    assert [p.text for p in first_profiles] == [p.text for p in second_profiles]
