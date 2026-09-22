"""Facts → explanations — project.md section 13.

Code builds a facts dictionary; every section below is a template filled from
it. Only the short summary may come from a model, and it is validated against
the same facts before it is shown.
"""

from __future__ import annotations

import re

from app.schemas.enums import DIMENSION_LABELS, FORBIDDEN_PHRASES
from app.schemas.evidence import ProfileRecord
from app.schemas.jd import JDConfig
from app.schemas.result import Explanation, MatchResult, WeightConfig

PROMPT_VERSION = "reason_writer_v1"


def build_facts(
    result: MatchResult,
    profile: ProfileRecord,
    jd: JDConfig,
    weights: WeightConfig,
    verdict_reasons: list[str],
    confidence_notes: list[str],
) -> dict:
    """Everything an explanation may refer to. Nothing outside this is allowed."""
    effective = __import__(
        "app.scoring.dimensions", fromlist=["effective_weights"]
    ).effective_weights(result.dimension_scores, weights)

    return {
        "profile_id": profile.profile_id,
        "display_name": profile.display_name or profile.profile_id,
        "job_title": jd.job_title,
        "jd_primary": [p.skill for p in jd.primaries],
        "candidate_primary": profile.lane_skill,
        "lane": _lane_label(profile, jd),
        "match_score": result.match_score,
        "verdict": result.verdict,
        "gate_passed": result.gate_passed,
        "gate_threshold": round(weights.gate_threshold * 100, 1),
        "deployable_threshold": round(weights.deployable_threshold * 100, 1),
        "analysis_confidence": result.analysis_confidence,
        "confidence_notes": confidence_notes,
        "verdict_reasons": verdict_reasons,
        "dimensions": [
            {
                "name": name,
                "label": DIMENSION_LABELS.get(name, name),
                "weight": effective.get(name, 0.0),
                "score": score,
                "contribution": result.dimension_contributions.get(name, 0.0),
            }
            for name, score in result.dimension_scores.items()
            if score is not None and effective.get(name, 0) > 0
        ],
        "na_dimensions": [
            DIMENSION_LABELS.get(n, n)
            for n, s in result.dimension_scores.items()
            if s is None and weights.weight_of(n) > 0
        ],
        "skills": [
            {
                "skill": f.skill,
                "tier": f.tier,
                "importance": f.importance,
                "needs": f"L{f.required_depth}·{f.required_years:g}y",
                "found": f"L{f.shown_depth}·{f.hands_on_years:g}y"
                if f.hands_on_years is not None
                else f"L{f.shown_depth}·years unknown",
                "projects": f.projects_used,
                "last_used": f.last_used_label,
                "fit": f.fit_pct,
                "relation": f.relation,
                "matched_skill": f.matched_skill,
                "scored": f.scored,
                "evidence": f.evidence,
                "gap": f.gap_note,
            }
            for f in result.skill_fits
        ],
        "red_flags": profile.red_flags,
        "parse_issues": profile.parse_issues,
        "review_flags": result.review_flags,
    }


def _lane_label(profile: ProfileRecord, jd: JDConfig) -> str:
    primaries = {p.skill.lower() for p in jd.primaries}
    if profile.lane_skill and profile.lane_skill.lower() in primaries:
        return "Same"
    if profile.role_family and jd.role_family:
        return "Same" if profile.role_family == jd.role_family else "Adjacent"
    return "Unknown"


def why_not_higher(facts: dict) -> list[dict]:
    """Lost points per dimension = weight x (1 - score), largest first."""
    rows: list[dict] = []
    for entry in facts["dimensions"]:
        lost = entry["weight"] * (1 - entry["score"] / 100)
        if lost <= 0.05:
            continue
        rows.append(
            {
                "dimension": entry["label"],
                "lost": round(lost, 2),
                "detail": _dimension_gap(facts, entry["name"]),
            }
        )
    rows.sort(key=lambda r: -r["lost"])
    return rows


def _dimension_gap(facts: dict, dimension: str) -> str:
    tier = {
        "primary_skill": "primary",
        "core_skills": "core",
        "secondary_skills": "secondary",
    }.get(dimension)
    if not tier:
        return ""
    gaps = [
        f"{s['skill']}: {s['gap'].replace('Partial evidence: ', '')}"
        for s in facts["skills"]
        if s["tier"] == tier and s["scored"] and s["fit"] < 100
    ]
    return "; ".join(gaps[:3])


