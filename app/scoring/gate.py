"""Main-skill gate and verdicts — project.md section 12.1.

The dual-primary question v2.0 left open — must a candidate prove both primary
skills, or either? — is now an explicit per-JD choice (decision D5), defaulting
to ``all`` so the strict reading applies unless someone deliberately relaxes it.
"""

from app.schemas.evidence import ProfileRecord
from app.schemas.jd import JDConfig
from app.schemas.result import SkillFit, WeightConfig


def primary_fits(fits: list[SkillFit]) -> list[SkillFit]:
    return [f for f in fits if f.tier == "primary"]


def gate_passed(
    fits: list[SkillFit], weights: WeightConfig, mode: str = "all"
) -> tuple[bool, list[str]]:
    """Whether the candidate clears the main-skill gate, and which primaries failed."""
    if not weights.gate_enabled:
        return True, []
    primaries = primary_fits(fits)
    if not primaries:
        return True, []
    failed = [f.skill for f in primaries if f.fit < weights.gate_threshold]
    if mode == "any":
        return len(failed) < len(primaries), failed
    return not failed, failed


def mandatory_met(
    fits: list[SkillFit],
    profile: ProfileRecord,
    jd: JDConfig,
    weights: WeightConfig,
    excused: set[str] | None = None,
) -> tuple[bool, list[str]]:
    """Mandatory = fit at or above the gate, cert held, minimum years met.

    ``excused`` names primary skills the dual-primary mode has already let
    through. Without it, ``mode="any"`` would be inert: the gate would pass on
    one primary and the other would immediately block the verdict again, so no
    candidate could ever reach Deployable Now on an either/or JD.
    """
    excused = excused or set()
    unmet: list[str] = []
    for fit in fits:
        if fit.importance != "mandatory":
            continue
        if fit.tier == "primary" and fit.skill in excused:
            continue
        if fit.fit < weights.gate_threshold:
            unmet.append(
                f"{fit.skill}: {fit.fit_pct}% below the {int(weights.gate_threshold * 100)}% bar"
            )
            continue
        # Only a floor the user set explicitly gates here. The JD's inferred
        # required_years is already inside the fit score.
        if (
            fit.min_years is not None
            and fit.hands_on_years is not None
            and fit.hands_on_years < fit.min_years
        ):
            unmet.append(
                f"{fit.skill}: {fit.hands_on_years:.1f} yrs vs a {fit.min_years:g} yr minimum"
            )
    held = {c.name.lower() for c in profile.certifications}
    for req in jd.certification_requirements:
        if req.importance in ("mandatory", "important") and req.skill.lower() not in held:
            unmet.append(f"{req.skill}: not held")
    return not unmet, unmet


def best_primary_or_close(fits: list[SkillFit]) -> float:
    primaries = primary_fits(fits)
    if not primaries:
        return 0.0
    return max(f.fit for f in primaries)


def decide_verdict(
    fits: list[SkillFit],
    profile: ProfileRecord,
    jd: JDConfig,
    weights: WeightConfig,
    match_score: float,
) -> tuple[str, bool, list[str]]:
    """Returns (verdict, gate_passed, reasons)."""
    mode = jd.dual_primary_mode
    passed, failed_primaries = gate_passed(fits, weights, mode)
    reasons: list[str] = []

    if passed:
        # In "any" mode the user has accepted that one primary may be missing,
        # so a primary the gate excused must not block through mandatory checks.
        excused = set(failed_primaries) if mode == "any" else set()
        met, unmet = mandatory_met(fits, profile, jd, weights, excused)
        if met and match_score >= weights.deployable_threshold * 100:
            return "deployable_now", True, reasons
        if not met:
            reasons.extend(unmet)
        else:
            reasons.append(
                f"Match score {match_score:.1f}% is below the "
                f"{weights.deployable_threshold * 100:.0f}% deployable threshold"
            )
        return "needs_ramp_up", True, reasons

    if failed_primaries:
        reasons.append(
            "Gate not met on: "
            + ", ".join(failed_primaries)
            + (" (this JD requires evidence of every primary skill)" if mode == "all" else "")
        )
    best = best_primary_or_close(fits)
    if best >= weights.trainable_threshold:
        return "trainable", False, reasons
    return "not_a_fit", False, reasons


def borderline_flags(match_score: float, fits: list[SkillFit], weights: WeightConfig) -> list[str]:
    """Scores sitting within the band of a threshold go to human review."""
    flags: list[str] = []
    band = weights.borderline_band
    deployable = weights.deployable_threshold * 100
    if abs(match_score - deployable) <= band:
        flags.append(
            f"Borderline: {match_score:.1f}% is within {band:g} points of the "
            f"{deployable:.0f}% deployable threshold"
        )
    gate = weights.gate_threshold * 100
    for fit in primary_fits(fits):
        if abs(fit.fit_pct - gate) <= band:
            flags.append(
                f"Borderline: {fit.skill} at {fit.fit_pct}% is within {band:g} points "
                f"of the {gate:.0f}% gate"
            )
    return flags
