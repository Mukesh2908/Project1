"""Scoring output models — project.md sections 11, 12, 13 and 18.1."""

from pydantic import BaseModel, Field

from app.schemas.enums import DIMENSIONS, DualPrimaryMode, Relation, Tier, Verdict


class DimensionWeight(BaseModel):
    enabled: bool = True
    weight: int = 0


class WeightConfig(BaseModel):
    """The scoring matrix plus every tunable in project.md 11.5."""

    dimensions: dict[str, DimensionWeight] = Field(default_factory=dict)
    skill_proof_parts: dict[str, float] = Field(
        default_factory=lambda: {
            "depth": 0.25,
            "years": 0.20,
            "projects": 0.20,
            "recency": 0.15,
            "production": 0.10,
            "ownership": 0.10,
        }
    )
    gate_enabled: bool = True
    gate_threshold: float = 0.60
    trainable_threshold: float = 0.25
    deployable_threshold: float = 0.80
    listed_only_cap: float = 0.10
    borderline_band: float = 3.0
    tier_skill_cap: int = 5
    primary_weight_floor: int = 35
    primary_weight_warn: int = 40
    match_factors: dict[str, float] = Field(
        default_factory=lambda: {"exact": 1.0, "equivalent": 0.8, "related": 0.5}
    )
    importance_multipliers: dict[str, float] = Field(
        default_factory=lambda: {
            "mandatory": 3.0,
            "important": 2.0,
            "preferred": 1.0,
            "optional": 0.5,
        }
    )
    dual_primary_mode: DualPrimaryMode = "all"

    # -- helpers -----------------------------------------------------------
    def weight_of(self, dimension: str) -> int:
        dw = self.dimensions.get(dimension)
        return dw.weight if dw and dw.enabled else 0

    def enabled_dimensions(self) -> list[str]:
        return [d for d in DIMENSIONS if self.weight_of(d) > 0]

    def total(self) -> int:
        return sum(self.weight_of(d) for d in DIMENSIONS)

    def is_valid(self) -> bool:
        return self.total() == 100


class SkillFit(BaseModel):
    """One requirement scored against one candidate — project.md 10.2."""

    skill: str
    tier: Tier | None = None
    importance: str = "preferred"
    required_depth: int = 3
    required_years: float = 3.0
    min_years: float | None = None
    matched_skill: str | None = None
    relation: Relation = "none"
    match_factor: float = 0.0
    fit: float = 0.0  # 0..1
    parts: dict[str, float] = Field(default_factory=dict)
    parts_used: list[str] = Field(default_factory=list)
    shown_depth: int = 0
    hands_on_years: float | None = None
    projects_used: int = 0
    last_used_label: str = "no evidence"
    production: bool = False
    ownership: str = "vague"
    listed_only: bool = False
    capped: bool = False
    scored: bool = True
    evidence: list[str] = Field(default_factory=list)
    gap_note: str = ""

    @property
    def fit_pct(self) -> float:
        return round(self.fit * 100, 1)


class Explanation(BaseModel):
    summary: str = ""
    summary_source: str = "template"  # template | llm
    #: One line saying why this score is what it is — the dimension that
    #: earned the most and the ones that cost the most. Built from the facts,
    #: never by a model, so it can sit beside the number in a list.
    score_reason: str = ""
    why_not_higher: list[dict] = Field(default_factory=list)
    path_to_deployable: list[str] = Field(default_factory=list)
    requires_verification: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)


class MatchResult(BaseModel):
    run_id: str
    profile_id: str
    display_name: str = ""
    jd_id: str = ""
    jd_version: int = 1
    weights_hash: str = ""
    taxonomy_version: str = ""
    equivalence_version: str = ""
    match_score: float = 0.0
    dimension_scores: dict[str, float | None] = Field(default_factory=dict)
    dimension_contributions: dict[str, float] = Field(default_factory=dict)
    skill_fits: list[SkillFit] = Field(default_factory=list)
    verdict: Verdict = "not_a_fit"
    gate_passed: bool = False
    #: Whether the candidate showed any trace of the JD's primary skill. False
    #: means they were scored anyway (every candidate gets a number) but had
    #: no primary-skill evidence at all, so the score reflects the other
    #: dimensions only.
    prefilter_passed: bool = True
    prefilter_note: str = ""
    analysis_confidence: int = 100
    review_flags: list[str] = Field(default_factory=list)
    facts: dict = Field(default_factory=dict)
    explanation: Explanation = Field(default_factory=Explanation)

    @property
    def needs_review(self) -> bool:
        return bool(self.review_flags)

    @property
    def confidence_band(self) -> str:
        if self.analysis_confidence >= 80:
            return "High"
        if self.analysis_confidence >= 60:
            return "Medium"
        return "Low"
