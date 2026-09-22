"""The scoring matrix — project.md section 11.

The matrix is derived from the confirmed JD (decision D8) rather than chosen
from a fixed preset. Deriving it in pure Python keeps section 2.3 intact: the
LLM tags signals, code turns them into numbers.

Normalisation uses the largest-remainder method, so a derived matrix totals
exactly 100 by construction. v2.0's five hand-written presets totalled 90, 90,
95, 95 and 80 against a rule requiring 100.
"""

from app.schemas.enums import DIMENSIONS
from app.schemas.jd import JDConfig
from app.schemas.result import DimensionWeight, WeightConfig

#: Base points per dimension — project.md 11.2. Tuned empirically against real
#: JDs (decision D9); treat these as a first draft, not doctrine.
BASE_POINTS = {
    "primary_skill": 40,
    "core_skills": 15,
    "secondary_skills": 5,
    "project_experience": 10,
    "relevant_experience": 8,
    "certification": 0,
    "education": 0,
    "role_seniority": 5,
    "domain_fit": 0,
}


def largest_remainder(exact: dict[str, float], target: int = 100) -> dict[str, int]:
    """Round floats to integers summing to exactly ``target``.

    Ties break by the canonical dimension order, so the result is deterministic
    rather than dependent on dict iteration.
    """
    order = {d: i for i, d in enumerate(DIMENSIONS)}
    floors = {k: int(v) for k, v in exact.items()}
    shortfall = target - sum(floors.values())
    if shortfall <= 0:
        return floors
    ranked = sorted(
        exact.keys(),
        key=lambda k: (-(exact[k] - floors[k]), order.get(k, 99)),
    )
    out = dict(floors)
    for key in ranked[:shortfall]:
        out[key] += 1
    return out


def normalise_points(points: dict[str, int | float], target: int = 100) -> dict[str, int]:
    total = sum(points.values())
    if total <= 0:
        return {k: 0 for k in points}
    exact = {k: v * target / total for k, v in points.items()}
    return largest_remainder(exact, target)


def apply_primary_floor(weights: dict[str, int], floor: int, target: int = 100) -> dict[str, int]:
    """Guarantee the primary skill never drops below the floor (decision D9)."""
    primary = weights.get("primary_skill", 0)
    if primary >= floor:
        return weights
    others = {k: v for k, v in weights.items() if k != "primary_skill"}
    other_total = sum(others.values())
    remaining = target - floor
    if other_total <= 0:
        out = {k: 0 for k in weights}
        out["primary_skill"] = target
        return out
    exact = {k: v * remaining / other_total for k, v in others.items()}
    rescaled = largest_remainder(exact, remaining)
    rescaled["primary_skill"] = floor
    return {k: rescaled.get(k, 0) for k in weights}


def derive_points(jd: JDConfig) -> tuple[dict[str, int], dict[str, str]]:
    """Points and the human-readable reason shown beside each weight."""
    points = dict(BASE_POINTS)
    reasons: dict[str, str] = {}

    # -- primary -----------------------------------------------------------
    primaries = jd.primaries
    primary_bits: list[str] = []
    if primaries:
        names = ", ".join(p.skill for p in primaries)
        primary_bits.append(f"{names} leads the JD")
        if any(p.importance == "mandatory" for p in primaries):
            points["primary_skill"] += 10
            primary_bits.append("mandatory")
        if _primary_dominates(jd):
            points["primary_skill"] += 5
            primary_bits.append("no competing skill family")
    else:
        primary_bits.append("no primary skill identified")
    reasons["primary_skill"] = "; ".join(primary_bits)

    # -- core --------------------------------------------------------------
    core = jd.by_tier("core")
    mandatory_core = [r for r in core if r.importance == "mandatory"]
    points["core_skills"] += min(10, 2 * len(mandatory_core))
    if mandatory_core:
        reasons["core_skills"] = (
            f"{len(mandatory_core)} mandatory core skill"
            f"{'s' if len(mandatory_core) != 1 else ''} "
            f"({', '.join(r.skill for r in mandatory_core)})"
        )
    elif core:
        reasons["core_skills"] = f"{len(core)} supporting skills"
    else:
        reasons["core_skills"] = "no core skills in the JD"
        points["core_skills"] = 0

    # -- secondary ---------------------------------------------------------
    secondary = jd.by_tier("secondary")
    if secondary:
        reasons["secondary_skills"] = f"{len(secondary)} secondary skills listed"
    else:
        points["secondary_skills"] = 0
        reasons["secondary_skills"] = "no secondary skills in the JD"

    # -- project experience ------------------------------------------------
    if jd.delivery_bullets >= 4:
        points["project_experience"] += 5
        reasons["project_experience"] = f"{jd.delivery_bullets} delivery-focused responsibilities"
    else:
        reasons["project_experience"] = "general project delivery expectations"

    # -- relevant experience -----------------------------------------------
    if jd.experience_min is not None:
        band = f"{jd.experience_min:g}"
        if jd.experience_max is not None:
            band += f"-{jd.experience_max:g}"
        reasons["relevant_experience"] = f"JD states {band} years"
    else:
        points["relevant_experience"] = 0
        reasons["relevant_experience"] = "JD states no years requirement"

    # -- certification -----------------------------------------------------
    certs = jd.certification_requirements
    required = [c for c in certs if c.importance in ("mandatory", "important")]
    if required:
        points["certification"] = 20
        reasons["certification"] = f"{required[0].skill} required"
    elif certs:
        points["certification"] = 8
        reasons["certification"] = f"{certs[0].skill} listed as preferred"
    else:
        reasons["certification"] = "no certification in the JD"

    # -- education ---------------------------------------------------------
    if jd.education_requirements:
        points["education"] = 5
        reasons["education"] = "; ".join(jd.education_requirements[:2])
    else:
        reasons["education"] = "no education requirement in the JD"

    # -- role & seniority --------------------------------------------------
    reasons["role_seniority"] = f"{jd.seniority}, {jd.role_family or 'unspecified family'}"

    # -- domain ------------------------------------------------------------
    if jd.domain and jd.domain_required:
        points["domain_fit"] = 12
        reasons["domain_fit"] = f"{jd.domain} experience required"
    elif jd.domain:
        points["domain_fit"] = 5
        reasons["domain_fit"] = f"{jd.domain} mentioned"
    else:
        reasons["domain_fit"] = "no domain in the JD"

    return points, reasons


