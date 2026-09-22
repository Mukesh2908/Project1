"""Pydantic models — project.md section 18.1."""

from app.schemas.evidence import (
    Certification,
    EvidenceCard,
    EvidenceQuote,
    ManualEvidence,
    ProfileRecord,
    Project,
    ProjectSkill,
)
from app.schemas.jd import Conflict, JDAnalysis, JDConfig, Requirement, SkillSignal
from app.schemas.result import (
    DimensionWeight,
    Explanation,
    MatchResult,
    SkillFit,
    WeightConfig,
)

__all__ = [
    "Certification",
    "Conflict",
    "DimensionWeight",
    "EvidenceCard",
    "EvidenceQuote",
    "Explanation",
    "JDAnalysis",
    "JDConfig",
    "ManualEvidence",
    "MatchResult",
    "ProfileRecord",
    "Project",
    "ProjectSkill",
    "Requirement",
    "SkillFit",
    "SkillSignal",
    "WeightConfig",
]
