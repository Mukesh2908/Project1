import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st  # noqa: E402

from app.config import text_hash  # noqa: E402
from app.services.jd_analyzer import analyse, config_diff, similarity  # noqa: E402
from app.ui.state import get_provider, get_store, models, page  # noqa: E402

page("JD Input", "Upload or paste a job description.")

store = get_store()

tab_paste, tab_upload = st.tabs(["Paste text", "Upload a file"])
jd_text = ""

with tab_paste:
    jd_text = st.text_area("Job description", height=320, placeholder="Paste the JD here…")

with tab_upload:
    uploaded = st.file_uploader("JD file", type=["pdf", "docx", "txt"])
    if uploaded is not None:
        if uploaded.name.endswith(".txt"):
            jd_text = uploaded.getvalue().decode("utf-8", errors="replace")
        else:
            from app.config import STORAGE_DIR
            from app.services.document_parser import extract

            target = STORAGE_DIR / "jds" / uploaded.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(uploaded.getbuffer())
            jd_text = extract(target).text
        st.text_area("Extracted text", jd_text, height=240, disabled=True)

# Similar-JD reuse: show what differs before offering to carry overrides across.
if jd_text.strip():
    for existing in store.list_jds():
        score = similarity(jd_text, existing.get("text") or "")
        if score < 0.85:
            continue
        previous = store.load_jd_config(existing["jd_id"])
        if not previous:
            continue
        st.info(
            f"This JD is {score:.0%} similar to **{existing['title']}** "
            f"({existing['jd_id']}, configured {existing['created_at'][:10]})."
        )
        st.session_state["reuse_from"] = existing["jd_id"]
        break

if st.button("Analyze JD", type="primary", disabled=not jd_text.strip()):
    with st.spinner("Reading the JD…"):
        result = analyse(jd_text, get_provider(), models().get("jd_analyzer", "mock/fixture"))
    config = result.config
    store.save_jd(config.jd_id, config.job_title, jd_text, text_hash(jd_text))
    store.save_jd_config(config, ai_suggestion=config)
    st.session_state["jd_id"] = config.jd_id

    reuse_id = st.session_state.get("reuse_from")
    if reuse_id:
        previous = store.load_jd_config(reuse_id)
        if previous:
            diff = config_diff(previous, config)
            with st.expander("What differs from the similar JD", expanded=True):
                if diff:
                    st.dataframe(diff, width="stretch", hide_index=True)
                else:
                    st.write("No differences in requirements.")
                st.caption(
                    "Reuse copies the earlier overrides and weights. Check the "
                    "differences first — a wrong primary skill propagates silently "
                    "otherwise."
                )

    st.success(f"Analyzed as {config.jd_id}. Open **JD Review** to check and confirm it.")
    st.page_link("pages/3_JD_Review.py", label="Go to JD Review →")

st.divider()
st.subheader("Recent job descriptions")
recent = store.list_jds()
if recent:
    st.dataframe(
        [{"JD": j["jd_id"], "Title": j["title"], "Added": j["created_at"][:16]} for j in recent],
        width="stretch",
        hide_index=True,
    )
else:
    st.caption("None yet.")
