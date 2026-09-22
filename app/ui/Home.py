"""Profile Match Engine — entry point.

Run with:
    streamlit run app/ui/Home.py --server.address=127.0.0.1
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from app.config import load_settings  # noqa: E402
from app.ui.state import get_store, models, page  # noqa: E402

page("Profile Match Engine", "AI interprets · Python calculates · Human decides")

store = get_store()
profiles = store.load_profiles(include_excluded=True)
jds = store.list_jds()
runs = store.list_runs()

left, middle, right = st.columns(3)
left.metric("Profiles in pool", len(profiles))
middle.metric("Job descriptions", len(jds))
right.metric("Match runs", len(runs))

st.divider()

col_a, col_b = st.columns([3, 2])

with col_a:
    st.subheader("How it works")
    st.markdown(
        """
1. **Profile Pool** — upload resumes once. Parsing is the expensive step and it
   never repeats for an unchanged file.
2. **JD Input** — paste or upload a job description.
3. **JD Review** — check what the system thinks the role is about, and correct it.
   Your version is what gets scored.
4. **Scoring Matrix** — the weights are derived from the JD. Adjust anything.
5. **Results** — ranked candidates with the evidence behind every point.
6. **Candidate Detail** — full breakdown, and a place to add what you know.
7. **Settings** — providers, privacy mode, thresholds, retention.

Scores are decision support. Every verdict is a starting point for a
conversation, not the end of one.
        """
    )

with col_b:
    st.subheader("Configured models")
    llm = models()
    for agent in ("profile_parser", "jd_analyzer", "equivalence_judge", "reason_writer"):
        st.write(f"**{agent.replace('_', ' ').title()}** — `{llm.get(agent, 'not set')}`")

    st.subheader("Embeddings")
    embeddings = load_settings().get("embeddings", {})
    st.write(f"`{embeddings.get('model')}` ({embeddings.get('provider')})")

    st.checkbox(
        "Use fixture responses (no API calls)",
        key="use_mock",
        help="Runs the pipeline against the deterministic test fixtures. "
        "Useful for trying the app without provider keys.",
    )

if runs:
    st.divider()
    st.subheader("Recent runs")
    st.dataframe(runs[:10], width="stretch", hide_index=True)
