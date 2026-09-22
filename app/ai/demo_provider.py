"""A deterministic, fully offline provider for trying the app without keys.

This is production code, not test scaffolding: the CLI's ``--mock`` flag and
the UI's "Use fixture responses" checkbox both need it, and neither should
depend on the ``tests/`` tree being present in a shipped install.

**What this is and is not.** It is a rule-based stand-in that genuinely reads
its input: the JD analyzer scans the JD text against the skill taxonomy and
tags the signals section 8.3 asks for, and the resume parser infers depth from
action verbs and ownership from pronouns. That makes the ``--mock`` path work
across arbitrary JDs and resumes, which is what allows the scoring engine to
be exercised at scale offline.

It is *not* a substitute for the Phase 0 depth-agreement spike against a real
model (project.md 22.2). A real LLM reads meaning; this reads keywords. Its
value is determinism — the same input always produces the same tags, so a
scoring regression cannot hide behind model variance.

``tests/fixtures/mock_responses.py`` re-exports this module so existing test
imports keep working unchanged.

The underlying MockProvider raises on any schema it has not been given, so a
test can never silently fall through to a live model.
"""

from __future__ import annotations

import re

from app.ai.provider import MockProvider
from app.schemas.evidence import ProjectSkill
from app.schemas.jd import JDAnalysis, SkillSignal
from app.services.profile_analyzer import ParsedProjectSkills
from app.services.skill_engine import _taxonomy, find_skills

# -- shared vocabulary ------------------------------------------------------

TEAM_VOICE = re.compile(r"\b(we|our|the team|was involved in|were involved in|assisted)\b", re.I)

#: Action verbs → the depth they evidence (project.md 7.6 ladder).
DEPTH_VERBS: list[tuple[int, tuple[str, ...]]] = [
    (
        5,
        (
            "led",
            "owned",
            "architected",
            "mentored",
            "reviewed",
            "defined the",
            "set the standard",
            "headed",
        ),
    ),
    (
        4,
        (
            "tuned",
            "optimised",
            "optimized",
            "profiled",
            "scaled",
            "designed",
            "refactored",
            "hardened",
            "benchmarked",
            "cut ",
            "reduced",
        ),
    ),
    (
        3,
        (
            "built",
            "developed",
            "implemented",
            "created",
            "migrated",
            "delivered",
            "integrated",
            "automated",
            "wrote",
            "shipped",
        ),
    ),
    (
        2,
        (
            "used",
            "ran",
            "supported",
            "maintained",
            "configured",
            "executed",
            "assisted",
            "helped",
            "investigated",
            "triaged",
        ),
    ),
]

PRODUCTION_WORDS = (
    "production",
    "live",
    "users",
    "customers",
    "deployed",
    "prod ",
    "went live",
    "daily",
    "subscribers",
)
SUPPORT_WORDS = ("support", "ticket", "triage", "incident", "l1", "l2", "helpdesk")
TEST_WORDS = ("test case", "testing", "qa ", "regression suite", "automation suite")

STRONG_WORDS = (
    "must",
    "required",
    "strong",
    "expert",
    "advanced",
    "extensive",
    "deep",
    "solid",
    "proven",
)
OPTIONAL_WORDS = (
    "nice to have",
    "nice-to-have",
    "plus",
    "preferred",
    "exposure",
    "good to have",
    "desirable",
    "bonus",
    "advantage",
)

SENIORITY_WORDS = {
    "lead": ("lead", "principal", "staff", "architect", "head of"),
    "senior": ("senior", "sr.", "sr "),
    "junior": ("junior", "jr.", "jr ", "graduate", "entry level", "fresher"),
}

#: Taxonomy skill group → the role family a JD dominated by it implies.
GROUP_TO_FAMILY = {
    "frontend": "frontend_dev",
    "backend_java": "backend_dev",
    "backend_python": "backend_dev",
    "backend_node": "backend_dev",
    "backend_jvm": "backend_dev",
    "data": "data_engineer",
    "data_engineering": "data_engineer",
    "devops": "devops",
    "cloud": "devops",
    "qa": "qa",
}

