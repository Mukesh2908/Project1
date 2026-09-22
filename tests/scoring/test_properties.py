"""Property tests — project.md 23.1.

``app/scoring`` is pure functions, which makes these cheap and worth far more
than the same effort spent on more examples.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.schemas.enums import DIMENSIONS
from app.schemas.evidence import EvidenceCard
from app.schemas.jd import Requirement
from app.schemas.result import WeightConfig
from app.scoring.gate import gate_passed
from app.scoring.skill_proof import compute_skill_fit
from app.scoring.weights import apply_primary_floor, largest_remainder, normalise_points

WEIGHTS = WeightConfig()

depths = st.integers(min_value=1, max_value=5)
years = st.one_of(st.none(), st.floats(min_value=0, max_value=25, allow_nan=False))
projects = st.integers(min_value=0, max_value=12)
since = st.one_of(st.none(), st.floats(min_value=0, max_value=20, allow_nan=False))


def build_card(depth, hands_on, project_count, current, years_since, production, ownership, listed):
    return EvidenceCard(
        skill="X",
        max_depth=depth,
        hands_on_years=hands_on,
        projects_used=project_count,
        is_current=current,
        years_since_last_use=years_since,
        production=production,
        ownership=ownership,
        skills_list_only=listed,
    )


def build_req(required_depth, required_years):
    return Requirement(
        skill="X",
        tier="primary",
        required_depth=required_depth,
        required_years=required_years,
    )


def fit(card, requirement, relation="exact"):
    return compute_skill_fit(requirement, card, relation, "X", WEIGHTS, is_primary=True).fit


@given(
    depths,
    years,
    projects,
    st.booleans(),
    since,
    st.booleans(),
    st.sampled_from(["self", "team", "vague"]),
    depths,
    st.floats(min_value=0.5, max_value=12, allow_nan=False),
)
@settings(max_examples=250, deadline=None)
def test_fit_always_within_bounds(d, y, p, cur, s, prod, own, rd, ry):
    value = fit(build_card(d, y, p, cur, s, prod, own, False), build_req(rd, ry))
    assert 0.0 <= value <= 1.0


@given(
    depths,
    st.floats(min_value=0, max_value=20, allow_nan=False),
    projects,
    depths,
    st.floats(min_value=0.5, max_value=12, allow_nan=False),
)
@settings(max_examples=250, deadline=None)
def test_more_projects_never_lowers_fit(d, y, p, rd, ry):
    """Adding evidence must never be a penalty."""
    fewer = fit(build_card(d, y, p, True, None, True, "self", False), build_req(rd, ry))
    more = fit(build_card(d, y, p + 1, True, None, True, "self", False), build_req(rd, ry))
    assert more >= fewer - 1e-9


@given(
    depths,
    st.floats(min_value=0, max_value=20, allow_nan=False),
    projects,
    depths,
    st.floats(min_value=0.5, max_value=10, allow_nan=False),
)
@settings(max_examples=250, deadline=None)
def test_raising_the_bar_never_raises_fit(d, y, p, rd, ry):
    card = build_card(d, y, p, True, None, True, "self", False)
    easier = fit(card, build_req(rd, ry))
    harder = fit(card, build_req(min(5, rd + 1), ry + 2))
    assert harder <= easier + 1e-9


@given(
    depths,
    st.floats(min_value=0, max_value=20, allow_nan=False),
    projects,
    depths,
    st.floats(min_value=0.5, max_value=12, allow_nan=False),
    st.sampled_from(["exact", "equivalent", "related"]),
)
@settings(max_examples=250, deadline=None)
def test_listed_only_cap_survives_the_match_factor(d, y, p, rd, ry, relation):
    """The cap is applied before the factor, so the product can only be smaller."""
    card = build_card(d, y, p, False, 1.0, True, "self", True)
    value = fit(card, build_req(rd, ry), relation)
    assert value <= WEIGHTS.listed_only_cap + 1e-9


@given(
    depths,
    st.floats(min_value=0, max_value=20, allow_nan=False),
    projects,
    depths,
    st.floats(min_value=0.5, max_value=12, allow_nan=False),
)
@settings(max_examples=200, deadline=None)
def test_related_credit_never_beats_an_exact_claim(d, y, p, rd, ry):
    card = build_card(d, y, p, True, None, True, "self", False)
    assert fit(card, build_req(rd, ry), "related") <= fit(card, build_req(rd, ry), "exact") + 1e-9


@given(st.lists(st.integers(min_value=0, max_value=60), min_size=1, max_size=9))
@settings(max_examples=250, deadline=None)
def test_normalised_points_total_exactly_100(values):
    points = {d: v for d, v in zip(DIMENSIONS, values, strict=False)}
    result = normalise_points(points)
    assert sum(result.values()) in (0, 100)


@given(
    st.lists(st.integers(min_value=1, max_value=60), min_size=2, max_size=9),
    st.integers(min_value=0, max_value=60),
)
@settings(max_examples=250, deadline=None)
def test_primary_floor_preserves_the_total(values, floor):
    weights = {d: v for d, v in zip(DIMENSIONS, values, strict=False)}
    weights = normalise_points(weights)
    floored = apply_primary_floor(weights, floor=min(floor, 100))
    assert sum(floored.values()) == 100
    assert floored["primary_skill"] >= min(floor, 100) or weights.get("primary_skill", 0) >= floor


@given(
    st.dictionaries(
        st.sampled_from(DIMENSIONS),
        st.floats(min_value=0, max_value=50, allow_nan=False),
        min_size=1,
    )
)
@settings(max_examples=200, deadline=None)
def test_largest_remainder_never_overshoots(exact):
    total = sum(exact.values())
    if total <= 0:
        return
    scaled = {k: v * 100 / total for k, v in exact.items()}
    assert sum(largest_remainder(scaled).values()) == 100


@given(st.lists(st.floats(min_value=0, max_value=1, allow_nan=False), min_size=1, max_size=4))
@settings(max_examples=200, deadline=None)
def test_all_mode_is_never_more_permissive_than_any(fits):
    from app.schemas.result import SkillFit

    skill_fits = [
        SkillFit(skill=f"S{i}", tier="primary", fit=value) for i, value in enumerate(fits)
    ]
    strict, _ = gate_passed(skill_fits, WEIGHTS, "all")
    lenient, _ = gate_passed(skill_fits, WEIGHTS, "any")
    assert not (strict and not lenient)
