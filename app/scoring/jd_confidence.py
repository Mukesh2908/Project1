"""How sure the system is about its reading of a JD — project.md 8.8."""

from app.schemas.jd import Conflict, Requirement, SkillSignal


def jd_confidence(
    primary: Requirement | None,
    signal: SkillSignal | None,
    conflicts: list[Conflict],
    intent_consistent: bool = True,
) -> tuple[int, dict[str, int]]:
    breakdown: dict[str, int] = {}
    if primary is None or signal is None:
        return 0, {"No primary skill identified": 0}

    if signal.in_title:
        breakdown["Primary in title"] = 30
    bullets = min(30, 8 * signal.responsibility_bullets)
    if bullets:
        breakdown["Primary in responsibilities"] = bullets

    agreeing = sum(
        [
            bool(signal.in_title),
            bool(signal.in_opening),
            signal.responsibility_bullets > 0,
            signal.required_years is not None,
        ]
    )
    if agreeing:
        breakdown["Independent signals agree"] = min(20, 5 * agreeing)

    if signal.strong_language:
        breakdown["Strong or required language"] = 10
    if intent_consistent:
        breakdown["Title, responsibilities and intent consistent"] = 10

    unresolved = [c for c in conflicts if not c.resolved]
    if unresolved:
        breakdown["Unresolved conflicts"] = -10 * len(unresolved)

    total = max(0, min(100, sum(breakdown.values())))
    return total, breakdown
