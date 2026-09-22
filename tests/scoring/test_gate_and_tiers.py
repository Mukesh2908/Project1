"""Gate, verdicts and the tier cap — project.md 11.4 and 12.1, decisions D5 and D10."""

from app.schemas.evidence import ProfileRecord
from app.schemas.jd import JDConfig, Requirement
from app.schemas.result import SkillFit, WeightConfig
from app.scoring.dimensions import importance_weighted_mean, select_scored_requirements
from app.scoring.gate import borderline_flags, decide_verdict, gate_passed

WEIGHTS = WeightConfig()
MULTIPLIERS = WEIGHTS.importance_multipliers


def primary(skill, fit):
    return SkillFit(skill=skill, tier="primary", importance="mandatory", fit=fit)


# -- dual primary, decision D5 --------------------------------------------


def test_single_primary_above_the_gate_passes():
    assert gate_passed([primary("React", 0.95)], WEIGHTS)[0] is True


def test_dual_primary_all_mode_requires_both():
    fits = [primary("React", 0.95), primary("Node.js", 0.10)]
    passed, failed = gate_passed(fits, WEIGHTS, "all")
    assert passed is False
    assert failed == ["Node.js"]


def test_dual_primary_any_mode_accepts_one():
    fits = [primary("React", 0.95), primary("Node.js", 0.10)]
    passed, failed = gate_passed(fits, WEIGHTS, "any")
    assert passed is True
    assert failed == ["Node.js"]


def test_all_is_the_default_so_the_strict_reading_applies_untouched():
    assert JDConfig(jd_id="X").dual_primary_mode == "all"


def test_the_two_modes_disagree_exactly_where_the_spec_says():
    """The case that motivated D5: strong React, no Node, full-stack JD."""
    fits = [primary("React", 0.95), primary("Node.js", 0.10)]
    profile = ProfileRecord(profile_id="C-1")
    strict = JDConfig(jd_id="X", dual_primary_mode="all")
    lenient = JDConfig(jd_id="X", dual_primary_mode="any")
    strict_verdict, _, _ = decide_verdict(fits, profile, strict, WEIGHTS, 88.0)
    lenient_verdict, _, _ = decide_verdict(fits, profile, lenient, WEIGHTS, 88.0)
    assert strict_verdict == "trainable"
    assert lenient_verdict == "deployable_now"


# -- verdicts --------------------------------------------------------------


def test_high_score_below_the_gate_is_never_deployable():
    """Secondary skills must not lift anyone past a failed gate."""
    fits = [primary("React", 0.30)]
    verdict, passed, _ = decide_verdict(
        fits, ProfileRecord(profile_id="C"), JDConfig(jd_id="X"), WEIGHTS, 95.0
    )
    assert passed is False
    assert verdict == "trainable"


def test_below_the_trainable_threshold_is_not_a_fit():
    fits = [primary("React", 0.05)]
    verdict, _, _ = decide_verdict(
        fits, ProfileRecord(profile_id="C"), JDConfig(jd_id="X"), WEIGHTS, 40.0
    )
    assert verdict == "not_a_fit"


def test_gate_passed_but_score_short_is_ramp_up():
    fits = [primary("React", 0.90)]
    verdict, _, reasons = decide_verdict(
        fits, ProfileRecord(profile_id="C"), JDConfig(jd_id="X"), WEIGHTS, 72.0
    )
    assert verdict == "needs_ramp_up"
    assert any("below" in r for r in reasons)


def test_user_set_minimum_years_blocks_deployable():
    """A floor the user set in My Requirements is a hard gate."""
    fits = [
        SkillFit(
            skill="React",
            tier="primary",
            importance="mandatory",
            fit=0.95,
            hands_on_years=1.0,
            required_years=4.0,
            min_years=3.0,
        )
    ]
    verdict, _, reasons = decide_verdict(
        fits, ProfileRecord(profile_id="C"), JDConfig(jd_id="X"), WEIGHTS, 92.0
    )
    assert verdict == "needs_ramp_up"
    assert any("minimum" in r for r in reasons)


def test_inferred_jd_years_do_not_gate_separately():
    """project.md 13.5: React 3.5 yrs against an inferred 4 is still Deployable Now.

    The shortfall is already inside the fit score, so gating on it again would
    both double-count the gap and contradict the spec's own worked example.
    """
    fits = [
        SkillFit(
            skill="React",
            tier="primary",
            importance="mandatory",
            fit=0.975,
            hands_on_years=3.5,
            required_years=4.0,
            min_years=None,
        )
    ]
    verdict, _, _ = decide_verdict(
        fits, ProfileRecord(profile_id="C"), JDConfig(jd_id="X"), WEIGHTS, 84.0
    )
    assert verdict == "deployable_now"


def test_borderline_scores_are_flagged():
    flags = borderline_flags(81.5, [primary("React", 0.95)], WEIGHTS)
    assert any("deployable threshold" in f for f in flags)


def test_borderline_primary_near_the_gate_is_flagged():
    flags = borderline_flags(95.0, [primary("React", 0.61)], WEIGHTS)
    assert any("gate" in f for f in flags)


# -- tier cap, decision D10 ------------------------------------------------


def build_jd(core_count, secondary_count, mandatory_core=0):
    requirements = [
        Requirement(skill="React", tier="primary", importance="mandatory", focus_score=112)
    ]
    for i in range(core_count):
        requirements.append(
            Requirement(
                skill=f"Core{i}",
                tier="core",
                focus_score=50 - i,
                importance="mandatory" if i < mandatory_core else "preferred",
            )
        )
    for i in range(secondary_count):
        requirements.append(Requirement(skill=f"Sec{i}", tier="secondary", focus_score=10 - i))
    return JDConfig(jd_id="X", requirements=requirements)


