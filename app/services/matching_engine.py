"""Stages 1 to 5 — project.md sections 4, 10 to 13.

Stage 1 is deliberately recall-oriented: it skips obvious non-starters, and
every exclusion is reported so nobody vanishes silently.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.config import taxonomy_version, weights_hash
from app.schemas.enums import DIMENSIONS
from app.schemas.evidence import ProfileRecord
from app.schemas.jd import JDConfig
from app.schemas.result import MatchResult, SkillFit, WeightConfig
from app.scoring import dimensions as dim
from app.scoring.confidence import candidate_confidence, review_flags
from app.scoring.gate import borderline_flags, decide_verdict
from app.scoring.skill_proof import compute_skill_fit
from app.services.explanation_engine import build_explanation, build_facts
from app.services.skill_engine import EquivalenceStore, best_match, domain_adjacency, role_adjacency


@dataclass
class Exclusion:
    profile_id: str
    display_name: str
    reason: str


@dataclass
class RunResult:
    run_id: str
    results: list[MatchResult] = field(default_factory=list)
    excluded: list[Exclusion] = field(default_factory=list)
    weights: WeightConfig | None = None

    @property
    def scored_count(self) -> int:
        return len(self.results)

    def by_verdict(self, verdict: str) -> list[MatchResult]:
        return [r for r in self.results if r.verdict == verdict]

    @property
    def review_queue(self) -> list[MatchResult]:
        return [r for r in self.results if r.review_flags]


def stage1_filter(
    profile: ProfileRecord, jd: JDConfig, store: EquivalenceStore
) -> tuple[bool, str]:
    """Cheap pre-filter on the primary skill and its close family.

    Returns (keep, reason). Anything with any trace of the primary — including
    related technology and a bare skills-list mention — is kept, because the
    proof engine is what decides how much that trace is worth.
    """
    primaries = jd.primaries
    if not primaries:
        return True, ""
    for requirement in primaries:
        matched, relation, _factor = best_match(requirement.skill, profile.evidence_cards, store)
        if matched and relation != "none":
            return True, ""
    names = ", ".join(p.skill for p in primaries)
    return False, f"No evidence of {names} or a close technology"


def score_profile(
    profile: ProfileRecord,
    jd: JDConfig,
    weights: WeightConfig,
    run_id: str,
    store: EquivalenceStore | None = None,
    project_relevance: dict[str, float] | None = None,
) -> MatchResult:
    """One candidate, end to end."""
    store = store or EquivalenceStore()
    fits: list[SkillFit] = []

    for requirement in jd.requirements:
        if requirement.category != "skill":
            continue
        matched, relation, _factor = best_match(requirement.skill, profile.evidence_cards, store)
        card = profile.evidence_cards.get(matched) if matched else None
        fits.append(
            compute_skill_fit(
                requirement,
                card,
                relation,
                matched,
                weights,
                is_primary=requirement.tier == "primary",
            )
        )

    scores: dict[str, float | None] = {
        "primary_skill": dim.tier_score(fits, "primary", weights),
        "core_skills": dim.tier_score(fits, "core", weights),
        "secondary_skills": dim.tier_score(fits, "secondary", weights),
        "project_experience": dim.project_experience_score(profile, jd, project_relevance),
        "certification": dim.certification_score(profile, jd),
        "education": dim.education_score(profile, jd),
        "role_seniority": dim.role_seniority_score(profile, jd, role_adjacency()),
        "domain_fit": dim.domain_fit_score(profile, jd, domain_adjacency()),
    }
    relevant, overqualified = dim.relevant_experience_score(profile, jd)
    scores["relevant_experience"] = relevant

    total, contributions = dim.weighted_total(scores, weights)
    verdict, gate_ok, reasons = decide_verdict(fits, profile, jd, weights, total)

    confidence, confidence_notes = candidate_confidence(profile, fits)
    borderline = borderline_flags(total, fits, weights)
    flags = review_flags(profile, jd, fits, confidence, borderline)
    if overqualified:
        flags.append("Possibly overqualified — well above the stated experience band")

    result = MatchResult(
        run_id=run_id,
        profile_id=profile.profile_id,
        display_name=profile.display_name or profile.profile_id,
        jd_id=jd.jd_id,
        jd_version=jd.version,
        weights_hash=weights_hash({d: weights.weight_of(d) for d in DIMENSIONS}),
        taxonomy_version=taxonomy_version(),
        equivalence_version=store.version(),
        match_score=round(total, 2),
        dimension_scores=scores,
        dimension_contributions=contributions,
        skill_fits=fits,
        verdict=verdict,  # type: ignore[arg-type]
        gate_passed=gate_ok,
        analysis_confidence=confidence,
        review_flags=flags,
    )
    result.facts = build_facts(result, profile, jd, weights, reasons, confidence_notes)
    result.explanation = build_explanation(result.facts)
    return result


def run_match(
    profiles: list[ProfileRecord],
    jd: JDConfig,
    weights: WeightConfig,
    store: EquivalenceStore | None = None,
    project_relevance: dict[str, dict[str, float]] | None = None,
    run_id: str | None = None,
) -> RunResult:
    """Score a pool against one JD."""
    store = store or EquivalenceStore()
    run_id = run_id or f"RUN-{uuid.uuid4().hex[:8].upper()}"
    run = RunResult(run_id=run_id, weights=weights)
    relevance = project_relevance or {}

    for profile in profiles:
        if profile.status == "excluded":
            run.excluded.append(
                Exclusion(
                    profile.profile_id, profile.display_name, "Scanned resume — excluded until OCR"
                )
            )
            continue
        keep, reason = stage1_filter(profile, jd, store)
        if not keep:
            run.excluded.append(Exclusion(profile.profile_id, profile.display_name, reason))
            continue
        run.results.append(
            score_profile(
                profile,
                jd,
                weights,
                run_id,
                store,
                relevance.get(profile.profile_id),
            )
        )

    run.results.sort(key=lambda r: -r.match_score)
    return run
