"""Style-invariance — project.md 23.3, and the fairness point in 20.5.

Roughly a third of skill fit keys on how a resume is written: section 7.2 caps
depth by phrasing, and ``ownership_part`` keys on direct action verbs. That
tracks English fluency and writing culture rather than competence, and it
disadvantages anyone whose resume says "we built" instead of "I built".

This test measures the size of that effect on a matched pair — same facts, same
dates, same projects, different voice. It needs no second rater, which matters
because the eval labels are self-authored (decision D1).

The tolerance below is a measurement, not an aspiration. Tighten it as the
parser improves; never loosen it to make a build pass.
"""

from pathlib import Path

import pytest

from app.schemas.result import WeightConfig
from app.scoring.weights import weight_config_from_weights
from app.services.jd_analyzer import analyse
from app.services.matching_engine import run_match
from app.services.profile_analyzer import ingest_file
from app.services.skill_engine import EquivalenceStore
from tests.fixtures.mock_responses import build_mock_provider

FIXTURES = Path(__file__).parent / "fixtures"

#: Current measured gap between the matched pair. Documented rather than
#: aspirational: the engine really does score prose this much.
STYLE_TOLERANCE_POINTS = 12.0


def score_pair() -> tuple[float, float]:
    provider = build_mock_provider()
    jd = analyse((FIXTURES / "jds" / "jd001_react_senior.txt").read_text(), provider).config
    weights = weight_config_from_weights(jd.derived_weights, WeightConfig())

    profiles = [
        ingest_file(FIXTURES / "resumes" / name, provider).profile
        for name in ("c001_react_strong.txt", "c006_react_strong_teamvoice.txt")
    ]
    run = run_match(profiles, jd, weights, EquivalenceStore())
    by_id = {r.profile_id: r.match_score for r in run.results}
    return by_id[profiles[0].profile_id], by_id[profiles[1].profile_id]


def test_same_facts_in_two_voices_score_within_tolerance():
    direct, team = score_pair()
    gap = abs(direct - team)
    assert gap <= STYLE_TOLERANCE_POINTS, (
        f"Writing style moved the score by {gap:.1f} points "
        f"(direct voice {direct:.1f}, team voice {team:.1f}). "
        "The engine is scoring prose rather than proof."
    )


def test_neither_voice_crosses_a_verdict_boundary_the_other_does_not():
    """A phrasing difference must not change the decision."""
    provider = build_mock_provider()
    jd = analyse((FIXTURES / "jds" / "jd001_react_senior.txt").read_text(), provider).config
    weights = weight_config_from_weights(jd.derived_weights, WeightConfig())
    profiles = [
        ingest_file(FIXTURES / "resumes" / name, provider).profile
        for name in ("c001_react_strong.txt", "c006_react_strong_teamvoice.txt")
    ]
    run = run_match(profiles, jd, weights, EquivalenceStore())
    verdicts = {r.verdict for r in run.results}
    assert len(verdicts) == 1, (
        f"The same facts produced different verdicts depending on phrasing: {verdicts}"
    )


def test_the_gap_is_reported_not_hidden():
    """Whatever the gap is, it must be visible in the run, not silently absorbed."""
    direct, team = score_pair()
    assert direct >= team, "Direct phrasing is expected to score at least as high"
    print(f"\nStyle gap: {direct - team:.1f} points (direct {direct:.1f}, team {team:.1f})")


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
