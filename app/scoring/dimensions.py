"""Dimension scores — project.md section 11.1.

Core and Secondary score the **top 5** requirements in their tier, not every
skill the JD lists (decision D10). Selection happens once per JD, never per
candidate: if candidates faced different skill sets the comparison table would
be meaningless.
"""

from app.schemas.evidence import ProfileRecord
from app.schemas.jd import JDConfig, Requirement
from app.schemas.result import SkillFit, WeightConfig

FAMILY_ADJACENT_CREDIT = 0.5


def select_scored_requirements(jd: JDConfig, cap: int) -> JDConfig:
    """Mark which requirements count toward Core and Secondary.

    All mandatory requirements survive the cap — they are gate-relevant, and
    section 8.9's "everything mandatory" conflict already asks the user to trim
    when there are too many. Remaining slots fill by focus score, ties broken
    alphabetically so the choice is deterministic.
    """
    out = jd.model_copy(deep=True)
    for tier in ("core", "secondary"):
        members = [r for r in out.requirements if r.tier == tier and r.category == "skill"]
        mandatory = [r for r in members if r.importance == "mandatory"]
        rest = [r for r in members if r.importance != "mandatory"]
        rest.sort(key=lambda r: (-(r.focus_score or 0.0), r.skill.lower()))
        keep = {id(r) for r in mandatory}
        for r in rest[: max(0, cap - len(mandatory))]:
            keep.add(id(r))
        for r in members:
            r.scored = id(r) in keep
    # Primary is never capped.
    for r in out.requirements:
        if r.tier == "primary" or r.category != "skill":
            r.scored = True
    return out


def importance_weighted_mean(fits: list[SkillFit], multipliers: dict[str, float]) -> float | None:
    """Mean of fits weighted by importance. ``None`` when there is nothing to score."""
    scored = [f for f in fits if f.scored]
    if not scored:
        return None
    total_weight = sum(multipliers.get(f.importance, 1.0) for f in scored)
    if total_weight <= 0:
        return None
    weighted = sum(multipliers.get(f.importance, 1.0) * f.fit for f in scored)
    return round(weighted / total_weight * 100, 4)


def tier_score(fits: list[SkillFit], tier: str, weights: WeightConfig) -> float | None:
    return importance_weighted_mean(
        [f for f in fits if f.tier == tier], weights.importance_multipliers
    )


def project_experience_score(
    profile: ProfileRecord,
    jd: JDConfig,
    relevance: dict[str, float] | None = None,
) -> float | None:
    """Mean of the best two projects — project.md 11.1.

    Per project: relevance 40 · uses primary/core 25 · complexity 10 ·
    ownership 10 · production 10 · duration 5. Latest x1.0, older x0.8.
    """
    if not profile.projects:
        return None
    relevance = relevance or {}
    primary_core = {r.skill.lower() for r in jd.requirements if r.tier in ("primary", "core")}
    scored: list[float] = []
    latest_id = profile.projects[0].project_id if profile.projects else None
    for project in profile.projects:
        rel = relevance.get(project.project_id, 0.5)
        uses = any(s.skill.lower() in primary_core for s in project.skills)
        max_depth = max((s.depth for s in project.skills), default=0)
        owns = any(s.ownership == "self" for s in project.skills)
        prod = any(s.production == "yes" for s in project.skills)
        months = _duration_months(project)

        value = (
            40 * min(1.0, max(0.0, rel))
            + 25 * (1.0 if uses else 0.0)
            + 10 * (max_depth / 5 if max_depth else 0.0)
            + 10 * (1.0 if owns else 0.0)
            + 10 * (1.0 if prod else 0.0)
            + 5 * min(1.0, months / 12)
        )
        if project.project_id != latest_id:
            value *= 0.8
        scored.append(value)

    scored.sort(reverse=True)
    top = scored[:2]
    return round(sum(top) / len(top), 4)


def _duration_months(project) -> float:
    if project.start is None:
        return 6.0
    from datetime import date as _date

    end = project.end or _date.today()
    return max(0.0, (end - project.start).days / 30.4)


def relevant_experience_score(profile: ProfileRecord, jd: JDConfig) -> tuple[float | None, bool]:
    """Years in the JD's role family. Returns (score, overqualified_flag)."""
    if jd.experience_min is None:
        return None, False
    years = _years_in_family(profile, jd.role_family)
    score = min(1.0, years / jd.experience_min) if jd.experience_min > 0 else 1.0
    ceiling = jd.experience_max if jd.experience_max is not None else jd.experience_min
    overqualified = years > ceiling + 3
    return round(score * 100, 4), overqualified


