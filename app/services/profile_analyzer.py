"""Ingestion — project.md section 7.

Parse once, score many: everything expensive happens here, and re-uploading an
unchanged file costs zero LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from app.ai.provider import AIProvider, CallRecord
from app.schemas.evidence import ProfileRecord, Project, ProjectSkill
from app.services import document_parser, evidence_engine, pii_masker, sectioner
from app.services.skill_engine import family_of, implied_skills, normalise

PROMPT_VERSION = "profile_parser_v1"


class ParsedProjectSkills(BaseModel):
    """What the Profile Parser Agent returns for one project block."""

    skills: list[ProjectSkill] = []
    role: str | None = None
    domain: str | None = None
    role_family: str | None = None


@dataclass
class IngestResult:
    profile: ProfileRecord
    pii_map: dict[str, str]
    calls: list[CallRecord] = field(default_factory=list)
    dropped_quotes: int = 0
    skipped: bool = False


def build_parser_prompt(project_text: str, title: str) -> str:
    from app.ai.prompts import load_prompt

    return load_prompt("profile_parser").format(title=title, project_text=project_text)


def ingest_file(
    path: Path | str,
    provider: AIProvider,
    model: str = "mock/fixture",
    known_hashes: dict[str, str] | None = None,
    real_data: bool = False,
    today: date | None = None,
) -> IngestResult:
    """One resume → a scored-ready profile."""
    today = today or date.today()
    path = Path(path)
    document = document_parser.extract(path)

    known_hashes = known_hashes or {}
    if document.file_hash in known_hashes:
        return IngestResult(
            profile=ProfileRecord(
                profile_id=known_hashes[document.file_hash],
                file_name=document.file_name,
                file_hash=document.file_hash,
                status="unchanged",
            ),
            pii_map={},
            skipped=True,
        )

    masked = pii_masker.mask(document.text)
    sections = sectioner.split_sections(masked.text)

    profile_id = f"C-{document.file_hash[:6].upper()}"
    parse_issues: list[str] = list(document.issues or [])
    if document.looks_scanned:
        parse_issues.append("Too little text extracted")

    skills_listed = [normalise(s) for s in sectioner.split_skills(sections.get("skills", ""))]
    skills_listed = [s for s in skills_listed if s]

    project_text = "\n\n".join(
        part for part in (sections.get("projects", ""), sections.get("experience", "")) if part
    )
    blocks = sectioner.split_projects(project_text)
    if not blocks and not parse_issues:
        parse_issues.append("No project or experience blocks detected")

    projects: list[Project] = []
    calls: list[CallRecord] = []
    for index, block in enumerate(blocks):
        prompt = build_parser_prompt(block.text, block.title)
        try:
            parsed, record = provider.extract(
                ParsedProjectSkills,
                prompt,
                model=model,
                prompt_version=PROMPT_VERSION,
                real_data=real_data,
            )
            calls.append(record)
        except Exception as exc:  # noqa: BLE001 - a bad block must not sink the resume
            parse_issues.append(f"Parser failed on '{block.title}': {exc}")
            continue

        tagged = _post_process(parsed.skills, block)
        projects.append(
            Project(
                project_id=f"{profile_id}-P{index + 1}",
                title=block.title,
                domain=parsed.domain,
                role=parsed.role,
                role_family=parsed.role_family,
                start=block.start,
                end=block.end,
                dates_approx=block.dates_approx,
                text=block.text,
                skills=tagged,
            )
        )

    # Newest first, so "latest two projects" and lane detection are meaningful.
    projects.sort(key=lambda p: (p.end is None, p.start or date.min), reverse=True)
    projects, dropped = evidence_engine.drop_unverified(projects)

    cards = evidence_engine.build_evidence_cards(projects, skills_listed=skills_listed, today=today)

    profile = ProfileRecord(
        profile_id=profile_id,
        file_name=document.file_name,
        file_hash=document.file_hash,
        display_name=masked.display_name or profile_id,
        education=[sections.get("education", "")] if sections.get("education") else [],
        domains=[p.domain for p in projects if p.domain],
        projects=projects,
        evidence_cards=cards,
        certifications=evidence_engine.normalise_certifications(
            _certification_lines(sections.get("certifications", "")), today
        ),
        skills_listed=skills_listed,
        parse_issues=parse_issues,
        status="excluded" if document.looks_scanned else "parsed",
    )
    profile.total_experience_years = evidence_engine.merge_ranges(
        [span for p in projects if (span := evidence_engine.project_span(p, today))]
    )
    profile.role_family = next((p.role_family for p in projects if p.role_family), None)
    profile.seniority = _seniority_from(profile.total_experience_years)
    profile.claimed_skill_years = _claimed_years(masked.text)
    profile.red_flags = evidence_engine.detect_red_flags(profile, cards, today)
    profile.lane, profile.lane_skill = evidence_engine.detect_lane(profile, cards)

    return IngestResult(
        profile=profile, pii_map=masked.pii_map, calls=calls, dropped_quotes=dropped
    )


def _post_process(skills: list[ProjectSkill], block: sectioner.ProjectBlock) -> list[ProjectSkill]:
    """Normalise names, mark stack-line-only skills, and add implied skills."""
    out: list[ProjectSkill] = []
    seen: set[str] = set()
    stack_skills = (
        {normalise(s.strip()) for s in block.tech_line.split(",") if s.strip()}
        if block.tech_line
        else set()
    )
    bullet_text = "\n".join(block.bullets)

    for skill in skills:
        canonical = normalise(skill.skill)
        if not canonical or canonical.lower() in seen:
            continue
        seen.add(canonical.lower())
        # Stack-line-only means the evidence IS the tech-stack line — not that
        # the bullet happens to omit the skill's name. "Built a component
        # library" is React evidence even though it never says "React".
        quote_is_from_a_bullet = bool(skill.quote) and skill.quote.strip() in bullet_text
        updated = skill.model_copy(
            update={
                "skill": canonical,
                "raw_name": skill.raw_name or skill.skill,
                "stack_line_only": skill.stack_line_only and not quote_is_from_a_bullet,
            }
        )
        out.append(updated)

    # Skills named only in the tech-stack line: real, but weak evidence (L2).
    for canonical in sorted(stack_skills):
        if not canonical or canonical.lower() in seen:
            continue
        seen.add(canonical.lower())
        out.append(
            ProjectSkill(
                skill=canonical,
                raw_name=canonical,
                action="listed in the tech stack",
                depth=2,
                ownership="vague",
                production="unknown",
                usage_context="dev",
                evidence_quality="weak_plus",
                quote=block.tech_line,
                stack_line_only=True,
            )
        )

    # Implied skills: "wrote stored procedures" demonstrates SQL.
    for bullet in block.bullets:
        for implied in implied_skills(bullet):
            if implied.lower() in seen:
                continue
            seen.add(implied.lower())
            out.append(
                ProjectSkill(
                    skill=implied,
                    raw_name=implied,
                    action="implied by the work described",
                    depth=3,
                    ownership="self",
                    production="unknown",
                    usage_context="dev",
                    evidence_quality="medium",
                    quote=bullet,
                    implied=True,
                )
            )
    return out


def _certification_lines(text: str) -> list[dict]:
    import re

    out: list[dict] = []
    for line in text.splitlines():
        cleaned = line.strip().strip("-•*▪· ")
        if len(cleaned) < 4:
            continue
        year = re.search(r"(19|20)\d{2}", cleaned)
        out.append(
            {
                "name": re.sub(r"[,(\-]?\s*(19|20)\d{2}\)?", "", cleaned).strip(),
                "year": int(year.group(0)) if year else None,
            }
        )
    return out


def _claimed_years(text: str) -> dict[str, float]:
    """'5 years of React' — what the resume asserts, to compare against evidence."""
    import re

    out: dict[str, float] = {}
    pattern = re.compile(
        r"(\d{1,2}(?:\.\d)?)\+?\s*(?:\+)?\s*(?:years?|yrs?)(?:\s+of)?\s+(?:experience\s+in\s+|hands[- ]on\s+)?([A-Za-z][\w.+# ]{1,25})",
        re.I,
    )
    for match in pattern.finditer(text):
        skill = normalise(match.group(2).strip())
        if family_of(skill):
            out[skill] = max(out.get(skill, 0.0), float(match.group(1)))
    return out


def _seniority_from(years: float | None) -> str:
    if years is None:
        return "mid"
    if years < 2:
        return "junior"
    if years < 5:
        return "mid"
    if years < 9:
        return "senior"
    return "lead"