def path_to_deployable(facts: dict) -> list[str]:
    """Missing evidence, closest gaps first. Never a time estimate."""
    steps: list[str] = []
    if not facts["gate_passed"]:
        for skill in facts["skills"]:
            if skill["tier"] != "primary" or skill["fit"] >= facts["gate_threshold"]:
                continue
            if skill["relation"] in ("related", "equivalent"):
                steps.append(
                    f"Direct {skill['skill']} project evidence — credit through "
                    f"{skill['matched_skill']} is capped below the gate"
                )
            elif skill["fit"] == 0:
                steps.append(f"Any {skill['skill']} project evidence")
            else:
                steps.append(f"{skill['skill']}: {skill['gap']}")
        steps.append(
            f"Gate status: not met — the primary skill must reach {facts['gate_threshold']:g}%."
        )
        return steps

    shortfall = facts["deployable_threshold"] - facts["match_score"]
    if shortfall > 0:
        steps.append(
            f"{shortfall:.1f} points needed to reach the "
            f"{facts['deployable_threshold']:g}% deployable threshold"
        )
    for row in why_not_higher(facts)[:3]:
        if row["detail"]:
            steps.append(f"{row['dimension']} (+{row['lost']:.1f} available) — {row['detail']}")
    for reason in facts["verdict_reasons"]:
        steps.append(reason)
    return steps


def requires_verification(facts: dict) -> list[str]:
    """Interview questions aimed at the weakest or least certain claims."""
    items: list[str] = []
    for skill in facts["skills"]:
        if not skill["scored"] or skill["fit"] == 0:
            continue
        for quote in skill["evidence"]:
            if any(token in quote for token in ("%", "x faster", "reduced", "cut ")):
                items.append(f'specifics behind "{quote}"')
                break
        if 0 < skill["fit"] < 70 and skill["tier"] in ("primary", "core"):
            items.append(f"a {skill['skill']} walkthrough — evidence is partial")
    for flag in facts["red_flags"]:
        if flag.startswith("Claim vs evidence"):
            items.append(
                flag.replace("Claim vs evidence — ", "").replace(" Verification recommended.", "")
            )
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out[:5]


def template_summary(facts: dict) -> str:
    """The fallback summary, and the reference the model output is judged against."""
    parts: list[str] = []
    primaries = [s for s in facts["skills"] if s["tier"] == "primary"]
    for skill in primaries:
        if skill["fit"] >= 80:
            parts.append(
                f"Evidence found of {skill['skill']} at L{skill['found'].split('·')[0][1:]} "
                f"across {skill['projects']} project(s), last used {skill['last_used']}."
            )
        elif skill["fit"] > 0:
            parts.append(
                f"Partial evidence of {skill['skill']}: {skill['gap'].replace('Partial evidence: ', '')}."
            )
        else:
            parts.append(f"No evidence found of {skill['skill']}.")
    core_ok = [s for s in facts["skills"] if s["tier"] == "core" and s["scored"] and s["fit"] >= 80]
    core_partial = [
        s for s in facts["skills"] if s["tier"] == "core" and s["scored"] and 0 < s["fit"] < 80
    ]
    if core_ok:
        parts.append(f"{', '.join(s['skill'] for s in core_ok[:3])} evidence is strong.")
    if core_partial:
        parts.append(f"{', '.join(s['skill'] for s in core_partial[:3])} evidence is partial.")
    return " ".join(parts)