BULLET = re.compile(r"^\s*(?:[-•*▪·]|\d+[.)])\s+")
YEARS_RANGE = re.compile(r"(\d{1,2})\s*(?:to|-|–|—)\s*(\d{1,2})\s*\+?\s*years", re.I)
YEARS_MIN = re.compile(r"(\d{1,2})\s*\+\s*(?:years|yrs)", re.I)
SKILL_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:years|yrs)", re.I)


def _alias_index() -> dict[str, str]:
    """Every known name and synonym, lowercased, → canonical skill."""
    index: dict[str, str] = {}
    for skill, meta in (_taxonomy().get("skills") or {}).items():
        index[skill.lower()] = skill
        for synonym in (meta or {}).get("synonyms", []) or []:
            index[synonym.lower()] = skill
    return index


def _skills_in(text: str) -> dict[str, int]:
    """Delegates to the shared taxonomy matcher in skill_engine."""
    return find_skills(text)


def _depth_from(text: str) -> int:
    lowered = text.lower()
    for depth, verbs in DEPTH_VERBS:
        if any(verb in lowered for verb in verbs):
            return depth
    return 1


def _seniority_from(text: str) -> str:
    lowered = text.lower()
    for band, words in SENIORITY_WORDS.items():
        if any(word in lowered for word in words):
            return band
    return "mid"


# -- JD analysis ------------------------------------------------------------


