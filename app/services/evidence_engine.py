"""Tagged mentions → evidence cards, years, flags and lane — project.md 7.3 to 7.7.

Everything here is computed in code, never asked of the LLM: hands-on years are
merged date ranges, depth is capped by evidence quality, and duplicate bullets
are counted once.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from rapidfuzz import fuzz

from app.schemas.enums import QUALITY_DEPTH_CAP, QUALITY_ORDER
from app.schemas.evidence import (
    Certification,
    EvidenceCard,
    EvidenceQuote,
    ManualEvidence,
    ProfileRecord,
    Project,
    ProjectSkill,
)

DUPLICATE_THRESHOLD = 95
QUOTE_MATCH_THRESHOLD = 90
MIN_QUOTE_LENGTH = 25
CLAIM_GAP_YEARS = 2.0
PADDING_MIN_SKILLS = 15
PADDING_PROVEN_RATIO = 0.4
STALE_YEARS = 4
COPY_PASTE_MIN = 3


# -- dates -----------------------------------------------------------------


def merge_ranges(ranges: Iterable[tuple[date, date]]) -> float:
    """Total years covered by a set of ranges, overlaps counted once.

    A candidate with six years of career and 3.5 years of React uses 3.5 —
    skill years are not career years (project.md 7.4).
    """
    spans = sorted((start, end) for start, end in ranges if start and end and end >= start)
    if not spans:
        return 0.0
    merged: list[list[date]] = [[spans[0][0], spans[0][1]]]
    for start, end in spans[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    days = sum((end - start).days for start, end in merged)
    return round(days / 365.25, 2)


def project_span(project: Project, today: date | None = None) -> tuple[date, date] | None:
    if project.start is None:
        return None
    return project.start, project.end or (today or date.today())


# -- evidence cards --------------------------------------------------------


def _dedupe_quotes(skills: list[ProjectSkill]) -> list[ProjectSkill]:
    """Near-identical bullets across projects count once (project.md 7.4)."""
    kept: list[ProjectSkill] = []
    for skill in skills:
        if not skill.quote:
            kept.append(skill)
            continue
        if any(
            other.quote and fuzz.ratio(skill.quote, other.quote) >= DUPLICATE_THRESHOLD
            for other in kept
        ):
            continue
        kept.append(skill)
    return kept


def _best_quality(qualities: Iterable[str]) -> str:
    ordered = [q for q in qualities if q in QUALITY_ORDER]
    if not ordered:
        return "weak"
    return max(ordered, key=QUALITY_ORDER.index)


def build_evidence_cards(
    projects: list[Project],
    skills_listed: list[str] | None = None,
    summary_skills: list[str] | None = None,
    today: date | None = None,
) -> dict[str, EvidenceCard]:
    """One card per skill, from every project that used it."""
    today = today or date.today()
    skills_listed = skills_listed or []
    summary_skills = summary_skills or []
    listed_lower = {s.lower() for s in skills_listed}

    by_skill: dict[str, list[tuple[Project, ProjectSkill]]] = {}
    for project in projects:
        for skill in project.skills:
            by_skill.setdefault(skill.skill, []).append((project, skill))

    cards: dict[str, EvidenceCard] = {}
    for skill_name, entries in by_skill.items():
        mentions = _dedupe_quotes([s for _, s in entries])
        project_ids = {p.project_id for p, _ in entries}
        spans = [span for p, _ in entries if (span := project_span(p, today))]
        hands_on = merge_ranges(spans) if spans else None

        ends = [p.end for p, _ in entries if p.start is not None]
        is_current = any(p.end is None for p, _ in entries if p.start is not None)
        real_ends = [e for e in ends if e is not None]
        last_used = max(real_ends) if real_ends else None
        if is_current:
            years_since: float | None = 0.0
        elif last_used is not None:
            years_since = round((today - last_used).days / 365.25, 2)
        else:
            years_since = None

        quality = _best_quality(s.evidence_quality for s in mentions)
        stack_only = all(s.stack_line_only for s in mentions) if mentions else False
        capped_depth = min(
            max((s.depth for s in mentions), default=1),
            QUALITY_DEPTH_CAP.get(quality, 5),
        )
        if stack_only:
            capped_depth = min(capped_depth, QUALITY_DEPTH_CAP["weak_plus"])

        contexts = {s.usage_context for s in mentions}
        if contexts and contexts <= {"test", "support"}:
            capped_depth = min(capped_depth, QUALITY_DEPTH_CAP["weak_plus"])

        cards[skill_name] = EvidenceCard(
            skill=skill_name,
            mentions={
                "skills_list": 1 if skill_name.lower() in listed_lower else 0,
                "summary": 1 if skill_name in summary_skills else 0,
                "project_lines": len(mentions),
            },
            projects_used=len(project_ids),
            hands_on_years=hands_on,
            last_used=last_used,
            is_current=is_current,
            years_since_last_use=years_since,
            max_depth=max(1, capped_depth),
            best_evidence_quality=quality,  # type: ignore[arg-type]
            production=any(s.production == "yes" for s in mentions),
            ownership="self"
            if any(s.ownership == "self" for s in mentions)
            else ("team" if any(s.ownership == "team" for s in mentions) else "vague"),
            usage_context=sorted(contexts),  # type: ignore[arg-type]
            stack_line_only=stack_only,
            skills_list_only=False,
            evidence=[
                EvidenceQuote(
                    quote=s.quote,
                    project=next(p.title for p, ps in entries if ps is s),
                    quality=s.evidence_quality,
                    source=s.source,
                )
                for s in mentions
                if s.quote
            ],
        )

    # Skills claimed in the list but never used in a project.
    for raw in skills_listed:
        if raw in cards:
            continue
        cards[raw] = EvidenceCard(
            skill=raw,
            mentions={"skills_list": 1, "summary": 0, "project_lines": 0},
            projects_used=0,
            hands_on_years=None,
            max_depth=1,
            best_evidence_quality="weak",
            production=False,
            ownership="vague",
            skills_list_only=True,
            years_since_last_use=None,
        )
    return cards


def merge_manual_evidence(
    cards: dict[str, EvidenceCard], manual: list[ManualEvidence]
) -> dict[str, EvidenceCard]:
    """Fold manager-added evidence in beside the parse — project.md 7.7, D6.

    The parsed record is never mutated: a verified entry is added, and the card
    takes the stronger of the two readings.
    """
    out = {name: card.model_copy(deep=True) for name, card in cards.items()}
    for entry in manual:
        card = out.get(entry.skill)
        if card is None:
            card = EvidenceCard(skill=entry.skill, projects_used=0)
            out[entry.skill] = card
        card.max_depth = max(card.max_depth, entry.depth)
        card.best_evidence_quality = "verified"
        card.skills_list_only = False
        card.stack_line_only = False
        if entry.years is not None:
            card.hands_on_years = max(card.hands_on_years or 0.0, entry.years)
        if entry.ownership == "self":
            card.ownership = "self"
        if entry.production == "yes":
            card.production = True
        if card.years_since_last_use is None:
            card.years_since_last_use = 0.0
        note = entry.note or f"Verified at L{entry.depth}"
        card.evidence.append(
            EvidenceQuote(
                quote=note,
                project=f"Verified by {entry.author or 'a manager'}",
                quality="verified",
                source="manual",
            )
        )
    return out


# -- quote verification ----------------------------------------------------


def verify_quote(quote: str, block_text: str) -> bool:
    """A quote must be findable in the block it came from — project.md 7.1.

    v2.0 checked partial_ratio against the whole document, which false-accepts
    short phrases. Scoping to the block plus a length floor closes that.
    """
    if not quote or len(quote.strip()) < MIN_QUOTE_LENGTH:
        return False
    if not block_text:
        return False
    normalised_quote = " ".join(quote.lower().split())
    normalised_block = " ".join(block_text.lower().split())
    if normalised_quote in normalised_block:
        return True
    return fuzz.token_set_ratio(normalised_quote, normalised_block) >= QUOTE_MATCH_THRESHOLD


def drop_unverified(projects: list[Project]) -> tuple[list[Project], int]:
    """Invented evidence scores zero — project.md 2.6."""
    dropped = 0
    out: list[Project] = []
    for project in projects:
        kept: list[ProjectSkill] = []
        for skill in project.skills:
            if skill.source == "manual" or not skill.quote:
                kept.append(skill)
                continue
            if verify_quote(skill.quote, project.text):
                kept.append(skill)
            else:
                dropped += 1
        out.append(project.model_copy(update={"skills": kept}))
    return out, dropped


# -- red flags -------------------------------------------------------------


def detect_red_flags(
    profile: ProfileRecord, cards: dict[str, EvidenceCard], today: date | None = None
) -> list[str]:
    today = today or date.today()
    flags: list[str] = []

    for skill, claimed in (profile.claimed_skill_years or {}).items():
        card = cards.get(skill)
        proven = (card.hands_on_years if card else None) or 0.0
        if claimed - proven >= CLAIM_GAP_YEARS:
            flags.append(
                f"Claim vs evidence — {skill}: claim {claimed:g} yrs, evidence ~{proven:g} yrs. "
                "Verification recommended."
            )

    listed = profile.skills_listed or []
    if len(listed) >= PADDING_MIN_SKILLS:
        proven = sum(1 for s in listed if (card := cards.get(s)) and card.projects_used > 0)
        if proven / max(1, len(listed)) < PADDING_PROVEN_RATIO:
            flags.append(f"Padding — {len(listed)} skills listed, {proven} shown in projects.")

    for skill, card in cards.items():
        if card.stack_line_only and card.projects_used:
            flags.append(f"Stack-line only — {skill} appears only in tech-stack lines.")
        if card.usage_context and set(card.usage_context) <= {"test", "support"}:
            flags.append(f"Wrong context — {skill} used only in test or support work.")
        if (
            not card.is_current
            and card.years_since_last_use is not None
            and card.years_since_last_use > STALE_YEARS
        ):
            flags.append(
                f"Stale — {skill} last used about {card.years_since_last_use:.0f} years ago."
            )

    undated = [p.title for p in profile.projects if p.start is None]
    if undated:
        flags.append(f"Undated — no dates on: {', '.join(undated[:3])}.")

    for a in profile.projects:
        if a.start and a.end and a.end < a.start:
            flags.append(f"Date conflict — {a.title} ends before it starts.")

    quotes = [s.quote for p in profile.projects for s in p.skills if s.quote]
    duplicates = 0
    for i, quote in enumerate(quotes):
        for other in quotes[i + 1 :]:
            if fuzz.ratio(quote, other) >= DUPLICATE_THRESHOLD:
                duplicates += 1
    if duplicates >= COPY_PASTE_MIN:
        flags.append(
            f"Copy-paste — {duplicates} near-identical bullets across projects, counted once."
        )

    return flags


def detect_lane(
    profile: ProfileRecord, cards: dict[str, EvidenceCard]
) -> tuple[str | None, str | None]:
    """Strongest evidence across the latest two projects — project.md 7.1 step 10."""
    recent = profile.projects[:2]
    if not recent:
        return None, None
    scores: dict[str, float] = {}
    for project in recent:
        for skill in project.skills:
            card = cards.get(skill.skill)
            weight = skill.depth + (1 if skill.production == "yes" else 0)
            if card and card.projects_used >= 2:
                weight += 1
            scores[skill.skill] = scores.get(skill.skill, 0) + weight
    if not scores:
        return None, None
    lane_skill = max(scores, key=lambda k: (scores[k], k))
    from app.services.skill_engine import family_of

    return family_of(lane_skill), lane_skill


def normalise_certifications(raw: list[dict], today: date | None = None) -> list[Certification]:
    from app.config import load_yaml

    today = today or date.today()
    catalogue = load_yaml("certifications.yaml").get("certifications") or {}
    index: dict[str, str] = {}
    for name, meta in catalogue.items():
        index[name.lower()] = name
        for synonym in (meta or {}).get("synonyms", []) or []:
            index[synonym.lower()] = name

    out: list[Certification] = []
    for entry in raw:
        raw_name = (entry.get("name") or "").strip()
        canonical = index.get(raw_name.lower(), raw_name)
        meta = catalogue.get(canonical) or {}
        year = entry.get("year")
        status = "unknown"
        validity = meta.get("validity_years")
        if year and validity:
            status = "expired" if today.year - int(year) > int(validity) else "active"
        elif year:
            status = "active"
        out.append(
            Certification(
                name=canonical,
                issuer=entry.get("issuer") or meta.get("issuer"),
                year=int(year) if year else None,
                status=status,
            )
        )
    return out