def validate_summary(summary: str, facts: dict) -> tuple[bool, str]:
    """Reject invented skills, invented numbers and forbidden wording."""
    lowered = summary.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lowered:
            return False, f"forbidden phrasing: {phrase!r}"

    # Multi-word skill names have to contribute their individual words, not
    # just the full name: the token scan below sees "Azure", "Data" and
    # "Factory" separately, so checking only against "azure data factory"
    # rejects a perfectly grounded summary as invented. That silently
    # discarded the model's summary for every multi-word skill — Azure Data
    # Factory, Spring Boot, AWS Glue, Delta Lake — and fell back to the
    # template without saying why.
    known: set[str] = set()

    def allow(value: str | None) -> None:
        if not value:
            return
        lowered = value.lower()
        known.add(lowered)
        known.update(lowered.split())

    for entry in facts["skills"]:
        allow(entry["skill"])
        # The skill a requirement was actually matched through. Related and
        # equivalent credit (section 10.1) names it in the gap text, so the
        # engine's own template summary says "related technology (Angular)"
        # — and without this the validator rejected that summary as
        # hallucinated, discarding it for every candidate matched through a
        # neighbouring technology.
        allow(entry.get("matched_skill"))
    allow(facts.get("candidate_primary"))
    for name in facts.get("jd_primary") or []:
        allow(name)

    for token in re.findall(r"\b[A-Z][A-Za-z.+#]{2,}\b", summary):
        if token.lower() in {
            "evidence",
            "partial",
            "requires",
            "verification",
            "no",
            "the",
            "this",
            "project",
            "projects",
            "found",
            "production",
            "level",
        }:
            continue
        if token.lower() not in known:
            return False, f"skill not in facts: {token}"

    numbers = set(re.findall(r"\d+(?:\.\d+)?", summary))
    allowed = {str(facts["match_score"]), str(int(facts["match_score"]))}
    for skill in facts["skills"]:
        allowed |= {str(skill["projects"]), str(skill["fit"]), str(int(skill["fit"]))}
        # The gap note is itself generated from these facts, so any number it
        # contains is grounded — including differently rounded renderings of
        # the same value.
        allowed |= set(
            re.findall(
                r"\d+(?:\.\d+)?",
                skill["found"] + skill["needs"] + skill["gap"] + skill["last_used"],
            )
        )
    for number in numbers:
        if number not in allowed:
            return False, f"number not in facts: {number}"
    return True, ""


def score_reason(facts: dict) -> str:
    """Why this score, in one line, for display beside the number.

    A ranked list is unreadable if the only way to learn why someone scored
    60% rather than 88% is to open their detail page. Two halves, each
    carrying information the other does not: how the primary skill did, which
    is what the gate turns on, and which *other* dimensions cost the most.

    The primary dimension is deliberately excluded from the gaps half. Listing
    it in both reads as self-contradictory — "Primary skill 94% ... lost most
    to Primary skill" — and its shortfall is already implied by the fit
    percentage stated first.
    """
    primaries = [s for s in facts["skills"] if s["tier"] == "primary"]
    gate = facts["gate_threshold"]

    # A failed gate is the whole story; nothing below it changes the outcome.
    if not facts["gate_passed"] and primaries:
        missing = [s for s in primaries if s["fit"] == 0]
        if missing:
            names = ", ".join(s["skill"] for s in missing)
            held = [s for s in primaries if s["fit"] > 0]
            if held:
                # A dual-primary role where one half is proven and the other
                # absent. Saying the score came from "other dimensions alone"
                # would be plainly wrong when they hold one of the primaries.
                have = ", ".join(f"{s['skill']} {s['fit']:.0f}%" for s in held)
                return f"No {names} evidence; has {have} — this role needs both"
            return (
                f"No {names} evidence — {facts['match_score']:.1f}% comes from the "
                "other dimensions alone"
            )
        weakest = min(primaries, key=lambda s: s["fit"])
        via = ""
        if weakest["relation"] in ("related", "equivalent"):
            via = f" (via {weakest['matched_skill']})"
        return f"{weakest['skill']} {weakest['fit']}%{via} is under the {gate:g}% gate"

    parts: list[str] = []
    if primaries:
        parts.append(
            ", ".join(
                f"{s['skill']} {s['fit']:.0f}%"
                + (
                    f" (via {s['matched_skill']})"
                    if s["relation"] in ("related", "equivalent")
                    else ""
                )
                for s in primaries
            )
        )
    else:
        ranked = sorted(facts["dimensions"], key=lambda d: -d["contribution"])
        if ranked:
            parts.append(f"{ranked[0]['label']} {ranked[0]['score']:.0f}%")

    gaps = [row for row in why_not_higher(facts) if row["dimension"] != "Primary skill"][:2]
    if gaps:
        parts.append(
            "biggest gaps: "
            + ", ".join(f"{row['dimension']} \u2212{row['lost']:.1f}" for row in gaps)
        )

    return " · ".join(parts) or "No scored dimensions"


def build_explanation(facts: dict, summary: str | None = None) -> Explanation:
    """Assemble the explanation, falling back to the template when needed."""
    source = "template"
    text = template_summary(facts)
    if summary:
        ok, _reason = validate_summary(summary, facts)
        if ok:
            text, source = summary, "llm"

    return Explanation(
        summary=text,
        summary_source=source,
        score_reason=score_reason(facts),
        why_not_higher=why_not_higher(facts),
        path_to_deployable=path_to_deployable(facts),
        requires_verification=requires_verification(facts),
        strengths=[
            f"{s['skill']} — {s['fit']}%" for s in facts["skills"] if s["scored"] and s["fit"] >= 80
        ][:4],
    )
