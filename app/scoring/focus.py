"""Focus scores, tiers, importance and required levels — project.md 8.4 to 8.7.

The LLM tags signals; everything numeric happens here.
"""

from app.schemas.jd import Requirement, SkillSignal

POINTS = {
    "in_title": 40,
    "in_opening": 15,
    "per_bullet": 8,
    "bullets_max": 32,
    "per_mention": 2,
    "mentions_max": 10,
    "strong_language": 15,
    "optional_language": -15,
    "same_family": 10,
}

DEPTH_WORDS = {
    2: ["exposure", "familiar", "basic", "awareness", "knowledge of"],
    3: ["hands-on", "hands on", "working knowledge", "good", "develop", "build"],
    4: ["strong", "expert", "advanced", "tuning", "optimization", "optimize", "performance"],
    5: ["lead", "architect", "own the design", "mentor", "design ownership"],
}

SENIORITY_YEARS = {"junior": 1.0, "mid": 3.0, "senior": 5.0, "lead": 8.0}
SENIORITY_DEPTH = {"junior": 2, "mid": 3, "senior": 4, "lead": 5}


def focus_score(
    signal: SkillSignal, same_family_as_top: bool = False
) -> tuple[float, dict[str, float]]:
    """Returns the score and its breakdown, so the UI can show the arithmetic."""
    breakdown: dict[str, float] = {}
    if signal.in_title:
        breakdown["Title"] = POINTS["in_title"]
    if signal.in_opening:
        breakdown["Opening"] = POINTS["in_opening"]
    if signal.responsibility_bullets:
        breakdown[f"{signal.responsibility_bullets} bullets"] = min(
            POINTS["bullets_max"], POINTS["per_bullet"] * signal.responsibility_bullets
        )
    if signal.extra_mentions:
        breakdown["Mentions"] = min(
            POINTS["mentions_max"], POINTS["per_mention"] * signal.extra_mentions
        )
    if signal.strong_language:
        label = f'"{signal.required_years:g}+ yrs"' if signal.required_years else "Strong"
        breakdown[label] = POINTS["strong_language"]
    if signal.optional_language:
        breakdown["Optional wording"] = POINTS["optional_language"]
    if same_family_as_top:
        breakdown["Same family"] = POINTS["same_family"]
    return float(sum(breakdown.values())), breakdown


def required_depth(signal: SkillSignal, seniority: str) -> int:
    """Depth the JD asks for, from its wording, falling back to seniority."""
    words = " ".join(w.lower() for w in signal.depth_words)
    for level in (5, 4, 3, 2):
        if any(token in words for token in DEPTH_WORDS[level]):
            return level
    return SENIORITY_DEPTH.get(seniority, 3)


def required_years(signal: SkillSignal, seniority: str) -> float:
    if signal.required_years is not None:
        return float(signal.required_years)
    return SENIORITY_YEARS.get(seniority, 3.0)


def importance_of(signal: SkillSignal) -> str:
    """Importance is independent of tier — project.md 8.6."""
    if signal.strong_language or signal.required_years is not None:
        return "mandatory"
    if signal.responsibility_bullets > 0:
        return "important"
    if signal.optional_language:
        return "optional"
    return "preferred"


def assign_tiers(
    signals: list[SkillSignal],
    families: dict[str, str],
    seniority: str,
    dual_primary_ratio: float = 0.8,
    substitutes: set[str] | None = None,
) -> list[Requirement]:
    """Focus scores → primary / core / secondary, with importance and levels.

    ``substitutes`` names skills that are alternatives to the primary rather
    than complements to it — Angular against React, say. Sections 8.4 and 8.5
    read literally would give Angular the same-family bonus and tier it Core on
    a React role, while section 9.1's own worked screen shows it as Secondary
    with a focus score of 0. Competing frameworks are the case the family rule
    was not written for, so they are excluded from both.
    """
    substitutes = substitutes or set()
    if not signals:
        return []

    # First pass without the family bonus, to find the top skill.
    provisional = {s.skill: focus_score(s)[0] for s in signals}
    top_skill = max(provisional, key=lambda k: (provisional[k], k))
    top_family = families.get(top_skill)

    requirements: list[Requirement] = []
    scores: dict[str, float] = {}
    breakdowns: dict[str, dict[str, float]] = {}
    for signal in signals:
        family = families.get(signal.skill)
        same_family = (
            bool(top_family)
            and family == top_family
            and signal.skill != top_skill
            and signal.skill not in substitutes
        )
        score, breakdown = focus_score(signal, same_family)
        scores[signal.skill] = score
        breakdowns[signal.skill] = breakdown

    primary_skill = max(scores, key=lambda k: (scores[k], k))
    primary_score = scores[primary_skill]
    primary_family = families.get(primary_skill)

    # Dual primary: a different family scoring at least 80% of the top.
    dual: set[str] = {primary_skill}
    for skill, score in scores.items():
        if skill == primary_skill:
            continue
        if (
            families.get(skill)
            and families.get(skill) != primary_family
            and primary_score > 0
            and score >= dual_primary_ratio * primary_score
        ):
            dual.add(skill)

    for signal in signals:
        skill = signal.skill
        family = families.get(skill)
        if skill in dual:
            tier = "primary"
        elif signal.responsibility_bullets > 0 or (
            family and family == primary_family and skill not in substitutes
        ):
            tier = "core"
        else:
            tier = "secondary"
        requirements.append(
            Requirement(
                skill=skill,
                category="skill",
                tier=tier,
                importance=importance_of(signal),
                required_depth=required_depth(signal, seniority),
                required_years=required_years(signal, seniority),
                focus_score=scores[skill],
                focus_breakdown=breakdowns[skill],
                family=family,
                source="ai",
                why=_why(signal),
            )
        )
    return requirements


def _why(signal: SkillSignal) -> str:
    bits: list[str] = []
    if signal.in_title:
        bits.append("in the job title")
    if signal.in_opening:
        bits.append("in the opening section")
    if signal.responsibility_bullets:
        bits.append(f"{signal.responsibility_bullets} responsibilities")
    if signal.required_years:
        bits.append(f'"{signal.required_years:g}+ years"')
    if signal.optional_language:
        bits.append("described as optional")
    return ", ".join(bits) or "mentioned in the JD"


def format_calculation(skill: str, breakdown: dict[str, float], total: float) -> str:
    """The arithmetic as shown on the JD Review screen — project.md 8.4."""
    parts = " · ".join(f"{k} {v:+g}" for k, v in breakdown.items())
    return f"{skill:12} {parts} = {total:g}"
