"""Weight derivation and normalisation — project.md 11.2, decisions D8 and D9.

The headline invariant: every matrix totals exactly 100. v2.0's five presets
totalled 90, 90, 95, 95 and 80 against a rule requiring 100, which is the bug
this file exists to prevent recurring.
"""

import yaml

from app.schemas.enums import DIMENSIONS
from app.schemas.jd import JDConfig, Requirement
from app.scoring.weights import (
    apply_primary_floor,
    derive_weights,
    largest_remainder,
    normalise_points,
    normalise_weight_config,
    redistribute_na,
    warnings_for,
    weight_config_from_weights,
)


def react_jd() -> JDConfig:
    """The JD from project.md section 9.1."""
    requirements = [
        Requirement(
            skill="React",
            tier="primary",
            importance="mandatory",
            focus_score=112,
            family="frontend",
            required_depth=4,
            required_years=4,
        ),
        Requirement(
            skill="TypeScript",
            tier="core",
            importance="mandatory",
            focus_score=41,
            family="frontend",
            required_depth=3,
            required_years=2,
        ),
        Requirement(
            skill="Redux", tier="core", importance="important", focus_score=18, family="frontend"
        ),
        Requirement(
            skill="Next.js", tier="core", importance="preferred", focus_score=16, family="frontend"
        ),
    ]
    for skill, family in [
        ("Angular", "frontend"),
        ("Python", "backend_python"),
        ("Java", "backend_java"),
        ("Scala", "backend_jvm"),
        ("SQL", "data"),
    ]:
        requirements.append(
            Requirement(
                skill=skill, tier="secondary", importance="preferred", focus_score=0, family=family
            )
        )
    requirements.append(
        Requirement(
            skill="AWS Certified Developer", category="certification", importance="preferred"
        )
    )
    return JDConfig(
        jd_id="JD-0001",
        job_title="Senior Software Engineer — React",
        role_family="frontend_dev",
        seniority="senior",
        domain="BFSI",
        domain_required=False,
        experience_min=4,
        experience_max=7,
        delivery_bullets=4,
        requirements=requirements,
    )


def test_worked_example_matches_the_spec():
    """project.md 11.2 publishes these exact numbers."""
    weights, _ = derive_weights(react_jd())
    assert weights == {
        "primary_skill": 47,
        "core_skills": 14,
        "secondary_skills": 4,
        "project_experience": 13,
        "relevant_experience": 7,
        "certification": 7,
        "education": 0,
        "role_seniority": 4,
        "domain_fit": 4,
    }


def test_derived_matrix_always_totals_100():
    weights, _ = derive_weights(react_jd())
    assert sum(weights.values()) == 100


def test_every_weight_carries_a_reason():
    weights, reasons = derive_weights(react_jd())
    for dimension in weights:
        assert reasons.get(dimension), f"{dimension} has no reason to show the user"


def test_dimensions_the_jd_is_silent_about_get_zero():
    weights, reasons = derive_weights(react_jd())
    assert weights["education"] == 0
    assert "no education requirement" in reasons["education"]


def test_certification_weight_rises_when_required():
    jd = react_jd()
    for requirement in jd.requirements:
        if requirement.category == "certification":
            requirement.importance = "mandatory"
    required, _ = derive_weights(jd)
    preferred, _ = derive_weights(react_jd())
    assert required["certification"] > preferred["certification"]
    assert sum(required.values()) == 100


def test_domain_weight_rises_when_required():
    jd = react_jd()
    jd.domain_required = True
    weights, _ = derive_weights(jd)
    assert weights["domain_fit"] > derive_weights(react_jd())[0]["domain_fit"]
    assert sum(weights.values()) == 100


# -- the primary floor, decision D9 ---------------------------------------


def test_primary_floor_is_applied():
    weights = {"primary_skill": 20, "certification": 50, "core_skills": 30}
    floored = apply_primary_floor(weights, floor=35)
    assert floored["primary_skill"] == 35
    assert sum(floored.values()) == 100


def test_primary_floor_leaves_a_healthy_matrix_alone():
    weights = {"primary_skill": 47, "core_skills": 53}
    assert apply_primary_floor(weights, floor=35) == weights


def test_cert_heavy_jd_still_respects_the_floor():
    jd = react_jd()
    jd.requirements = [
        r for r in jd.requirements if r.tier == "primary" or r.category == "certification"
    ]
    for requirement in jd.requirements:
        if requirement.category == "certification":
            requirement.importance = "mandatory"
    jd.domain_required = True
    weights, _ = derive_weights(jd, floor=35)
    assert weights["primary_skill"] >= 35
    assert sum(weights.values()) == 100


# -- rounding --------------------------------------------------------------


def test_largest_remainder_hits_the_target_exactly():
    exact = {d: 100 / 3 for d in DIMENSIONS[:3]}
    assert sum(largest_remainder(exact).values()) == 100


def test_largest_remainder_breaks_ties_deterministically():
    exact = {"core_skills": 33.5, "primary_skill": 33.5, "secondary_skills": 33.0}
    result = largest_remainder(exact)
    # primary_skill precedes core_skills in the canonical order, so it wins the tie
    assert result["primary_skill"] == 34
    assert result["core_skills"] == 33


def test_normalise_points_handles_all_zero():
    assert sum(normalise_points({"primary_skill": 0, "core_skills": 0}).values()) == 0


# -- shipped presets -------------------------------------------------------


def test_every_shipped_preset_totals_100():
    """The v2.0 presets summed to 90, 90, 95, 95 and 80."""
    data = yaml.safe_load(open("app/data/weight_presets.yaml"))
    for key, preset in data["presets"].items():
        assert sum(preset["weights"].values()) == 100, f"{key} does not total 100"


def test_presets_only_use_known_dimensions():
    data = yaml.safe_load(open("app/data/weight_presets.yaml"))
    for key, preset in data["presets"].items():
        unknown = set(preset["weights"]) - set(DIMENSIONS)
        assert not unknown, f"{key} references unknown dimensions: {unknown}"


# -- UI helpers ------------------------------------------------------------


def test_normalize_button_rescales_to_100():
    cfg = weight_config_from_weights({"primary_skill": 50, "core_skills": 45})
    assert normalise_weight_config(cfg).total() == 100


def test_na_redistribution_preserves_the_total():
    cfg = weight_config_from_weights({"primary_skill": 47, "core_skills": 14, "certification": 39})
    assert redistribute_na(cfg, {"certification"}).total() == 100


def test_warning_fires_when_primary_is_low():
    cfg = weight_config_from_weights({"primary_skill": 15, "core_skills": 85})
    assert any("keyword matching" in w for w in warnings_for(cfg))


def test_warning_fires_when_total_is_not_100():
    cfg = weight_config_from_weights({"primary_skill": 50, "core_skills": 45})
    assert any("must total 100" in w for w in warnings_for(cfg))
