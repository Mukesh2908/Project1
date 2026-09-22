"""Evidence → skill fit — project.md section 10.2.

Two rules here were undefined in v2.0 and are now normative:

* the listed-only cap applies **before** the match factor, which is what
  reproduces the "Java developer scores ~5%" example in section 10.5;
* a part that cannot be computed is **dropped** and the remaining part weights
  are renormalised, rather than scored as zero. A missing date already costs
  Analysis Confidence 25 points, and penalising it in the score too would
  count the same gap twice.
"""

from app.schemas.evidence import EvidenceCard
from app.schemas.jd import Requirement
from app.schemas.result import SkillFit, WeightConfig

#: Parts whose absence means "unknown" rather than "zero".
DROPPABLE_PARTS = ("years", "recency")


def depth_part(shown_depth: int, required_depth: int) -> float:
    if required_depth <= 0:
        return 1.0
    return min(1.0, shown_depth / required_depth)


def years_part(hands_on_years: float | None, required_years: float) -> float | None:
    if hands_on_years is None:
        return None  # unknown → dropped and renormalised
    if required_years <= 0:
        return 1.0
    return min(1.0, hands_on_years / required_years)


def projects_part(distinct_projects: int) -> float:
    if distinct_projects >= 2:
        return 1.0
    if distinct_projects == 1:
        return 0.5
    return 0.0


def recency_part(
    card: EvidenceCard,
    is_primary: bool,
    jd_requires_recent: bool = False,
) -> float | None:
    """Recency, deliberately not over-punishing older core work — project.md 10.3."""
    if card.skills_list_only:
        return 0.0
    if card.is_current:
        return 1.0
    if card.years_since_last_use is None:
        return None  # unknown → dropped and renormalised
    if card.years_since_last_use <= 3:
        return 0.7
    if is_primary:
        return 0.4
    return 0.4 if jd_requires_recent else 0.7


def production_part(card: EvidenceCard) -> float:
    return 1.0 if card.production else 0.5


def ownership_part(card: EvidenceCard) -> float:
    return 1.0 if card.ownership == "self" else 0.5


def combine_parts(parts: dict[str, float | None], part_weights: dict[str, float]) -> float:
    """Weighted mean over the parts that are known, renormalised.

    With every part known this is the plain weighted sum, because the default
    part weights total 1.0.
    """
    known = {k: v for k, v in parts.items() if v is not None}
    if not known:
        return 0.0
    total_weight = sum(part_weights.get(k, 0.0) for k in known)
    if total_weight <= 0:
        return 0.0
    return sum(part_weights.get(k, 0.0) * v for k, v in known.items()) / total_weight


def compute_skill_fit(
    requirement: Requirement,
    card: EvidenceCard | None,
    relation: str,
    matched_skill: str | None,
    weights: WeightConfig,
    is_primary: bool = False,
    jd_requires_recent: bool = False,
) -> SkillFit:
    """Score one requirement against one candidate's evidence.

    ``card`` is ``None`` when no evidence of any kind was found, which scores 0
    rather than raising — "no evidence found" is a legitimate, reportable answer.
    """
    fit = SkillFit(
        skill=requirement.skill,
        tier=requirement.tier,
        importance=requirement.importance,
        required_depth=requirement.required_depth,
        required_years=requirement.required_years,
        min_years=requirement.min_years,
        matched_skill=matched_skill,
        relation=relation,  # type: ignore[arg-type]
        scored=requirement.scored,
    )

    if card is None or relation == "none":
        fit.match_factor = 0.0
        fit.fit = 0.0
        fit.gap_note = "No evidence found"
        return fit

    match_factor = weights.match_factors.get(relation, 0.0)
    parts: dict[str, float | None] = {
        "depth": depth_part(card.max_depth, requirement.required_depth),
        "years": years_part(card.hands_on_years, requirement.required_years),
        "projects": projects_part(card.projects_used),
        "recency": recency_part(card, is_primary, jd_requires_recent),
        "production": production_part(card),
        "ownership": ownership_part(card),
    }

    base = combine_parts(parts, weights.skill_proof_parts)

    # Cap BEFORE the match factor. Reversing these two lines changes the
    # section 10.5 Java-developer result from 5.0% to 8.1%.
    capped = False
    if card.skills_list_only:
        if base > weights.listed_only_cap:
            capped = True
        base = min(base, weights.listed_only_cap)

    fit.match_factor = match_factor
    fit.fit = max(0.0, min(1.0, base * match_factor))
    fit.parts = {k: v for k, v in parts.items() if v is not None}
    fit.parts_used = list(fit.parts.keys())
    fit.shown_depth = card.max_depth
    fit.hands_on_years = card.hands_on_years
    fit.projects_used = card.projects_used
    fit.production = card.production
    fit.ownership = card.ownership
    fit.listed_only = card.skills_list_only
    fit.capped = capped
    fit.last_used_label = _last_used_label(card)
    fit.evidence = [e.quote for e in card.evidence[:3]]
    fit.gap_note = _gap_note(fit, card, requirement)
    return fit


def _last_used_label(card: EvidenceCard) -> str:
    if card.skills_list_only:
        return "skills list only"
    if card.is_current:
        return "current"
    if card.years_since_last_use is None:
        return "date unknown"
    years = card.years_since_last_use
    if years < 1:
        return "within the last year"
    return f"{years:.0f} yrs ago"


def _gap_note(fit: SkillFit, card: EvidenceCard, requirement: Requirement) -> str:
    """Factual wording only — project.md 2.8."""
    gaps: list[str] = []
    if card.skills_list_only:
        gaps.append("skills list only, no project evidence")
    if card.max_depth < requirement.required_depth:
        gaps.append(f"depth L{card.max_depth} vs L{requirement.required_depth} required")
    if card.hands_on_years is None:
        gaps.append("no dates, years unknown")
    elif card.hands_on_years < requirement.required_years:
        gaps.append(f"{card.hands_on_years:.1f} yrs vs {requirement.required_years:.0f} required")
    if card.projects_used == 1:
        gaps.append("evidence in 1 project")
    if fit.relation == "related":
        gaps.append(f"related technology ({fit.matched_skill}), credit capped at 50%")
    elif fit.relation == "equivalent":
        gaps.append(f"equivalent technology ({fit.matched_skill})")
    if not gaps:
        return "Evidence found"
    return "Partial evidence: " + "; ".join(gaps)
