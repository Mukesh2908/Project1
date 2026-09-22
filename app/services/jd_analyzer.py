"""JD pipeline — project.md section 8.

The LLM tags signals and writes the intent sentence. Focus scores, tiers,
importance, required levels, confidence and conflicts are all computed here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.ai.provider import AIProvider, CallRecord
from app.config import text_hash
from app.schemas.jd import JDAnalysis, JDConfig, Requirement
from app.scoring.conflicts import detect_conflicts
from app.scoring.dimensions import select_scored_requirements
from app.scoring.focus import assign_tiers
from app.scoring.jd_confidence import jd_confidence
from app.scoring.weights import derive_weights
from app.services.skill_engine import family_of, normalise

PROMPT_VERSION = "jd_analyzer_v1"


@dataclass
class JDResult:
    config: JDConfig
    analysis: JDAnalysis
    calls: list[CallRecord] = field(default_factory=list)


def build_prompt(jd_text: str) -> str:
    from app.ai.prompts import load_prompt

    return load_prompt("jd_analyzer").format(jd_text=jd_text)


def analyse(
    jd_text: str,
    provider: AIProvider,
    model: str = "mock/fixture",
    jd_id: str | None = None,
    tier_cap: int = 5,
    primary_floor: int = 35,
    real_data: bool = False,
) -> JDResult:
    """JD text → a scored, versioned config with a suggested weight matrix."""
    jd_id = jd_id or f"JD-{text_hash(jd_text)[:6].upper()}"
    analysis, record = provider.extract(
        JDAnalysis,
        build_prompt(jd_text),
        model=model,
        prompt_version=PROMPT_VERSION,
        real_data=real_data,
    )

    signals = []
    for signal in analysis.skill_signals:
        canonical = normalise(signal.skill)
        if canonical:
            signals.append(signal.model_copy(update={"skill": canonical}))

    families = {s.skill: family_of(s.skill) for s in signals}
    requirements: list[Requirement] = assign_tiers(
        signals,
        {k: v for k, v in families.items() if v},
        analysis.seniority,
        substitutes=_substitutes_of_top(signals),
    )

    for entry in analysis.certifications:
        name = (entry or {}).get("name")
        if not name:
            continue
        level = (entry or {}).get("level", "preferred")
        requirements.append(
            Requirement(
                skill=name,
                category="certification",
                importance="important" if level == "required" else "preferred",
                source="ai",
                why=f"listed as {level}",
            )
        )

    conflicts = detect_conflicts(
        requirements,
        analysis.seniority,
        analysis.years_min,
        analysis.years_max,
        analysis.job_title,
        analysis.responsibilities,
    )

    primaries = [r for r in requirements if r.tier == "primary"]
    top = max(primaries, key=lambda r: r.focus_score or 0) if primaries else None
    top_signal = next((s for s in signals if top and s.skill == top.skill), None)
    confidence, _breakdown = jd_confidence(top, top_signal, conflicts)

    config = JDConfig(
        jd_id=jd_id,
        version=1,
        job_title=analysis.job_title,
        role_intent=analysis.role_intent,
        role_family=analysis.role_family,
        seniority=analysis.seniority,
        domain=analysis.domain,
        domain_required=analysis.domain_required,
        experience_min=analysis.years_min,
        experience_max=analysis.years_max,
        requirements=requirements,
        conflicts=conflicts,
        confidence=confidence,
        delivery_bullets=analysis.delivery_bullets or len(analysis.responsibilities),
        education_requirements=analysis.education_requirements,
        dual_primary_mode="all",
    )
    config = finalise(config, tier_cap, primary_floor)
    return JDResult(config=config, analysis=analysis, calls=[record])


def _substitutes_of_top(signals) -> set[str]:
    """Skills the taxonomy marks as alternatives to the highest-scoring skill."""
    from app.scoring.focus import focus_score
    from app.services.skill_engine import EquivalenceStore

    if not signals:
        return set()
    store = EquivalenceStore()
    scores = {s.skill: focus_score(s)[0] for s in signals}
    top = max(scores, key=lambda k: (scores[k], k))
    return {
        s.skill for s in signals if s.skill != top and store.relation(top, s.skill) == "related"
    }


def finalise(config: JDConfig, tier_cap: int = 5, primary_floor: int = 35) -> JDConfig:
    """Apply the tier cap and derive the weight matrix.

    Run again after any user override, so the cap and the suggested matrix
    always reflect the version that will actually be scored.
    """
    config = select_scored_requirements(config, tier_cap)
    weights, reasons = derive_weights(config, floor=primary_floor)
    config.derived_weights = weights
    config.derived_weight_reasons = reasons
    return config


def similarity(a: str, b: str) -> float:
    """Cheap overlap score for the similar-JD prompt — project.md 8.1."""
    from rapidfuzz import fuzz

    return fuzz.token_set_ratio(a, b) / 100


def config_diff(old: JDConfig, new: JDConfig) -> list[dict]:
    """What differs between two JD configs.

    Shown before reusing a previous JD's overrides: a bare yes/no prompt is how
    a wrong primary skill propagates silently.
    """
    rows: list[dict] = []
    old_map = {r.skill: r for r in old.requirements}
    new_map = {r.skill: r for r in new.requirements}
    for skill in sorted(set(old_map) | set(new_map)):
        before, after = old_map.get(skill), new_map.get(skill)
        if before is None:
            rows.append(
                {
                    "skill": skill,
                    "change": "added",
                    "from": "—",
                    "to": f"{after.tier}/{after.importance}",
                }
            )
        elif after is None:
            rows.append(
                {
                    "skill": skill,
                    "change": "removed",
                    "from": f"{before.tier}/{before.importance}",
                    "to": "—",
                }
            )
        elif (before.tier, before.importance) != (after.tier, after.importance):
            rows.append(
                {
                    "skill": skill,
                    "change": "changed",
                    "from": f"{before.tier}/{before.importance}",
                    "to": f"{after.tier}/{after.importance}",
                }
            )
    if old.seniority != new.seniority:
        rows.append(
            {
                "skill": "(seniority)",
                "change": "changed",
                "from": old.seniority,
                "to": new.seniority,
            }
        )
    if old.domain != new.domain:
        rows.append(
            {
                "skill": "(domain)",
                "change": "changed",
                "from": old.domain or "—",
                "to": new.domain or "—",
            }
        )
    return rows
