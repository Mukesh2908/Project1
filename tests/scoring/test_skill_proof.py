"""Golden tests from project.md sections 10.4, 10.5 and 13.5.

These numbers are quoted in the specification and in the Excel report examples;
if they move, either the spec or the code is wrong.
"""

import pytest

from app.schemas.evidence import EvidenceCard
from app.schemas.jd import Requirement
from app.schemas.result import WeightConfig
from app.scoring.skill_proof import combine_parts, compute_skill_fit


def card(
    depth=4,
    years=3.5,
    projects=3,
    current=True,
    since=None,
    production=True,
    ownership="self",
    listed=False,
):
    return EvidenceCard(
        skill="X",
        max_depth=depth,
        hands_on_years=years,
        projects_used=projects,
        is_current=current,
        years_since_last_use=since,
        production=production,
        ownership=ownership,
        skills_list_only=listed,
    )


def req(depth, years, tier="primary", importance="mandatory"):
    return Requirement(
        skill="X",
        tier=tier,
        importance=importance,
        required_depth=depth,
        required_years=years,
    )


def fit_of(requirement, evidence, relation="exact", primary=True, weights=None):
    return compute_skill_fit(
        requirement, evidence, relation, "X", weights or WeightConfig(), is_primary=primary
    ).fit_pct


# -- section 10.4 : SQL, required L4 and 3 years ---------------------------


def test_sql_candidate_a_full_proof():
    assert fit_of(req(4, 3), card(4, 3.5, 3, current=True)) == 100.0


def test_sql_candidate_b_shallow_and_stale():
    evidence = card(2, 1, 1, current=False, since=2, production=False)
    assert fit_of(req(4, 3), evidence) == 54.7


def test_sql_candidate_c_skills_list_only_is_capped():
    evidence = card(1, None, 0, current=False, production=False, ownership="vague", listed=True)
    assert fit_of(req(4, 3), evidence) == 10.0


# -- section 10.5 : React JD ----------------------------------------------


def test_react_developer():
    assert fit_of(req(4, 4), card(4, 3.5, 3, current=True)) == 97.5


def test_angular_developer_gets_related_credit_only():
    assert fit_of(req(4, 4), card(4, 4, 3, current=True), relation="related") == 50.0


def test_java_developer_with_angular_listed_once():
    """The cap must apply BEFORE the match factor: 0.10 x 0.5 = 5%, not 8.1%."""
    evidence = card(1, None, 0, current=False, production=False, ownership="vague", listed=True)
    assert fit_of(req(4, 4), evidence, relation="related") == 5.0


# -- section 13.5 : the worked example ------------------------------------


def test_typescript_core():
    evidence = card(3, 2.5, 2, current=True)
    assert fit_of(req(3, 2, "core"), evidence, primary=False) == 100.0


def test_redux_core_partial():
    evidence = card(2, 1, 1, current=False, since=2, production=False)
    assert fit_of(req(3, 2, "core"), evidence, primary=False) == 62.2


def test_sql_secondary():
    evidence = card(2, 1, 1, current=False, since=2, production=False)
    assert fit_of(req(2, 1, "secondary"), evidence, primary=False) == 80.5


# -- unknown-part renormalisation (project.md 10.2) ------------------------


def test_unknown_years_is_dropped_not_zeroed():
    """A missing date already costs confidence; it must not also score zero."""
    known = card(4, 3.5, 3, current=True)
    unknown = card(4, None, 3, current=True)
    with_years = fit_of(req(4, 3), known)
    without_years = fit_of(req(4, 3), unknown)
    assert with_years == 100.0
    assert without_years == 100.0  # renormalised over the remaining parts


def test_unknown_years_does_not_silently_help():
    """Dropping a part must not turn a weak profile into a strong one."""
    weak_known = card(2, 0.5, 1, current=False, since=2, production=False)
    weak_unknown = card(2, None, 1, current=False, since=2, production=False)
    assert fit_of(req(4, 3), weak_unknown) > fit_of(req(4, 3), weak_known)
    assert fit_of(req(4, 3), weak_unknown) < 70.0


def test_no_evidence_scores_zero_without_raising():
    result = compute_skill_fit(req(4, 3), None, "none", None, WeightConfig())
    assert result.fit == 0.0
    assert result.gap_note == "No evidence found"


def test_combine_parts_with_all_known_matches_plain_weighted_sum():
    weights = {"a": 0.5, "b": 0.5}
    assert combine_parts({"a": 1.0, "b": 0.0}, weights) == pytest.approx(0.5)


def test_combine_parts_with_nothing_known_is_zero():
    assert combine_parts({"a": None}, {"a": 0.5}) == 0.0
