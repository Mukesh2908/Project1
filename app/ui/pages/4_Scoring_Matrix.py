import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st  # noqa: E402

from app.config import load_settings  # noqa: E402
from app.models.store import Store  # noqa: E402
from app.schemas.enums import DIMENSION_LABELS, DIMENSIONS  # noqa: E402
from app.schemas.result import WeightConfig  # noqa: E402
from app.scoring.weights import (  # noqa: E402
    normalise_weight_config,
    warnings_for,
    weight_config_from_weights,
)
from app.services.matching_engine import run_match  # noqa: E402
from app.ui.state import current_jd_id, get_equivalence_store, get_store, models, page  # noqa: E402

page("Scoring Matrix", "Derived from the JD. Change anything you disagree with.")

store: Store = get_store()
jd_id = current_jd_id(store)
if not jd_id:
    st.warning("Analyze and confirm a JD first.")
    st.stop()

config = store.load_jd_config(jd_id, st.session_state.get("jd_version"))
if config is None:
    st.error("No confirmed JD configuration found.")
    st.stop()

settings = load_settings().get("scoring", {})
base = WeightConfig(
    skill_proof_parts=settings.get("skill_proof_parts", WeightConfig().skill_proof_parts),
    gate_threshold=settings.get("gate_threshold", 0.60),
    trainable_threshold=settings.get("trainable_threshold", 0.25),
    deployable_threshold=settings.get("deployable_threshold", 0.80),
    listed_only_cap=settings.get("listed_only_cap", 0.10),
    borderline_band=settings.get("borderline_band", 3.0),
    tier_skill_cap=settings.get("tier_skill_cap", 5),
    dual_primary_mode=config.dual_primary_mode,
)

st.caption(
    "These weights come from what the JD actually asks for, not from a preset. Each line shows why."
)

if "weights" not in st.session_state or st.session_state.get("weights_jd") != jd_id:
    st.session_state["weights"] = dict(config.derived_weights)
    st.session_state["weights_jd"] = jd_id

current = st.session_state["weights"]

for dimension in DIMENSIONS:
    cols = st.columns([2, 3, 4])
    cols[0].markdown(f"**{DIMENSION_LABELS[dimension]}**")
    current[dimension] = cols[1].slider(
        DIMENSION_LABELS[dimension],
        0,
        100,
        int(current.get(dimension, 0)),
        key=f"w-{dimension}",
        label_visibility="collapsed",
    )
    reason = config.derived_weight_reasons.get(dimension, "")
    derived = config.derived_weights.get(dimension, 0)
    marker = "" if current[dimension] == derived else f"  ·  _derived {derived}%_"
    cols[2].caption(f"{reason}{marker}")

total = sum(current.values())
cols = st.columns([1, 1, 3])
cols[0].metric("Total", f"{total}%")
if cols[1].button("Normalize"):
    normalised = normalise_weight_config(weight_config_from_weights(current, base))
    st.session_state["weights"] = {d: normalised.weight_of(d) for d in DIMENSIONS}
    st.rerun()

weights = weight_config_from_weights(current, base)
for message in warnings_for(weights):
    cols[2].warning(message)

with st.expander("Advanced settings"):
    left, right = st.columns(2)
    weights.gate_threshold = left.slider("Main-skill gate", 0.0, 1.0, weights.gate_threshold, 0.05)
    weights.deployable_threshold = left.slider(
        "Deployable Now threshold", 0.0, 1.0, weights.deployable_threshold, 0.05
    )
    weights.trainable_threshold = left.slider(
        "Trainable threshold", 0.0, 1.0, weights.trainable_threshold, 0.05
    )
    weights.listed_only_cap = right.slider(
        "Listed-only cap",
        0.0,
        0.5,
        weights.listed_only_cap,
        0.05,
        help="A skill that appears only in a skills list can never score above this.",
    )
    weights.tier_skill_cap = right.number_input(
        "Skills scored per tier",
        1,
        20,
        weights.tier_skill_cap,
        help="Core and Secondary score this many requirements. Mandatory ones "
        "always count. Keeps a padded JD from moving everyone's score.",
    )
    weights.borderline_band = right.number_input(
        "Borderline band (points)", 0.0, 10.0, weights.borderline_band, 0.5
    )
    st.caption(
        "Changing anything here re-runs the skill proof engine, not just the "
        "weighted sum — verdicts can change, not only scores."
    )

st.divider()

profiles = store.load_profiles()
disabled = total != 100 or not profiles
if total != 100:
    st.info("The Run button unlocks when the weights total exactly 100%.")
if not profiles:
    st.info("No profiles in the pool yet.")

if st.button("Run match", type="primary", disabled=disabled):
    with st.spinner(f"Scoring {len(profiles)} profiles…"):
        run = run_match(profiles, config, weights, get_equivalence_store())
        store.save_run(run, config, weights, models())
    st.session_state["run_id"] = run.run_id
    st.success(
        f"Scored {run.scored_count} profiles"
        + (f", {len(run.excluded)} excluded by the pre-filter." if run.excluded else ".")
    )
    st.page_link("pages/5_Results.py", label="Go to Results →")

if st.session_state.get("run_id"):
    st.divider()
    st.subheader("What-if")
    st.caption(
        "Compare the current matrix against a proposal. Weight-only changes are "
        "instant; advanced settings above recompute the scoring."
    )
    results = store.load_results(st.session_state["run_id"])
    if results:
        from app.scoring.whatif import compare_matrices, contribution_deltas

        proposal = dict(current)
        chosen = st.selectbox(
            "Boost a dimension by 10 points", [DIMENSION_LABELS[d] for d in DIMENSIONS]
        )
        target = next(d for d in DIMENSIONS if DIMENSION_LABELS[d] == chosen)
        proposal[target] = min(100, proposal.get(target, 0) + 10)
        proposed = normalise_weight_config(weight_config_from_weights(proposal, base))

        rows = compare_matrices(results, weights, proposed)
        st.dataframe(rows, width="stretch", hide_index=True)

        if rows:
            first = next(r for r in results if r.profile_id == rows[0]["profile_id"])
            st.caption(f"Why {first.display_name}'s score moved")
            st.dataframe(
                contribution_deltas(first, weights, proposed), width="stretch", hide_index=True
            )