def _primary_dominates(jd: JDConfig) -> bool:
    """True when the primary outscores the best skill of any other family 2:1."""
    primaries = jd.primaries
    if not primaries:
        return False
    top = max((p.focus_score or 0.0) for p in primaries)
    primary_families = {p.family for p in primaries if p.family}
    rival = 0.0
    for r in jd.skill_requirements:
        if r.tier == "primary":
            continue
        if r.family and r.family in primary_families:
            continue
        rival = max(rival, r.focus_score or 0.0)
    return top >= 2 * rival


def derive_weights(jd: JDConfig, floor: int = 35) -> tuple[dict[str, int], dict[str, str]]:
    """The suggested matrix for a JD, plus the reason shown beside each line."""
    points, reasons = derive_points(jd)
    weights = normalise_points(points)
    weights = apply_primary_floor(weights, floor)
    return weights, reasons


def weight_config_from_weights(
    weights: dict[str, int], base: WeightConfig | None = None
) -> WeightConfig:
    cfg = (base or WeightConfig()).model_copy(deep=True)
    cfg.dimensions = {
        d: DimensionWeight(enabled=weights.get(d, 0) > 0, weight=weights.get(d, 0))
        for d in DIMENSIONS
    }
    return cfg


def normalise_weight_config(cfg: WeightConfig) -> WeightConfig:
    """The UI's Normalize button — rescale whatever is there to total 100."""
    current = {d: cfg.weight_of(d) for d in DIMENSIONS}
    return weight_config_from_weights(normalise_points(current), cfg)


def redistribute_na(cfg: WeightConfig, na_dimensions: set[str]) -> WeightConfig:
    """Spread the weight of not-applicable dimensions over the rest.

    Rarely fires now: the deriver already gives 0 to dimensions the JD is
    silent about (project.md 11.3).
    """
    if not na_dimensions:
        return cfg
    remaining = {
        d: cfg.weight_of(d) for d in DIMENSIONS if d not in na_dimensions and cfg.weight_of(d) > 0
    }
    if not remaining:
        return cfg
    out = normalise_points(remaining)
    full = {d: out.get(d, 0) for d in DIMENSIONS}
    return weight_config_from_weights(full, cfg)


def warnings_for(cfg: WeightConfig) -> list[str]:
    msgs: list[str] = []
    total = cfg.total()
    if total != 100:
        msgs.append(f"Weights must total 100%. Current total: {total}%.")
    primary = cfg.weight_of("primary_skill")
    if primary < 20:
        msgs.append("Primary skill is under 20% — results will drift toward keyword matching.")
    elif primary < cfg.primary_weight_warn:
        msgs.append(
            f"Primary skill is under {cfg.primary_weight_warn}% — results will drift "
            "toward keyword matching."
        )
    return msgs
