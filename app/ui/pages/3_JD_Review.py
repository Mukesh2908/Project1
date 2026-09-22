import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app.scoring.focus import format_calculation  # noqa: E402
from app.services.jd_analyzer import finalise  # noqa: E402
from app.ui.state import current_jd_id, get_store, page  # noqa: E402

page("JD Review", "The AI suggests. You decide. Your version is what gets scored.")

store = get_store()
jd_id = current_jd_id(store)
if not jd_id:
    st.warning("Analyze a JD first on the **JD Input** page.")
    st.stop()

config = store.load_jd_config(jd_id)
if config is None:
    st.error(f"No configuration found for {jd_id}.")
    st.stop()

band = config.confidence_band
header = st.columns([3, 1])
header[0].markdown(f"### {config.job_title or jd_id}")
header[1].metric("JD confidence", f"{config.confidence}%", band)
st.caption(f"**Role intent:** {config.role_intent or '—'}")

if band == "Low":
    st.warning(
        "Confidence is low: the JD gives little title or responsibility evidence. "
        "Confirm the primary skill before matching."
    )

primaries = config.primaries
st.markdown(f"**Suggested primary:** {', '.join(p.skill for p in primaries) or 'none identified'}")
for requirement in primaries:
    if requirement.focus_breakdown:
        st.code(
            format_calculation(
                requirement.skill, requirement.focus_breakdown, requirement.focus_score or 0
            ),
            language=None,
        )
    if requirement.why:
        st.caption(f"Why {requirement.skill}? {requirement.why}")

if len(primaries) > 1:
    st.info(
        "This JD has two primary skills. Must a candidate prove **both**, or is "
        "**either** acceptable? This changes the verdict for a candidate strong in "
        "one and absent in the other."
    )
    mode = st.radio(
        "Dual primary rule",
        ["all", "any"],
        format_func=lambda m: "Must prove both" if m == "all" else "Either is acceptable",
        index=0 if config.dual_primary_mode == "all" else 1,
        horizontal=True,
    )
    config.dual_primary_mode = mode  # type: ignore[assignment]

if config.conflicts:
    st.subheader(f"{len(config.conflicts)} conflict(s) to review")
    for index, conflict in enumerate(config.conflicts):
        with st.container(border=True):
            st.warning(conflict.message)
            st.caption(f"Suggested: {conflict.suggested_action}")
            conflict.resolved = st.checkbox(
                "Resolved", value=conflict.resolved, key=f"conflict-{index}"
            )
            conflict.resolution_note = st.text_input(
                "Note", value=conflict.resolution_note, key=f"conflict-note-{index}"
            )

st.divider()
st.subheader("Requirements")
st.caption(
    "Edit anything. Tier decides which dimension a skill scores in; importance "
    "decides how much it weighs within that tier. **Min years** is a hard floor "
    "you set — unlike the JD's inferred years, it gates the verdict."
)

editable = pd.DataFrame(
    [
        {
            "Skill": r.skill,
            "Category": r.category,
            "Tier": r.tier or "",
            "Importance": r.importance,
            "Depth": r.required_depth,
            "Years": r.required_years,
            "Min years": r.min_years,
            "Focus": r.focus_score or 0,
            "Scored": r.scored,
            "Source": r.source,
        }
        for r in config.requirements
    ]
)

edited = st.data_editor(
    editable,
    width="stretch",
    hide_index=True,
    disabled=["Focus", "Source"],
    column_config={
        "Tier": st.column_config.SelectboxColumn(options=["", "primary", "core", "secondary"]),
        "Importance": st.column_config.SelectboxColumn(
            options=["mandatory", "important", "preferred", "optional"]
        ),
        "Category": st.column_config.SelectboxColumn(
            options=["skill", "certification", "domain", "education", "experience", "note"]
        ),
        "Depth": st.column_config.NumberColumn(min_value=1, max_value=5),
        "Scored": st.column_config.CheckboxColumn(
            help="Unticked means reported but not counted — beyond the tier cap."
        ),
    },
    key="requirement_editor",
)

st.caption(
    "Rows marked **not scored** are beyond the tier cap: they appear in the evidence "
    "table and the gaps, but cannot move the score. This is what stops a padded "
    "skills list dragging everyone down."
)

with st.expander("Add a requirement of your own"):
    cols = st.columns([2, 1, 1, 1])
    new_skill = cols[0].text_input("Requirement")
    new_category = cols[1].selectbox(
        "Category", ["skill", "certification", "domain", "education", "experience", "note"]
    )
    new_importance = cols[2].selectbox(
        "Importance", ["mandatory", "important", "preferred", "optional"], index=2
    )
    new_min_years = cols[3].number_input("Min years", min_value=0.0, value=0.0, step=0.5)
    if st.button("Add", disabled=not new_skill.strip()):
        from app.schemas.jd import Requirement

        config.requirements.append(
            Requirement(
                skill=new_skill.strip(),
                category=new_category,
                tier="core" if new_category == "skill" else None,
                importance=new_importance,
                min_years=new_min_years or None,
                source="user",
            )
        )
        store.save_jd_config(config)
        st.rerun()

if st.button("Confirm this version", type="primary"):
    by_skill = {r.skill: r for r in config.requirements}
    for _, row in edited.iterrows():
        requirement = by_skill.get(row["Skill"])
        if requirement is None:
            continue
        changed = (
            requirement.tier != (row["Tier"] or None)
            or requirement.importance != row["Importance"]
            or requirement.required_depth != int(row["Depth"])
            or requirement.required_years != float(row["Years"])
        )
        requirement.tier = row["Tier"] or None
        requirement.importance = row["Importance"]
        requirement.category = row["Category"]
        requirement.required_depth = int(row["Depth"])
        requirement.required_years = float(row["Years"])
        requirement.min_years = (
            float(row["Min years"]) if pd.notna(row["Min years"]) and row["Min years"] else None
        )
        requirement.scored = bool(row["Scored"])
        if changed and requirement.source == "ai":
            requirement.source = "edited"

    config.version = store.next_version(config.jd_id)
    config = finalise(config)
    store.save_jd_config(config)
    st.session_state["jd_version"] = config.version
    st.success(f"Saved as version {config.version}. Open **Scoring Matrix** next.")
    st.page_link("pages/4_Scoring_Matrix.py", label="Go to Scoring Matrix →")
