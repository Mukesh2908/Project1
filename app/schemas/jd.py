"""JD-side models — project.md sections 8, 9 and 18.1."""

from pydantic import BaseModel, Field

from app.schemas.enums import Category, DualPrimaryMode, Importance, Seniority, Source, Tier


class SkillSignal(BaseModel):
    """What the LLM tags. Focus scores are computed in code (project.md 8.3)."""

    skill: str
    in_title: bool = False
    in_opening: bool = False
    responsibility_bullets: int = 0
    extra_mentions: int = 0
    strong_language: bool = False
    optional_language: bool = False
    required_years: float | None = None
    depth_words: list[str] = Field(default_factory=list)


class JDAnalysis(BaseModel):
    """Raw JD Analyzer output, before any code-side scoring."""

    job_title: str = ""
    role_intent: str = ""
    role_family: str = ""
    seniority: Seniority = "mid"
    domain: str | None = None
    domain_required: bool = False
    responsibilities: list[str] = Field(default_factory=list)
    delivery_bullets: int = 0
    years_min: float | None = None
    years_max: float | None = None
    certifications: list[dict] = Field(default_factory=list)
    education_requirements: list[str] = Field(default_factory=list)
    skill_signals: list[SkillSignal] = Field(default_factory=list)


class Requirement(BaseModel):
    """One thing the JD asks for.

    ``required_depth`` and ``required_years`` are resolved when the config is
    confirmed (project.md 9.4), so scoring never divides by ``None``.
    """

    skill: str
    category: Category = "skill"
    tier: Tier | None = None
    importance: Importance = "preferred"
    required_depth: int = Field(default=3, ge=1, le=5)
    required_years: float = 3.0
    #: A hard floor the user sets in My Requirements (project.md 9.3). Distinct
    #: from ``required_years``, which is inferred from the JD and already priced
    #: into the fit score; gating on that too would fail a 97.5% candidate over
    #: a half-year shortfall and double-count the same gap.
    min_years: float | None = None
    focus_score: float | None = None
    focus_breakdown: dict[str, float] = Field(default_factory=dict)
    scored: bool = True  # False when beyond the tier cap — project.md 11.4
    family: str | None = None
    source: Source = "ai"
    why: str | None = None
    notes: str | None = None


class Conflict(BaseModel):
    kind: str
    message: str
    suggested_action: str = ""
    resolved: bool = False
    resolution_note: str = ""


class JDConfig(BaseModel):
    """A confirmed, versioned reading of one JD. Every run cites one of these."""

    jd_id: str
    version: int = 1
    job_title: str = ""
    role_intent: str = ""
    role_family: str = ""
    seniority: Seniority = "mid"
    domain: str | None = None
    domain_required: bool = False
    experience_min: float | None = None
    experience_max: float | None = None
    requirements: list[Requirement] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    confidence: int = 0
    delivery_bullets: int = 0
    education_requirements: list[str] = Field(default_factory=list)
    dual_primary_mode: DualPrimaryMode = "all"  # decision D5
    derived_weights: dict[str, int] = Field(default_factory=dict)
    derived_weight_reasons: dict[str, str] = Field(default_factory=dict)

    # -- convenience views -------------------------------------------------
    def by_tier(self, tier: str) -> list[Requirement]:
        return [r for r in self.requirements if r.tier == tier]

    def scored_by_tier(self, tier: str) -> list[Requirement]:
        """Only the requirements that count toward the dimension (project.md 11.4)."""
        return [r for r in self.requirements if r.tier == tier and r.scored]

    @property
    def primaries(self) -> list[Requirement]:
        return self.by_tier("primary")

    @property
    def skill_requirements(self) -> list[Requirement]:
        return [r for r in self.requirements if r.category == "skill"]

    @property
    def certification_requirements(self) -> list[Requirement]:
        return [r for r in self.requirements if r.category == "certification"]

    @property
    def confidence_band(self) -> str:
        if self.confidence >= 80:
            return "High"
        if self.confidence >= 60:
            return "Medium"
        return "Low"