def _years_in_family(profile: ProfileRecord, role_family: str | None) -> float:
    if not role_family:
        return profile.total_experience_years or 0.0
    from datetime import date as _date

    months = 0.0
    for project in profile.projects:
        if project.role_family and project.role_family != role_family:
            continue
        if project.start is None:
            continue
        end = project.end or _date.today()
        months += max(0.0, (end - project.start).days / 30.4)
    return round(months / 12, 2)


def certification_score(profile: ProfileRecord, jd: JDConfig) -> float | None:
    """(required held + 0.5 x preferred held) / (required + 0.5 x preferred)."""
    certs = jd.certification_requirements
    if not certs:
        return None
    held = {c.name.lower(): c for c in profile.certifications}
    required = [c for c in certs if c.importance in ("mandatory", "important")]
    preferred = [c for c in certs if c.importance not in ("mandatory", "important")]
    denominator = len(required) + 0.5 * len(preferred)
    if denominator <= 0:
        return None

    def credit(req: Requirement) -> float:
        match = held.get(req.skill.lower())
        if match is None:
            return 0.0
        return 0.5 if match.status == "expired" else 1.0

    numerator = sum(credit(c) for c in required) + 0.5 * sum(credit(c) for c in preferred)
    return round(numerator / denominator * 100, 4)


def education_score(profile: ProfileRecord, jd: JDConfig) -> float | None:
    if not jd.education_requirements:
        return None
    wanted = " ".join(jd.education_requirements).lower()
    have = " ".join(profile.education).lower()
    if not have:
        return 0.0
    for token in ("phd", "m.tech", "mtech", "masters", "mca", "b.tech", "btech", "be", "bsc"):
        if token in wanted and token in have:
            return 100.0
    return 50.0 if have else 0.0


def role_seniority_score(
    profile: ProfileRecord, jd: JDConfig, adjacency: dict[str, list[str]]
) -> float | None:
    """0.6 x role-family match + 0.4 x seniority band fit."""
    if not jd.role_family:
        return None
    family = profile.role_family
    if family == jd.role_family:
        family_score = 1.0
    elif family and family in adjacency.get(jd.role_family, []):
        family_score = FAMILY_ADJACENT_CREDIT
    else:
        family_score = 0.0

    bands = ["junior", "mid", "senior", "lead"]
    try:
        distance = abs(bands.index(profile.seniority or "mid") - bands.index(jd.seniority))
    except ValueError:
        distance = 1
    seniority_score = max(0.0, 1.0 - 0.5 * distance)
    return round((0.6 * family_score + 0.4 * seniority_score) * 100, 4)


def domain_fit_score(
    profile: ProfileRecord, jd: JDConfig, adjacency: dict[str, list[str]]
) -> float | None:
    if not jd.domain:
        return None
    domains = {d.lower() for d in profile.domains if d}
    domains |= {p.domain.lower() for p in profile.projects if p.domain}
    target = jd.domain.lower()
    if target in domains:
        return 100.0
    for adjacent in adjacency.get(jd.domain, []):
        if adjacent.lower() in domains:
            return 50.0
    return 0.0


def weighted_total(
    dimension_scores: dict[str, float | None], weights: WeightConfig
) -> tuple[float, dict[str, float]]:
    """Weighted sum over dimensions that have a score.

    Dimensions scoring ``None`` are not applicable: their weight is spread over
    the rest so the total still reads out of 100.
    """
    applicable = {
        d: s for d, s in dimension_scores.items() if s is not None and weights.weight_of(d) > 0
    }
    if not applicable:
        return 0.0, {}
    weight_sum = sum(weights.weight_of(d) for d in applicable)
    if weight_sum <= 0:
        return 0.0, {}
    scale = 100 / weight_sum
    contributions = {
        d: round(weights.weight_of(d) * scale * s / 100, 4) for d, s in applicable.items()
    }
    return round(sum(contributions.values()), 4), contributions


def effective_weights(
    dimension_scores: dict[str, float | None], weights: WeightConfig
) -> dict[str, float]:
    """Weights after N/A redistribution — what the UI and Excel actually show."""
    applicable = [
        d for d, s in dimension_scores.items() if s is not None and weights.weight_of(d) > 0
    ]
    weight_sum = sum(weights.weight_of(d) for d in applicable)
    if weight_sum <= 0:
        return {}
    scale = 100 / weight_sum
    return {d: round(weights.weight_of(d) * scale, 4) for d in applicable}
