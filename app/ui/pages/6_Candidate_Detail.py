import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app.schemas.evidence import ManualEvidence  # noqa: E402
from app.ui.state import current_run_id, get_store, page, verdict_chip  # noqa: E402

page("Candidate Detail", "Every point traces back to a line in the resume.")

store = get_store()
run_id = current_run_id(store)
results_preview = store.load_results(run_id) if run_id else []
profile_id = st.session_state.get("profile_id") or (
    results_preview[0].profile_id if results_preview else None
)
if not run_id or not profile_id:
    st.warning("Open a candidate from the **Results** page.")
    st.stop()

results = store.load_results(run_id)
result = next((r for r in results if r.profile_id == profile_id), None)
profile = store.load_profile(profile_id)
if result is None or profile is None:
    st.error("Candidate not found in this run.")
    st.stop()

facts = result.facts
cols = st.columns([3, 1, 1, 1])
cols[0].markdown(f"### {result.display_name}")
cols[1].metric("Match Score", f"{result.match_score:.1f}%")
# st.metric truncates a long value to an ellipsis ("Deploy..."), which is
# useless for the one field a reader most needs to read.
cols[2].markdown("Verdict")
cols[2].markdown(f"### {verdict_chip(result.verdict)}")
cols[3].metric("Confidence", f"{result.analysis_confidence}%", result.confidence_band)

st.caption(
    f"JD primary: {', '.join(facts['jd_primary']) or '—'} · "
    f"Candidate primary: {facts['candidate_primary'] or '—'} · Lane: {facts['lane']}"
)
st.info(result.explanation.summary, icon="📋")
if result.explanation.summary_source == "template":
    st.caption("Summary generated from the facts table, not by a model.")

tabs = st.tabs(
    [
        "Score breakdown",
        "Skill evidence",
        "Why not higher",
        "Path to deployable",
        "Flags & verification",
        "Add verified evidence",
    ]
)

with tabs[0]:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Dimension": d["label"],
                    "Weight %": round(d["weight"], 1),
                    "Score %": round(d["score"], 1),
                    "Contribution": round(d["contribution"], 2),
                }
                for d in facts["dimensions"]
            ]
        ),
        width="stretch",
        hide_index=True,
    )
    st.metric("Total", f"{result.match_score:.2f}")
    if facts["na_dimensions"]:
        st.caption(
            "Not applicable for this JD, weight redistributed across the rest: "
            + ", ".join(facts["na_dimensions"])
        )

with tabs[1]:
    for skill in facts["skills"]:
        if skill["fit"] == 0 and not skill["evidence"]:
            continue
        # When a requirement is credited through a different technology, say
        # so in the header. The years, project count and quotes below all
        # belong to the matched skill, not the requirement, and burying that
        # in a caption under the quotes reads as if the candidate had direct
        # experience they do not have.
        via = ""
        if skill["relation"] not in ("exact", "none") and skill["matched_skill"]:
            via = f" · _via {skill['matched_skill']} ({skill['relation']})_"
        header = (
            f"**{skill['skill']}**{via} · {skill['tier']} · needs {skill['needs']} · "
            f"found {skill['found']} · {skill['projects']} project(s) · "
            f"{skill['last_used']} — **{skill['fit']}%**"
        )
        if not skill["scored"]:
            header += "  _(reported, not scored)_"
        st.markdown(header)
        if via:
            st.caption(
                f"The evidence below is {skill['matched_skill']} work, credited at the "
                f"{skill['relation']} rate — not direct {skill['skill']} experience."
            )
        for quote in skill["evidence"]:
            st.code(quote, language=None)
        if skill["gap"] != "Evidence found":
            st.caption(skill["gap"])
        st.divider()

    missing = [s for s in facts["skills"] if s["fit"] == 0 and not s["evidence"]]
    if missing:
        st.caption("No evidence found: " + ", ".join(s["skill"] for s in missing))

with tabs[2]:
    for row in result.explanation.why_not_higher:
        st.markdown(f"**↓ {row['dimension']} — {row['lost']:.1f} points**")
        if row["detail"]:
            st.caption(row["detail"])

with tabs[3]:
    for step in result.explanation.path_to_deployable:
        st.markdown(f"- {step}")
    st.caption(
        "The system states what evidence is missing. It does not estimate how long "
        "learning would take."
    )

with tabs[4]:
    if profile.red_flags:
        for flag in profile.red_flags:
            st.warning(flag)
    if result.review_flags:
        st.subheader("Review triggers")
        for flag in result.review_flags:
            st.info(flag)
    if result.explanation.requires_verification:
        st.subheader("Requires verification")
        st.caption("Suggested interview questions for the weakest or least certain claims.")
        for item in result.explanation.requires_verification:
            st.markdown(f"- {item}")

with tabs[5]:
    st.caption(
        "Adding evidence does not overwrite what the parser read. Both readings stay "
        "on the record, and every entry becomes a labelled example for tuning."
    )
    existing = store.manual_evidence_for(profile_id)
    if existing:
        st.dataframe(
            [
                {
                    "Skill": e.skill,
                    "Depth": f"L{e.depth}",
                    "Years": e.years,
                    "Note": e.note,
                    "By": e.author,
                }
                for e in existing
            ],
            width="stretch",
            hide_index=True,
        )
    with st.form("add_evidence"):
        cols = st.columns([2, 1, 1, 1])
        skill = cols[0].text_input("Skill")
        depth = cols[1].number_input("Depth (L)", 1, 5, 4)
        years = cols[2].number_input("Years", 0.0, 30.0, 0.0, 0.5)
        ownership = cols[3].selectbox("Ownership", ["self", "team", "vague"])
        note = st.text_input("What you know", placeholder="Interviewed them — led the rebuild")
        author = st.text_input("Your name")
        if st.form_submit_button("Add verified evidence", type="primary") and skill.strip():
            store.add_manual_evidence(
                ManualEvidence(
                    profile_id=profile_id,
                    skill=skill.strip(),
                    depth=int(depth),
                    years=years or None,
                    ownership=ownership,
                    note=note,
                    author=author,
                )
            )
            st.success("Added. Re-run the match to see it reflected in the score.")
