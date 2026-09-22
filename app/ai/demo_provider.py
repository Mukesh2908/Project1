"""A deterministic, fully offline provider for trying the app without keys.

This is production code, not test scaffolding: the CLI's ``--mock`` flag and
the UI's "Use fixture responses" checkbox both need it, and neither should
depend on the ``tests/`` tree being present in a shipped install. The rules
below are hand-written against the bundled fixtures in ``tests/fixtures`` —
they are a demo of the pipeline's shape, not a substitute for the Phase 0
depth-agreement spike against a real model (project.md 22.2).

``tests/fixtures/mock_responses.py`` re-exports this module so the existing
test suite's imports keep working unchanged.

The underlying MockProvider raises on any schema it has not been given, so a
test can never silently fall through to a live model.
"""

from __future__ import annotations

import re

from app.ai.provider import MockProvider
from app.schemas.evidence import ProjectSkill
from app.schemas.jd import JDAnalysis, SkillSignal
from app.services.profile_analyzer import ParsedProjectSkills

REACT_JD = JDAnalysis(
    job_title="Senior Software Engineer — React",
    role_intent="Build customer-facing React web apps for a banking client",
    role_family="frontend_dev",
    seniority="senior",
    domain="BFSI",
    domain_required=False,
    responsibilities=[
        "Build and ship React components for customer-facing banking journeys",
        "Optimize front-end performance across the portfolio",
        "Migrate legacy JavaScript screens to TypeScript",
        "Work with Redux for application state management",
    ],
    delivery_bullets=4,
    years_min=4,
    years_max=7,
    certifications=[{"name": "AWS Certified Developer", "level": "preferred"}],
    education_requirements=[],
    skill_signals=[
        SkillSignal(
            skill="React",
            in_title=True,
            in_opening=True,
            responsibility_bullets=4,
            extra_mentions=5,
            strong_language=True,
            required_years=4,
            depth_words=["build", "optimize"],
        ),
        SkillSignal(
            skill="TypeScript",
            responsibility_bullets=2,
            strong_language=True,
            depth_words=["strong"],
        ),
        SkillSignal(skill="Redux", responsibility_bullets=1, depth_words=["hands-on"]),
        SkillSignal(
            skill="Next.js", extra_mentions=1, optional_language=True, depth_words=["exposure"]
        ),
        SkillSignal(skill="Angular"),
        SkillSignal(skill="Python"),
        SkillSignal(skill="Java"),
        SkillSignal(skill="Scala"),
        SkillSignal(skill="SQL", depth_words=["basic"]),
    ],
)

#: Phrase -> (skill, depth, ownership, production, quality)
RULES: list[tuple[str, tuple[str, int, str, str, str]]] = [
    ("component library", ("React", 4, "self", "yes", "strong")),
    ("cut page load", ("React", 4, "self", "yes", "very_strong")),
    ("owned the design of the state", ("React", 5, "self", "yes", "very_strong")),
    ("migrating 120 components", ("TypeScript", 3, "self", "yes", "strong")),
    ("migrated 120 components", ("TypeScript", 3, "self", "yes", "strong")),
    ("dashboard screens", ("React", 3, "self", "yes", "medium")),
    ("redux for cart state", ("Redux", 2, "self", "unknown", "medium")),
    ("redux state design", ("Redux", 2, "team", "unknown", "medium")),
    ("state management layer", ("Redux", 3, "self", "yes", "strong")),
    ("self-care portal", ("Angular", 4, "self", "yes", "very_strong")),
    ("component architecture", ("Angular", 5, "self", "yes", "very_strong")),
    ("change detection", ("Angular", 4, "self", "yes", "very_strong")),
    ("admin console", ("Angular", 3, "self", "unknown", "medium")),
    ("payment processing microservices", ("Java", 4, "self", "yes", "very_strong")),
    ("reconciliation service", ("Java", 5, "self", "yes", "very_strong")),
    ("order management apis", ("Java", 4, "self", "yes", "strong")),
    ("tuned sql queries", ("SQL", 4, "self", "yes", "very_strong")),
    ("data check queries", ("SQL", 2, "self", "unknown", "medium")),
    ("production support tickets", ("React", 2, "self", "unknown", "medium")),
    ("supported the reporting platform", ("SQL", 2, "self", "unknown", "medium")),
]

TEAM_VOICE = re.compile(r"\b(we|the team|was involved in|were involved in)\b", re.I)


def _parse_block(prompt: str) -> ParsedProjectSkills:
    """Tag the fixture block the way a careful parser would."""
    body = prompt.split("PROJECT TEXT:")[-1]
    skills: list[ProjectSkill] = []
    seen: set[str] = set()

    for line in body.splitlines():
        stripped = line.strip().lstrip("-•* ").strip()
        if len(stripped) < 15:
            continue
        lowered = stripped.lower()
        for phrase, (skill, depth, ownership, production, quality) in RULES:
            if phrase not in lowered:
                continue
            # Team phrasing downgrades ownership, which is exactly the confound
            # the style-invariance test measures.
            if TEAM_VOICE.search(stripped):
                ownership = "team"
                quality = "medium" if quality in ("strong", "very_strong") else quality
                depth = max(1, depth - 1)
            key = f"{skill}:{stripped[:30]}"
            if key in seen:
                continue
            seen.add(key)
            skills.append(
                ProjectSkill(
                    skill=skill,
                    raw_name=skill,
                    action=phrase,
                    depth=depth,
                    ownership=ownership,
                    production=production,
                    usage_context="support" if "support" in lowered else "dev",
                    evidence_quality=quality,
                    quote=stripped,
                )
            )

    family = "frontend_dev"
    if any(s.skill == "Java" for s in skills):
        family = "backend_dev"
    domain = None
    for name, token in [
        ("BFSI", "bank"),
        ("Insurance", "insurance"),
        ("Telecom", "telecom"),
        ("Ecommerce", "ecommerce"),
    ]:
        if token in body.lower():
            domain = name
            break
    return ParsedProjectSkills(skills=skills, role_family=family, domain=domain)


def build_mock_provider() -> MockProvider:
    provider = MockProvider()
    provider.register(JDAnalysis, REACT_JD)
    provider.register(ParsedProjectSkills, _parse_block)
    return provider
