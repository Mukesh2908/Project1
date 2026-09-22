"""Candidate-side models — project.md sections 7 and 18.1."""

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.enums import (
    EvidenceQuality,
    EvidenceSource,
    Ownership,
    Production,
    UsageContext,
)


class ProjectSkill(BaseModel):
    """One skill as used in one project, as tagged by the Profile Parser."""

    skill: str
    raw_name: str = ""
    action: str = ""
    depth: int = Field(ge=1, le=5)
    ownership: Ownership = "vague"
    production: Production = "unknown"
    usage_context: UsageContext = "dev"
    evidence_quality: EvidenceQuality = "medium"
    quote: str = ""
    stack_line_only: bool = False
    implied: bool = False
    source: EvidenceSource = "parsed"


class Project(BaseModel):
    project_id: str
    title: str
    domain: str | None = None
    role: str | None = None
    role_family: str | None = None
    start: date | None = None
    end: date | None = None  # None means present
    dates_approx: bool = False
    text: str = ""
    skills: list[ProjectSkill] = Field(default_factory=list)


class EvidenceQuote(BaseModel):
    quote: str
    project: str
    quality: EvidenceQuality
    source: EvidenceSource = "parsed"


class EvidenceCard(BaseModel):
    """Everything known about one skill for one candidate — project.md 7.3."""

    skill: str
    mentions: dict[str, int] = Field(default_factory=dict)
    projects_used: int = 0
    hands_on_years: float | None = None  # None → part dropped, see scoring/skill_proof
    claimed_years: float | None = None
    last_used: date | None = None
    is_current: bool = False
    years_since_last_use: float | None = None
    max_depth: int = 1
    best_evidence_quality: EvidenceQuality = "weak"
    production: bool = False
    ownership: Ownership = "vague"
    usage_context: list[UsageContext] = Field(default_factory=list)
    stack_line_only: bool = False
    skills_list_only: bool = False
    evidence: list[EvidenceQuote] = Field(default_factory=list)

    @property
    def has_verified(self) -> bool:
        return any(e.source == "manual" for e in self.evidence)


class ManualEvidence(BaseModel):
    """Manager-added verified evidence — project.md 7.7, decision D6.

    Never mutates the parsed record; it is merged as an additional entry.
    """

    profile_id: str
    skill: str
    depth: int = Field(ge=1, le=5)
    years: float | None = None
    ownership: Ownership = "self"
    production: Production = "unknown"
    note: str = ""
    author: str = ""
    created_at: str = ""


class Certification(BaseModel):
    name: str
    issuer: str | None = None
    year: int | None = None
    status: str = "active"  # active | expired | unknown


class ProfileRecord(BaseModel):
    """A parsed candidate."""

    profile_id: str
    file_name: str = ""
    file_hash: str = ""
    display_name: str = ""
    lane: str | None = None
    lane_skill: str | None = None
    total_experience_years: float | None = None
    role_family: str | None = None
    seniority: str | None = None
    education: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    evidence_cards: dict[str, EvidenceCard] = Field(default_factory=dict)
    certifications: list[Certification] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    parse_issues: list[str] = Field(default_factory=list)
    claimed_skill_years: dict[str, float] = Field(default_factory=dict)
    skills_listed: list[str] = Field(default_factory=list)
    status: str = "parsed"
