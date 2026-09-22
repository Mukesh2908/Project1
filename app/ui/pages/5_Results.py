import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app.config import STORAGE_DIR  # noqa: E402
from app.schemas.enums import VERDICT_LABELS  # noqa: E402
from app.ui.state import (  # noqa: E402
    current_jd_id,
    current_run_id,
    get_store,
    models,
    page,
    style_verdict,
    verdict_chip,
)

page("Results", "Match Score and Verdict — not a rank. The human decides.")

store = get_store()
run_id = current_run_id(store)
if not run_id:
    st.warning("Run a match first on the **Scoring Matrix** page.")
    st.stop()

results = store.load_results(run_id)
config = store.load_jd_config(current_jd_id(store), st.session_state.get("jd_version"))
if not results or config is None:
    st.error("No results for this run.")
    st.stop()

with st.sidebar:
    st.subheader("Filters")
    min_score = st.slider("Minimum match score", 0, 100, 0)
    min_primary = st.slider("Minimum primary skill score", 0, 100, 0)
    confidence_filter = st.multiselect("Confidence", ["High", "Medium", "Low"])
    review_only = st.checkbox("Only those needing review")
    search = st.text_input("Search", placeholder="React 3+ years AWS certified")


def keep(result) -> bool:
    if result.match_score < min_score:
        return False
    primary = result.dimension_scores.get("primary_skill") or 0
    if primary < min_primary:
        return False
    if confidence_filter and result.confidence_band not in confidence_filter:
        return False
    if review_only and not result.review_flags:
        return False
    if search.strip():
        haystack = " ".join(
            [result.display_name, result.verdict]
            + [s["skill"] for s in result.facts["skills"] if s["fit"] > 0]
        ).lower()
        if not all(token.lower() in haystack for token in search.split() if len(token) > 2):
            return False
    return True


filtered = [r for r in results if keep(r)]


NUMERIC_COLUMNS = {
    "Match Score": "{:.1f}",
    "Primary": "{:.1f}",
    "Core": "{:.1f}",
    "Projects": "{:.1f}",
}


def styled(frame: pd.DataFrame):
    """One decimal place, not pandas' default six."""
    return frame.style.map(style_verdict, subset=["Verdict"]).format(NUMERIC_COLUMNS)


def table(rows) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Candidate": r.display_name,
                "Match Score": round(r.match_score, 1),
                "Verdict": verdict_chip(r.verdict),
                "Confidence": f"{r.analysis_confidence}% ({r.confidence_band})",
                "Candidate Primary": r.facts.get("candidate_primary") or "—",
                "Primary": round(r.dimension_scores.get("primary_skill") or 0, 1),
                "Core": round(r.dimension_scores.get("core_skills") or 0, 1),
                "Projects": round(r.dimension_scores.get("project_experience") or 0, 1),
                "Main Strength": (r.explanation.strengths or ["—"])[0],
                "Main Gap": (
                    r.explanation.why_not_higher[0]["dimension"]
                    if r.explanation.why_not_higher
                    else "—"
                ),
                "Flags": len(r.review_flags),
            }
            for r in rows
        ]
    )


tabs = st.tabs(
    [
        f"{VERDICT_LABELS[v]} ({len([r for r in filtered if r.verdict == v])})"
        for v in VERDICT_LABELS
    ]
    + [f"Needs review ({len([r for r in filtered if r.review_flags])})", "All"]
)

for tab, verdict in zip(tabs, list(VERDICT_LABELS), strict=False):
    with tab:
        subset = [r for r in filtered if r.verdict == verdict]
        if subset:
            st.dataframe(styled(table(subset)), width="stretch", hide_index=True)
        else:
            st.caption("No candidates in this group.")

with tabs[-2]:
    subset = [r for r in filtered if r.review_flags]
    if subset:
        for result in subset:
            with st.container(border=True):
                cols = st.columns([3, 1, 1])
                cols[0].markdown(f"**{result.display_name}** — {verdict_chip(result.verdict)}")
                cols[1].metric("Score", f"{result.match_score:.1f}%")
                cols[2].metric("Confidence", f"{result.analysis_confidence}%")
                for flag in result.review_flags:
                    st.warning(flag)
                action = st.columns([1, 1, 1, 3])
                note = action[3].text_input(
                    "Note",
                    key=f"note-{result.profile_id}",
                    label_visibility="collapsed",
                    placeholder="Note",
                )
                for index, choice in enumerate(["confirm", "change_verdict", "dismiss"]):
                    if action[index].button(
                        choice.replace("_", " ").title(), key=f"{choice}-{result.profile_id}"
                    ):
                        from app.services.review_service import record

                        record(store, result, choice, note=note, reviewer="ui")
                        st.success("Logged and added to the eval set.")
    else:
        st.success("Nothing flagged for review in this run.")

with tabs[-1]:
    st.dataframe(styled(table(filtered)), width="stretch", hide_index=True)

st.divider()

excluded_count = len(results) - len(filtered)
st.caption(
    f"Showing {len(filtered)} of {len(results)} scored profiles"
    + (f" ({excluded_count} hidden by filters)." if excluded_count else ".")
)

left, right = st.columns([1, 2])
with left:
    st.subheader("Open a candidate")
    chosen = st.selectbox(
        "Candidate",
        [r.profile_id for r in filtered],
        format_func=lambda pid: next(r.display_name for r in filtered if r.profile_id == pid),
    )
    if st.button("Open detail"):
        st.session_state["profile_id"] = chosen
        st.switch_page("pages/6_Candidate_Detail.py")

with right:
    st.subheader("Excel report")
    use_names = st.checkbox("Use real names", value=True)
    include_quotes = st.checkbox("Include evidence quotes", value=True)
    if st.button("Build report", type="primary"):
        from app.services.excel_report import build_report
        from app.services.matching_engine import RunResult

        run = RunResult(run_id=run_id, results=filtered)
        weights = st.session_state.get("last_weights")
        from app.schemas.result import WeightConfig
        from app.scoring.weights import weight_config_from_weights

        weights = weights or weight_config_from_weights(
            st.session_state.get("weights", config.derived_weights), WeightConfig()
        )
        stamp = pd.Timestamp.now().strftime("%Y-%m-%d_%H%M")
        title = (config.job_title or config.jd_id).replace(" ", "_")[:40]
        path = STORAGE_DIR / "reports" / f"ProfileMatch_{title}_{stamp}.xlsx"
        build_report(run, config, weights, path, use_names, include_quotes, models())
        st.download_button(
            "Download .xlsx",
            path.read_bytes(),
            file_name=path.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