def _analyze_jd(prompt: str) -> JDAnalysis:
    """Read an arbitrary JD and tag the signals project.md 8.3 asks for.

    Only tags what is observable. Focus scores, tiers, importance and
    confidence are all computed downstream in ``app/scoring`` — this must not
    rank or prioritise anything itself (project.md 2.3).
    """
    body = prompt.split("JOB DESCRIPTION:")[-1].split("---")[1] if "---" in prompt else prompt
    lines = [line.rstrip() for line in body.splitlines()]
    non_empty = [line for line in lines if line.strip()]
    title = non_empty[0].strip() if non_empty else ""
    opening = " ".join(non_empty[1:4])

    bullets = [line.strip() for line in lines if BULLET.match(line)]
    bullet_bodies = [BULLET.sub("", b) for b in bullets]

    # Responsibility bullets are those under a responsibilities-style heading,
    # falling back to every bullet when the JD has no such heading.
    responsibilities: list[str] = []
    in_resp = False
    for line in lines:
        stripped = line.strip()
        low = stripped.lower()
        if re.match(r"^(responsibilities|what you.ll do|the role|you will)\b", low):
            in_resp = True
            continue
        if re.match(
            r"^(requirements|qualifications|skills|what we.re looking|must have|nice)\b", low
        ):
            in_resp = False
            continue
        if in_resp and BULLET.match(line):
            responsibilities.append(BULLET.sub("", stripped))
    if not responsibilities:
        responsibilities = bullet_bodies

    delivery_verbs = (
        "build",
        "develop",
        "ship",
        "deliver",
        "implement",
        "design",
        "create",
        "migrate",
        "optimis",
        "optimiz",
        "maintain",
    )
    delivery_bullets = sum(
        1 for r in responsibilities if any(v in r.lower() for v in delivery_verbs)
    )

    counts = _skills_in(body)
    signals: list[SkillSignal] = []
    for skill, total in counts.items():
        aliases = [a for a, c in _alias_index().items() if c == skill]

        def mentions_skill(text: str, aliases: list[str] = aliases) -> bool:
            low = text.lower()
            return any(re.search(rf"(?<![\w.]){re.escape(a)}(?![\w.])", low) for a in aliases)

        in_resp_bullets = sum(1 for r in responsibilities if mentions_skill(r))
        skill_lines = [line for line in non_empty if mentions_skill(line)]
        context = " ".join(skill_lines).lower()

        strong = any(word in context for word in STRONG_WORDS)
        optional = any(word in context for word in OPTIONAL_WORDS)
        # "5+ years of X" on the same line is the strongest years signal.
        required_years: float | None = None
        for line in skill_lines:
            match = SKILL_YEARS.search(line)
            if match and not YEARS_RANGE.search(line):
                required_years = float(match.group(1))
                break

        signals.append(
            SkillSignal(
                skill=skill,
                in_title=mentions_skill(title),
                in_opening=mentions_skill(opening),
                responsibility_bullets=in_resp_bullets,
                extra_mentions=max(
                    0, total - in_resp_bullets - (1 if mentions_skill(title) else 0)
                ),
                strong_language=strong and not optional,
                optional_language=optional,
                required_years=required_years,
                depth_words=[w for _, verbs in DEPTH_VERBS for w in verbs if w in context][:4],
            )
        )

    # Years band for the role overall.
    years_min = years_max = None
    range_match = YEARS_RANGE.search(body)
    if range_match:
        years_min, years_max = float(range_match.group(1)), float(range_match.group(2))
    else:
        overall = [
            float(m.group(1))
            for line in non_empty
            if (m := YEARS_MIN.search(line)) and not _skills_in(line)
        ]
        if overall:
            years_min = min(overall)

    certifications = []
    for line in non_empty:
        if re.search(r"certifi", line, re.I):
            level = "preferred" if any(w in line.lower() for w in OPTIONAL_WORDS) else "required"
            name = re.sub(r"^[-•*▪·\s]+", "", line)
            name = re.split(r"\s*[-–—(]\s*(?:required|preferred|nice)", name, flags=re.I)[0]
            for word in OPTIONAL_WORDS + STRONG_WORDS:
                name = re.sub(rf"\b{re.escape(word)}\b", "", name, flags=re.I)
            certifications.append({"name": name.strip(" .,:;"), "level": level})

    education = [
        re.sub(r"^[-•*▪·\s]+", "", line)
        for line in non_empty
        if re.search(r"\b(b\.?tech|b\.?e\.?|bachelor|master|m\.?tech|mca|degree)\b", line, re.I)
    ]

    domain = None
    domain_required = False
    for name in _taxonomy().get("domains") or {}:
        if re.search(rf"\b{re.escape(name)}\b", body, re.I):
            domain = name
            domain_required = bool(
                re.search(
                    rf"{re.escape(name)}[^.\n]*\b(experience|domain)\b[^.\n]*"
                    rf"\b(required|must|essential)\b",
                    body,
                    re.I,
                )
                or re.search(
                    rf"\b(required|must have|essential)\b[^.\n]*{re.escape(name)}", body, re.I
                )
            )
            break

    # Role family follows whichever skill group dominates the mentions.
    group_weight: dict[str, int] = {}
    for skill, total in counts.items():
        group = ((_taxonomy().get("skills") or {}).get(skill) or {}).get("group")
        if group:
            group_weight[group] = group_weight.get(group, 0) + total
    top_group = max(group_weight, key=lambda g: group_weight[g]) if group_weight else ""
    role_family = GROUP_TO_FAMILY.get(top_group, "backend_dev")

    return JDAnalysis(
        job_title=title,
        role_intent=(responsibilities[0] if responsibilities else title),
        role_family=role_family,
        seniority=_seniority_from(title) if title else _seniority_from(body),
        domain=domain,
        domain_required=domain_required,
        responsibilities=responsibilities,
        delivery_bullets=delivery_bullets,
        years_min=years_min,
        years_max=years_max,
        certifications=certifications,
        education_requirements=education,
        skill_signals=signals,
    )


# -- resume project parsing -------------------------------------------------


