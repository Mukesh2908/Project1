"""Contradictions inside a JD — project.md 8.9.

Shown as cards for a human to resolve; unresolved ones lower JD confidence and
mark the run for review.
"""

from app.schemas.jd import Conflict, Requirement


def detect_conflicts(
    requirements: list[Requirement],
    seniority: str,
    experience_min: float | None,
    experience_max: float | None,
    title: str = "",
    responsibilities: list[str] | None = None,
) -> list[Conflict]:
    conflicts: list[Conflict] = []
    responsibilities = responsibilities or []
    skills = [r for r in requirements if r.category == "skill"]
    primaries = [r for r in skills if r.tier == "primary"]

    # Mandatory but barely mentioned.
    for req in skills:
        if req.importance == "mandatory" and req.tier == "secondary":
            conflicts.append(
                Conflict(
                    kind="mandatory_low_focus",
                    message=(
                        f"{req.skill} is marked mandatory but appears only in passing "
                        f"(focus score {req.focus_score:g})."
                    ),
                    suggested_action=f"Confirm {req.skill} as Core rather than Secondary.",
                )
            )

    # Two strong primaries under a single-focus title.
    if len(primaries) > 1 and title:
        named = [p for p in primaries if p.skill.lower() in title.lower()]
        if len(named) < len(primaries):
            missing = ", ".join(p.skill for p in primaries if p not in named)
            conflicts.append(
                Conflict(
                    kind="dual_primary_title",
                    message=(
                        f"The title names {named[0].skill if named else 'one skill'}, but "
                        f"{missing} carries comparable weight in the body."
                    ),
                    suggested_action="Confirm whether this is a dual-primary role or Core.",
                )
            )

    # Years contradiction.
    if experience_max is not None:
        for req in skills:
            if req.required_years > experience_max:
                conflicts.append(
                    Conflict(
                        kind="years_contradiction",
                        message=(
                            f"{req.skill} asks for {req.required_years:g}+ years, but total "
                            f"experience is capped at {experience_max:g}."
                        ),
                        suggested_action="Fix the years requirement.",
                    )
                )

    # Seniority mismatch.
    lead_words = ("lead a team", "mentor", "own the architecture", "manage a team")
    if seniority == "junior" and any(w in " ".join(responsibilities).lower() for w in lead_words):
        conflicts.append(
            Conflict(
                kind="seniority_mismatch",
                message="The title reads junior, but the responsibilities describe leading others.",
                suggested_action="Confirm the seniority band.",
            )
        )

    # Everything mandatory.
    mandatory = [r for r in skills if r.importance == "mandatory"]
    if len(mandatory) > 8:
        conflicts.append(
            Conflict(
                kind="everything_mandatory",
                message=f"{len(mandatory)} skills are marked mandatory.",
                suggested_action="Pick the top 3 that genuinely gate the role.",
            )
        )

    return conflicts
