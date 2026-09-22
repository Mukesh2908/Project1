"""Deterministic generator for a large JD/resume corpus.

Hand-written fixtures are the anchor: they encode specific risks from
project.md 24 and are worth reading. This generator exists for the other job —
scale. It produces a corpus large enough that every JD has a real pool to rank,
which is what surfaces defects that only appear across JD variety.

Everything is seeded, so the corpus is identical on every run: a failure is
reproducible from the seed alone rather than "sometimes fails".

The variation axes are deliberate, not decorative. Uniform generated data
gives false confidence — it exercises one path many times. Each profile varies
in voice (direct vs team), date completeness, production evidence, depth verbs,
claim honesty and padding, so the corpus spreads across the branches that
actually matter to scoring.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

# -- lanes ------------------------------------------------------------------


@dataclass(frozen=True)
class Lane:
    key: str
    primary: str
    core: tuple[str, ...]
    secondary: tuple[str, ...]
    domain: str
    role: str
    projects: tuple[str, ...]
    verbs: tuple[str, ...] = ("Built", "Developed", "Designed", "Tuned", "Led")


LANES: tuple[Lane, ...] = (
    Lane(
        "react",
        "React",
        ("TypeScript", "Redux"),
        ("SQL", "JavaScript"),
        "BFSI",
        "Frontend Engineer",
        ("Retail Banking Portal", "Wealth Dashboard", "Onboarding Journey"),
    ),
    Lane(
        "angular",
        "Angular",
        ("TypeScript", "RxJS"),
        ("SQL",),
        "Telecom",
        "Frontend Engineer",
        ("Self-Care Portal", "Billing Console", "Partner Portal"),
    ),
    Lane(
        "java",
        "Java",
        ("Spring Boot", "SQL"),
        ("Kafka", "Docker"),
        "Fintech",
        "Backend Engineer",
        ("Payments Platform", "Order Management", "Ledger Service"),
    ),
    Lane(
        "python",
        "Python",
        ("Django", "SQL"),
        ("FastAPI", "Docker"),
        "Retail",
        "Backend Engineer",
        ("Logistics Platform", "Pricing Service", "Internal Tools"),
    ),
    Lane(
        "node",
        "Node.js",
        ("Express", "MongoDB"),
        ("React", "TypeScript"),
        "Ecommerce",
        "Backend Engineer",
        ("Commerce API", "Checkout Service", "Catalogue Service"),
    ),
    Lane(
        "data",
        "Databricks",
        ("PySpark", "Azure Data Factory"),
        ("SQL", "Airflow"),
        "Insurance",
        "Data Engineer",
        ("Claims Data Platform", "Policy Lakehouse", "Actuarial Pipeline"),
    ),
    Lane(
        "data_aws",
        "AWS Glue",
        ("PySpark", "SQL"),
        ("Airflow", "AWS"),
        "Retail",
        "Data Engineer",
        ("Analytics Lake", "Inventory Pipeline", "Customer 360"),
    ),
    Lane(
        "devops",
        "Kubernetes",
        ("Terraform", "Docker"),
        ("Jenkins", "AWS"),
        "Telecom",
        "DevOps Engineer",
        ("Delivery Platform", "Cluster Migration", "CI Modernisation"),
    ),
    Lane(
        "qa",
        "Selenium",
        ("Cypress", "SQL"),
        ("Java",),
        "Healthcare",
        "QA Engineer",
        ("Regression Suite", "Patient Journey QA", "Release Automation"),
    ),
    Lane(
        "cloud",
        "AWS",
        ("Terraform", "Kubernetes"),
        ("Docker",),
        "Manufacturing",
        "Cloud Engineer",
        ("Cloud Migration", "Landing Zone", "Platform Rebuild"),
    ),
)

SENIORITY = (
    ("junior", 1.5, ("Developed", "Used", "Wrote")),
    ("mid", 4.0, ("Built", "Developed", "Integrated")),
    ("senior", 7.0, ("Built", "Tuned", "Optimized", "Designed")),
    ("lead", 11.0, ("Led", "Architected", "Designed", "Mentored")),
)

FIRST = (
    "Priya",
    "Arjun",
    "Meena",
    "Rohit",
    "Kavita",
    "Vikram",
    "Ananya",
    "Farhan",
    "Lakshmi",
    "Suresh",
    "Tara",
    "Imran",
    "Deepak",
    "Neha",
    "Ravi",
    "Sneha",
    "Gopal",
    "Anil",
    "Farida",
    "Nikhil",
    "Ramesh",
    "Sandeep",
    "Arun",
    "Mohan",
)
LAST = (
    "Raghavan",
    "Nair",
    "Iyer",
    "Sharma",
    "Deshpande",
    "Chatterjee",
    "Sheikh",
    "Narayanan",
    "Babu",
    "Qureshi",
    "Menon",
    "Bhatt",
    "Shankar",
    "Pillai",
    "Verma",
    "Kumar",
    "Hussain",
    "Rao",
    "Gopalan",
    "Kulkarni",
    "Mehta",
    "Das",
)

PADDING_SKILLS = (
    "Vue",
    "Scala",
    "MongoDB",
    "Jenkins",
    "Terraform",
    "Kafka",
    "Hibernate",
    "Airflow",
    "PostgreSQL",
    "Azure",
    "GCP",
    "Cypress",
    "Selenium",
)


@dataclass
class GeneratedProfile:
    name: str
    lane: str
    text: str
    seniority: str
    traits: list[str] = field(default_factory=list)


def _person(rng: random.Random, used: set[str]) -> str:
    for _ in range(200):
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        if name not in used:
            used.add(name)
            return name
    return f"Person {len(used)}"


def generate_profile(
    lane: Lane, index: int, rng: random.Random, used: set[str]
) -> GeneratedProfile:
    """One resume, with its variation axes chosen from the seeded rng."""
    name = _person(rng, used)
    band, years, verbs = SENIORITY[index % len(SENIORITY)]
    traits: list[str] = [band]

    team_voice = index % 5 == 0
    undated = index % 7 == 3
    no_production = index % 4 == 1
    inflated = index % 9 == 4
    padded = index % 6 == 2
    stack_only_core = index % 8 == 5

    if team_voice:
        traits.append("team-voice")
    if undated:
        traits.append("undated")
    if no_production:
        traits.append("no-production")
    if inflated:
        traits.append("inflated-claim")
    if padded:
        traits.append("padded")
    if stack_only_core:
        traits.append("stack-line-only-core")

    claimed = years + 4 if inflated else years
    listed = [lane.primary, *lane.core, *lane.secondary]
    if padded:
        listed += list(rng.sample(PADDING_SKILLS, 8))

    lines = [
        name,
        f"{name.split()[0].lower()}.{index}@example.com",
        "",
        "PROFESSIONAL SUMMARY",
        f"{lane.role} with {claimed:g} years of {lane.primary} experience in {lane.domain}.",
        "",
        "TECHNICAL SKILLS",
        ", ".join(dict.fromkeys(listed)),
        "",
        "PROJECTS",
    ]

    project_count = 1 if band == "junior" else 2
    end_year = 2026
    for p in range(project_count):
        title = lane.projects[(index + p) % len(lane.projects)]
        span = max(1, int(years / project_count))
        start_year = end_year - span
        lines.append(f"Project {p + 1}: {title}")
        if not undated:
            if p == 0:
                lines.append(f"Jan {start_year} - Present")
            else:
                lines.append(f"Feb {start_year - span} - Dec {start_year - 1}")
        stack = (
            [lane.primary, *lane.core]
            if not stack_only_core
            else [lane.primary, *lane.core, *lane.secondary]
        )
        lines.append(f"Tech stack: {', '.join(stack)}")

        verb = verbs[p % len(verbs)]
        prod = " in production" if not no_production else ""
        subject = "We" if team_voice else ""

        def bullet(text: str, subject: str = subject) -> str:
            return f"- {('We ' + text[0].lower() + text[1:]) if subject else text}"

        skill_for_bullets = lane.primary if not stack_only_core else lane.core[0]
        lines.append(bullet(f"{verb} {skill_for_bullets} components for the {title.lower()}{prod}"))
        if band in ("senior", "lead"):
            lines.append(bullet(f"Tuned {skill_for_bullets} performance and cut runtime 40%{prod}"))
        if band == "lead":
            lines.append(bullet(f"Led the {skill_for_bullets} architecture and mentored engineers"))
        for core in lane.core[:2]:
            if stack_only_core and core == lane.core[0]:
                continue
            lines.append(bullet(f"Developed {core} integrations for the {title.lower()}"))
        lines.append("")

    lines += ["EDUCATION", "B.Tech, Computer Science"]
    return GeneratedProfile(name, lane.key, "\n".join(lines), band, traits)


def generate_jd(lane: Lane, variant: int) -> tuple[str, str]:
    """One JD. Variant 0 is senior and strict; variant 1 is mid and looser."""
    senior = variant == 0
    band = "Senior" if senior else ""
    years_min = 5 if senior else 3
    years_max = 9 if senior else 6
    title = f"{band} {lane.role}".strip()

    lines = [
        title,
        "",
        f"We are hiring a {title} for a {lane.domain} client.",
        "",
        "Responsibilities:",
        f"- Build and ship {lane.primary} features for the platform",
        f"- Design {lane.core[0]} integrations across services",
        f"- Optimize {lane.primary} performance",
        f"- Maintain {lane.core[-1]} components",
        "",
        "Requirements:",
        f"- {years_min}+ years of strong {lane.primary} experience, must have",
        f"- Strong {lane.core[0]} required",
    ]
    if senior:
        lines.append(f"- {lane.core[-1]} required")
    else:
        lines.append(f"- {lane.core[-1]} is nice to have")
    if lane.secondary:
        lines.append(f"- {lane.secondary[0]} exposure is a plus")
    lines.append(f"- {years_min} to {years_max} years of total experience")
    return f"jd_{lane.key}_{'senior' if senior else 'mid'}", "\n".join(lines)


def build_corpus(
    profiles_per_lane: int = 12, seed: int = 20260922
) -> tuple[dict[str, str], list[GeneratedProfile]]:
    """Returns ({jd_name: jd_text}, [profiles]) — deterministic for a seed."""
    rng = random.Random(seed)
    used: set[str] = set()

    jds: dict[str, str] = {}
    for lane in LANES:
        for variant in (0, 1):
            name, text = generate_jd(lane, variant)
            jds[name] = text

    profiles: list[GeneratedProfile] = []
    for lane in LANES:
        for index in range(profiles_per_lane):
            profiles.append(generate_profile(lane, index, rng, used))
    return jds, profiles
