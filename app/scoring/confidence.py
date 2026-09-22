"""Analysis confidence and human-review triggers — project.md 12.2 and 12.3.

Match Score and Analysis Confidence are deliberately separate numbers: two
candidates can both score 86%, one of them on solid dated evidence and one on a
single undated line.
"""

from app.schemas.evidence import ProfileRecord
from app.schemas.jd import JDConfig
from app.schemas.result import SkillFit


def candidate_confidence(profile: ProfileRecord, fits: list[SkillFit]) -> tuple[int, list[str]]:
    """Start at 100 and deduct for every reason to doubt the reading."""
    score = 100
    notes: list[str] = []

    undated = any("Undated" in flag or "no dates" in flag.lower() for flag in profile.red_flags)
    if undated:
        score -= 25
        notes.append("No dates on one or more projects")

    gaps = [f for f in profile.red_flags if f.startswith("Claim vs evidence")]
    if gaps:
        deduction = min(30, 15 * len(gaps))
        score -= deduction
        notes.append(f"{len(gaps)} claim-vs-evidence gap{'s' if len(gaps) != 1 else ''}")

    primaries = [f for f in fits if f.tier == "primary"]
    for fit in primaries:
        if 0 < len(fit.evidence) <= 1 and fit.fit > 0:
            score -= 15
            notes.append(f"{fit.skill} proven by a single line")
            break

    if any(f.tier == "primary" and f.relation in ("related", "equivalent") for f in primaries):
        score -= 10
        notes.append("Primary skill evidenced only through a related technology")

    if profile.parse_issues:
        score -= 10
        notes.append("Parsing issues on this resume")

    if any(flag.startswith("Padding") for flag in profile.red_flags):
        score -= 10
        notes.append("Skills listed well beyond what the projects show")

    return max(0, min(100, score)), notes


def review_flags(
    profile: ProfileRecord,
    jd: JDConfig,
    fits: list[SkillFit],
    confidence: int,
    borderline: list[str],
) -> list[str]:
    """Everything that should send a result to the human review queue."""
    flags: list[str] = list(borderline)

    if jd.confidence < 60:
        flags.append(f"JD analysis confidence is low ({jd.confidence}%)")
    unresolved = [c for c in jd.conflicts if not c.resolved]
    if unresolved:
        flags.append(f"{len(unresolved)} unresolved JD conflict(s)")

    if confidence < 60:
        flags.append(f"Candidate analysis confidence is low ({confidence}%)")

    for flag in profile.red_flags:
        if flag.startswith(("Claim vs evidence", "Date conflict", "Undated")):
            flags.append(flag)

    if profile.lane and jd.primaries:
        primary_skills = {p.skill.lower() for p in jd.primaries}
        if profile.lane_skill and profile.lane_skill.lower() not in primary_skills:
            if any(f.tier == "primary" and f.fit >= 0.25 for f in fits):
                flags.append(
                    f"Career lane is {profile.lane_skill}, not the JD primary — "
                    "confirm the transition"
                )

    if profile.parse_issues:
        flags.append("Parsing problems: " + "; ".join(profile.parse_issues[:2]))

    seen: set[str] = set()
    deduped: list[str] = []
    for flag in flags:
        if flag not in seen:
            seen.add(flag)
            deduped.append(flag)
    return deduped
