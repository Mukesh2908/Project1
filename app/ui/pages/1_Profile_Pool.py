import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app.config import STORAGE_DIR  # noqa: E402
from app.services.job_runner import start_ingest  # noqa: E402
from app.services.retention_service import due_for_review  # noqa: E402
from app.ui.state import get_provider, get_store, models, page  # noqa: E402

page("Profile Pool", "Upload once. Parsing never repeats for an unchanged file.")

store = get_store()

uploaded = st.file_uploader("Add resumes", type=["pdf", "docx", "txt"], accept_multiple_files=True)

col_a, col_b = st.columns([1, 3])
with col_a:
    if st.button("Parse uploaded", type="primary", disabled=not uploaded):
        inbox = STORAGE_DIR / "resumes"
        inbox.mkdir(parents=True, exist_ok=True)
        paths = []
        for item in uploaded:
            target = inbox / item.name
            target.write_bytes(item.getbuffer())
            paths.append(target)
        st.session_state["job_id"] = start_ingest(
            store, paths, get_provider(), models().get("profile_parser", "mock/fixture")
        )

job_id = st.session_state.get("job_id")
if job_id:

    @st.fragment(run_every=2)
    def progress() -> None:
        job = store.get_job(job_id)
        if not job:
            return
        st.progress(job["progress"], text=f"{job['done']}/{job['total']} — {job['message']}")
        if job["status"] == "done":
            st.success("Parsing complete.")
        elif job["status"] == "failed":
            st.error(job["error"])

    progress()

st.divider()

profiles = store.load_profiles(include_excluded=True)
if not profiles:
    st.info("No profiles yet. Upload resumes above to get started.")
    st.stop()

rows = []
for profile in profiles:
    proven = sum(1 for c in profile.evidence_cards.values() if c.projects_used > 0)
    rows.append(
        {
            "ID": profile.profile_id,
            "Name": profile.display_name,
            "Lane": profile.lane_skill or "—",
            "Years": profile.total_experience_years,
            "Skills proven": proven,
            "Skills listed": len(profile.skills_listed),
            "Projects": len(profile.projects),
            "Flags": len(profile.red_flags),
            "Status": profile.status,
        }
    )

st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

selected = st.selectbox(
    "Inspect a profile",
    [p.profile_id for p in profiles],
    format_func=lambda pid: (
        f"{pid} — {next(p.display_name for p in profiles if p.profile_id == pid)}"
    ),
)
profile = next(p for p in profiles if p.profile_id == selected)

tab_evidence, tab_projects, tab_flags = st.tabs(["Evidence cards", "Projects", "Flags"])

with tab_evidence:
    card_rows = [
        {
            "Skill": card.skill,
            "Depth": f"L{card.max_depth}",
            "Years": card.hands_on_years if card.hands_on_years is not None else "unknown",
            "Projects": card.projects_used,
            "Last used": "current"
            if card.is_current
            else (
                f"{card.years_since_last_use:.0f} yrs ago"
                if card.years_since_last_use is not None
                else "unknown"
            ),
            "Quality": card.best_evidence_quality,
            "Production": "yes" if card.production else "—",
            "Ownership": card.ownership,
            "Listed only": "yes" if card.skills_list_only else "",
        }
        for card in sorted(profile.evidence_cards.values(), key=lambda c: -c.max_depth)
    ]
    st.dataframe(pd.DataFrame(card_rows), width="stretch", hide_index=True)

with tab_projects:
    for project in profile.projects:
        dates = f"{project.start or 'undated'} → {project.end or 'present'}"
        with st.expander(f"{project.title} · {dates}"):
            st.caption(
                f"Domain: {project.domain or '—'} · Role family: {project.role_family or '—'}"
            )
            for skill in project.skills:
                st.markdown(
                    f"**{skill.skill}** · L{skill.depth} · {skill.ownership} · "
                    f"production: {skill.production}"
                )
                if skill.quote:
                    st.code(skill.quote, language=None)

with tab_flags:
    if profile.red_flags:
        for flag in profile.red_flags:
            st.warning(flag)
    else:
        st.success("No red flags on this profile.")
    if profile.parse_issues:
        st.subheader("Parse issues")
        for issue in profile.parse_issues:
            st.info(issue)

st.divider()
overdue = due_for_review(store)
if overdue:
    st.subheader("Past the retention window")
    st.caption(
        "These profiles are older than the retention period set in Settings. "
        "Deleting removes the file, the evidence, the PII map and the vectors."
    )
    for profile in overdue:
        cols = st.columns([3, 2, 1])
        cols[0].write(f"{profile.profile_id} — {profile.display_name}")
        reason = cols[1].text_input(
            "Reason",
            key=f"reason-{profile.profile_id}",
            label_visibility="collapsed",
            placeholder="Reason",
        )
        if cols[2].button("Delete", key=f"del-{profile.profile_id}"):
            from app.services.retention_service import purge

            purge(store, profile.profile_id, reason, "ui")
            st.rerun()