def test_tier_cap_limits_core_to_five():
    jd = select_scored_requirements(build_jd(8, 0), cap=5)
    assert len(jd.scored_by_tier("core")) == 5
    assert len(jd.by_tier("core")) == 8  # the rest still reported, just not scored


def test_tier_cap_keeps_the_highest_focus_scores():
    jd = select_scored_requirements(build_jd(8, 0), cap=5)
    kept = {r.skill for r in jd.scored_by_tier("core")}
    assert kept == {"Core0", "Core1", "Core2", "Core3", "Core4"}


def test_mandatory_requirements_survive_the_cap():
    jd = select_scored_requirements(build_jd(8, 0, mandatory_core=7), cap=5)
    scored = jd.scored_by_tier("core")
    assert len(scored) == 7
    assert all(r.importance == "mandatory" for r in scored)


def test_primary_is_never_capped():
    requirements = [
        Requirement(skill=f"P{i}", tier="primary", focus_score=100 - i) for i in range(7)
    ]
    jd = select_scored_requirements(JDConfig(jd_id="X", requirements=requirements), cap=5)
    assert len(jd.scored_by_tier("primary")) == 7


def test_padded_jd_no_longer_moves_the_secondary_score():
    """The defect behind D10, using the numbers from project.md 11.4."""

    def secondary_score(extra_zero_skills):
        fits = [
            SkillFit(skill="SQL", tier="secondary", importance="preferred", fit=0.805),
            SkillFit(skill="Python", tier="secondary", importance="preferred", fit=0.10),
        ]
        fits += [
            SkillFit(skill=f"Z{i}", tier="secondary", importance="preferred", fit=0.0, scored=False)
            for i in range(extra_zero_skills)
        ]
        return importance_weighted_mean(fits, MULTIPLIERS)

    # Unscored padding must not change the result.
    assert secondary_score(0) == secondary_score(3) == 45.25


def test_without_the_cap_padding_would_still_drag_the_mean():
    """Documents the old behaviour so the fix cannot be silently reverted."""
    fits = [
        SkillFit(skill="SQL", tier="secondary", importance="preferred", fit=0.805),
        SkillFit(skill="Python", tier="secondary", importance="preferred", fit=0.10),
    ] + [
        SkillFit(skill=f"Z{i}", tier="secondary", importance="preferred", fit=0.0) for i in range(3)
    ]
    assert importance_weighted_mean(fits, MULTIPLIERS) == 18.1


def test_importance_weighting_matches_the_spec_core_mean():
    fits = [
        SkillFit(skill="TypeScript", tier="core", importance="mandatory", fit=1.0),
        SkillFit(skill="Redux", tier="core", importance="important", fit=0.622),
    ]
    assert round(importance_weighted_mean(fits, MULTIPLIERS), 1) == 84.9


# -- project relevance is no longer a constant (fixes a dead 0.5 fallback) --


def test_project_relevance_discriminates_by_content():
    """The previous behaviour gave every project 0.5 regardless of content,
    which is mathematically incapable of telling a matching project from an
    unrelated one. This proves the replacement actually varies."""
    from app.schemas.evidence import Project
    from app.scoring.dimensions import default_project_relevance

    jd = JDConfig(
        jd_id="X",
        responsibilities=["Build and ship React components for banking journeys"],
        requirements=[
            Requirement(skill="React", tier="primary", category="skill"),
            Requirement(skill="TypeScript", tier="core", category="skill"),
        ],
    )
    matching = Project(
        project_id="p1",
        title="Banking Portal",
        text="Built React components and TypeScript screens for banking journeys",
        skills=[],
    )
    unrelated = Project(
        project_id="p2",
        title="Warehouse Inventory",
        text="Maintained a legacy COBOL batch job for warehouse inventory counts",
        skills=[],
    )
    empty = Project(project_id="p3", title="Untitled", text="", skills=[])

    high = default_project_relevance(matching, jd)
    low = default_project_relevance(unrelated, jd)
    zero = default_project_relevance(empty, jd)

    # The unrelated project shares literally no tokens with the JD, so 0 is
    # the correct answer for it, not a test bug — the point being proven is
    # that it differs from `high` at all, which a constant never could.
    assert high > low
    assert high > 0
    assert zero == 0.0
    assert 0.0 <= high <= 1.0
    assert 0.0 <= low <= 1.0


def test_project_relevance_with_no_jd_text_does_not_crash():
    from app.schemas.evidence import Project
    from app.scoring.dimensions import default_project_relevance

    jd = JDConfig(jd_id="X")
    project = Project(project_id="p1", title="Something", text="some text", skills=[])
    assert default_project_relevance(project, jd) == 0.0


def test_project_experience_score_now_varies_with_project_content():
    """End to end: project_experience_score must no longer be identical for
    two candidates whose projects have completely different content."""
    from datetime import date

    from app.schemas.evidence import ProfileRecord, Project
    from app.scoring.dimensions import project_experience_score

    jd = JDConfig(
        jd_id="X",
        responsibilities=["Build and ship React components for banking journeys"],
        requirements=[Requirement(skill="React", tier="primary", category="skill")],
    )

    def profile_with(text: str) -> ProfileRecord:
        return ProfileRecord(
            profile_id="C",
            projects=[
                Project(
                    project_id="p1",
                    title="Project",
                    start=date(2022, 1, 1),
                    end=None,
                    text=text,
                    skills=[],
                )
            ],
        )

    on_topic = project_experience_score(
        profile_with("Built React components for banking journeys"), jd
    )
    off_topic = project_experience_score(profile_with("Maintained a legacy COBOL batch job"), jd)
    assert on_topic > off_topic
