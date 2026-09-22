"""The one-line reason shown beside every score — project.md 13.

It sits in a ranked list where nobody will open a detail page, so it has to
be correct on its own: grounded in the facts, factual in wording, and never
self-contradictory.
"""

import pytest

from app.schemas.enums import FORBIDDEN_PHRASES
from app.services.explanation_engine import score_reason


def facts(
    *,
    gate_passed=True,
    match_score=80.0,
    primaries=(("React", 90.0, "exact", "React"),),
    dimensions=(("Core skills", "core_skills", 60.0, 15.0, 25.0),),
):
    return {
        "gate_passed": gate_passed,
        "gate_threshold": 60.0,
        "match_score": match_score,
        "skills": [
            {
                "skill": name,
                "tier": "primary",
                "fit": fit,
                "relation": relation,
                "matched_skill": matched,
                "scored": True,
                "gap": "",
            }
            for name, fit, relation, matched in primaries
        ],
        "dimensions": [
            {"name": key, "label": label, "score": score, "weight": weight,
             "contribution": contribution}
            for label, key, score, contribution, weight in dimensions
        ],
    }


def test_a_failed_gate_is_the_whole_reason():
    reason = score_reason(
        facts(gate_passed=False, primaries=(("React", 50.0, "exact", "React"),))
    )
    assert "React 50.0%" in reason
    assert "under the 60% gate" in reason


def test_related_technology_credit_is_named_on_a_failed_gate():
    reason = score_reason(
        facts(gate_passed=False, primaries=(("React", 50.0, "related", "Angular"),))
    )
    assert "via Angular" in reason


def test_no_evidence_at_all_says_so():
    reason = score_reason(
        facts(gate_passed=False, match_score=6.0, primaries=(("React", 0.0, "none", None),))
    )
    assert "No React evidence" in reason
    assert "other dimensions alone" in reason


def test_a_dual_primary_with_one_half_missing_does_not_claim_nothing_was_found():
    """Saying the score came from "other dimensions alone" would be plainly
    false for someone who holds one of the two primaries."""
    reason = score_reason(
        facts(
            gate_passed=False,
            match_score=38.0,
            primaries=(("Node.js", 0.0, "none", None), ("React", 100.0, "exact", "React")),
        )
    )
    assert "No Node.js evidence" in reason
    assert "React 100%" in reason
    assert "other dimensions alone" not in reason


def test_a_passing_score_names_the_primary_and_the_other_gaps():
    reason = score_reason(facts())
    assert "React 90%" in reason
    assert "Core skills" in reason


def test_the_primary_is_never_listed_as_both_driver_and_gap():
    """"Primary skill 94% ... lost most to Primary skill" is incoherent."""
    reason = score_reason(
        facts(
            dimensions=(
                ("Primary skill", "primary_skill", 94.0, 51.6, 55.0),
                ("Core skills", "core_skills", 60.0, 15.0, 25.0),
            )
        )
    )
    assert reason.count("Primary skill") == 0


def test_both_primaries_are_named_on_a_dual_role():
    reason = score_reason(
        facts(primaries=(("React", 100.0, "exact", "React"), ("Node.js", 95.0, "exact", "Node.js")))
    )
    assert "React 100%" in reason
    assert "Node.js 95%" in reason


def test_a_jd_with_no_primary_still_produces_a_reason():
    reason = score_reason(facts(primaries=()))
    assert reason
    assert "Core skills" in reason


def test_no_dimensions_at_all_does_not_crash():
    assert score_reason(facts(primaries=(), dimensions=())) == "No scored dimensions"


@pytest.mark.parametrize("phrase", FORBIDDEN_PHRASES)
def test_the_reason_never_uses_forbidden_wording(phrase):
    for sample in (
        facts(),
        facts(gate_passed=False, primaries=(("React", 0.0, "none", None),)),
        facts(gate_passed=False, primaries=(("React", 40.0, "related", "Vue"),)),
    ):
        assert phrase not in score_reason(sample).lower()
