"""Shared literal types and ordered vocabularies."""

from typing import Literal

Ownership = Literal["self", "team", "vague"]
Production = Literal["yes", "no", "unknown"]
UsageContext = Literal["dev", "test", "support", "analysis", "other"]
EvidenceQuality = Literal["weak", "weak_plus", "medium", "strong", "very_strong", "verified"]
Tier = Literal["primary", "core", "secondary"]
Importance = Literal["mandatory", "important", "preferred", "optional"]
Category = Literal["skill", "certification", "domain", "education", "experience", "note"]
Seniority = Literal["junior", "mid", "senior", "lead"]
Verdict = Literal["deployable_now", "needs_ramp_up", "trainable", "not_a_fit"]
Source = Literal["ai", "edited", "user"]
EvidenceSource = Literal["parsed", "manual"]
Relation = Literal["exact", "equivalent", "related", "none"]
DualPrimaryMode = Literal["all", "any"]

#: Depth a given evidence quality can prove — project.md section 7.2.
QUALITY_DEPTH_CAP: dict[str, int] = {
    "weak": 1,
    "weak_plus": 2,
    "medium": 3,
    "strong": 4,
    "very_strong": 5,
    "verified": 5,
}

#: Ranked worst → best, so ``max`` picks the strongest evidence.
QUALITY_ORDER: list[str] = ["weak", "weak_plus", "medium", "strong", "very_strong", "verified"]

#: Canonical dimension order. Also the tie-break order for largest-remainder
#: rounding in the weight deriver (project.md section 11.2).
DIMENSIONS: list[str] = [
    "primary_skill",
    "core_skills",
    "secondary_skills",
    "project_experience",
    "relevant_experience",
    "certification",
    "education",
    "role_seniority",
    "domain_fit",
]

DIMENSION_LABELS: dict[str, str] = {
    "primary_skill": "Primary skill",
    "core_skills": "Core skills",
    "secondary_skills": "Secondary skills",
    "project_experience": "Project experience",
    "relevant_experience": "Relevant experience",
    "certification": "Certification",
    "education": "Education",
    "role_seniority": "Role & seniority",
    "domain_fit": "Domain fit",
}

VERDICT_LABELS: dict[str, str] = {
    "deployable_now": "Deployable Now",
    "needs_ramp_up": "Needs Ramp-up",
    "trainable": "Trainable",
    "not_a_fit": "Not a Fit",
}

#: Verdict presentation. A symbol always accompanies the colour so the verdict
#: survives a colourblind reader and a greyscale print (project.md section 17.3).
VERDICT_STYLE: dict[str, dict[str, str]] = {
    "deployable_now": {"symbol": "●", "colour": "#D7F0E3", "text": "#1F6B4B"},
    "needs_ramp_up": {"symbol": "◐", "colour": "#D9EAF7", "text": "#1F5C86"},
    "trainable": {"symbol": "◔", "colour": "#FBEBCF", "text": "#8A5B12"},
    "not_a_fit": {"symbol": "○", "colour": "#ECECEC", "text": "#555555"},
}

#: Wording rules — project.md section 2.8 / 13.2.
FORBIDDEN_PHRASES: list[str] = [
    "definitely",
    "will succeed",
    "guaranteed",
    "best candidate",
    "better than",
    "worse than",
    "perfect fit",
    "ideal candidate",
    "should be hired",
    "highly recommend",
    "top talent",
    "certainly",
]