def _parse_block(prompt: str) -> ParsedProjectSkills:
    """Tag one project block: which skills, used how deeply, by whom."""
    body = prompt.split("PROJECT TEXT:")[-1]
    lines = [line.strip() for line in body.splitlines() if line.strip()]

    # Real resumes often declare the stack once and then describe the work
    # without repeating technology names: "Tech stack: React, Redux" followed
    # by "Built a component library used by 4 apps". A real model attributes
    # that bullet to React; a keyword matcher would drop the evidence
    # entirely and leave the skill looking stack-line-only. Unnamed work
    # bullets are therefore attributed to the project's declared stack —
    # capped at L3 and medium quality, because inferred attribution should
    # never manufacture the L4/L5 evidence only an explicit claim earns.
    stack_pattern = re.compile(
        r"^(tech(nology)?\s*stack|technologies|environment|tools)\s*[:\-]", re.I
    )
    stack_line = next((line for line in lines if stack_pattern.match(line)), "")
    stack_skills = list(_skills_in(stack_line)) if stack_line else []
    INFERRED_DEPTH_CAP = 3

    skills: list[ProjectSkill] = []
    seen: set[str] = set()

    for line in lines:
        stripped = BULLET.sub("", line).strip()
        if len(stripped) < 12:
            continue
        lowered = stripped.lower()
        # The tech-stack line is handled by profile_analyzer, which marks those
        # skills stack_line_only; tagging them here too would double count.
        if stack_pattern.match(stripped):
            continue

        found = _skills_in(stripped)
        inferred = False
        team_voice = bool(TEAM_VOICE.search(stripped))
        depth = _depth_from(stripped)

        if not found:
            if not stack_skills or depth < INFERRED_DEPTH_CAP:
                continue
            found = dict.fromkeys(stack_skills, 1)
            inferred = True
            depth = min(depth, INFERRED_DEPTH_CAP)
        production = "yes" if any(w in lowered for w in PRODUCTION_WORDS) else "unknown"
        if any(w in lowered for w in SUPPORT_WORDS):
            context = "support"
        elif any(w in lowered for w in TEST_WORDS):
            context = "test"
        else:
            context = "dev"

        # Team phrasing costs ownership and a depth level — the writing-style
        # confound project.md 20.5 names, reproduced here deliberately so the
        # style-invariance test has something real to measure.
        # Team phrasing costs ownership (project.md 10.2) and drops the
        # evidence-quality tier, which in turn caps depth via
        # QUALITY_DEPTH_CAP. Subtracting a depth level here as well would
        # penalise the same phrasing three times over and overstate the
        # writing-style confound section 20.5 describes.
        ownership = "team" if team_voice else "self"

        if depth >= 5:
            quality = "very_strong"
        elif depth == 4:
            quality = "very_strong" if production == "yes" else "strong"
        elif depth == 3:
            quality = "strong" if production == "yes" else "medium"
        else:
            quality = "medium"
        if team_voice and quality in ("strong", "very_strong"):
            quality = "medium"
        if inferred:
            quality = "medium"

        for skill in found:
            key = f"{skill}:{stripped[:40]}"
            if key in seen:
                continue
            seen.add(key)
            skills.append(
                ProjectSkill(
                    skill=skill,
                    raw_name=skill,
                    action=stripped[:60],
                    depth=depth,
                    ownership=ownership,
                    production=production,
                    usage_context=context,
                    evidence_quality=quality,
                    quote=stripped,
                    implied=inferred,
                )
            )

    # Role family from whichever group this project's skills sit in.
    group_weight: dict[str, int] = {}
    for skill in {s.skill for s in skills}:
        group = ((_taxonomy().get("skills") or {}).get(skill) or {}).get("group")
        if group:
            group_weight[group] = group_weight.get(group, 0) + 1
    top_group = max(group_weight, key=lambda g: group_weight[g]) if group_weight else ""
    family = GROUP_TO_FAMILY.get(top_group, "backend_dev")

    domain = None
    for name in _taxonomy().get("domains") or {}:
        if re.search(rf"\b{re.escape(name)}\b", body, re.I):
            domain = name
            break
    if domain is None:
        for name, token in [
            ("BFSI", "bank"),
            ("Insurance", "insurance"),
            ("Telecom", "telecom"),
            ("Ecommerce", "ecommerce"),
            ("Healthcare", "health"),
            ("Retail", "retail"),
        ]:
            if token in body.lower():
                domain = name
                break

    return ParsedProjectSkills(skills=skills, role_family=family, domain=domain)


def build_mock_provider() -> MockProvider:
    provider = MockProvider()
    provider.register(JDAnalysis, _analyze_jd)
    provider.register(ParsedProjectSkills, _parse_block)
    return provider


#: Kept for the existing fixture-based tests that import it by name.
REACT_JD = None
RULES: list = []
