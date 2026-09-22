import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st  # noqa: E402
import yaml  # noqa: E402

from app.ai.provider import available_providers  # noqa: E402
from app.config import DATA_DIR, load_settings, save_settings  # noqa: E402
from app.ui.state import get_equivalence_store, get_store, page  # noqa: E402

page("Settings", "Providers, privacy, thresholds and the taxonomy.")

settings = load_settings()
store = get_store()

tab_privacy, tab_models, tab_equivalence, tab_taxonomy = st.tabs(
    ["Privacy & providers", "Models", "Equivalence review", "Taxonomy"]
)

with tab_privacy:
    privacy = settings.setdefault("privacy", {})
    st.subheader("Privacy mode")
    st.caption(
        "This is enforced in code at the provider boundary, not by convention. "
        "A blocked provider raises before a request is built."
    )
    mode = st.radio(
        "Mode",
        ["dummy_data_only", "approved_cloud"],
        index=0 if privacy.get("mode", "dummy_data_only") == "dummy_data_only" else 1,
        format_func=lambda m: (
            "Dummy data only — fixtures, any provider"
            if m == "dummy_data_only"
            else "Approved cloud — real profiles, approved providers only"
        ),
    )

    st.subheader("Providers")
    providers = available_providers()
    trains = [p for p, meta in providers.items() if meta["free_tier_trains"]]
    st.warning(
        "Free tiers of **" + ", ".join(trains) + "** may use submitted prompts to "
        "improve their models. They are appropriate for synthetic fixtures, not for "
        "real employee resumes. Approve only endpoints carrying no-training terms.",
        icon="⚠️",
    )
    for name, meta in providers.items():
        if name == "mock":
            continue
        cols = st.columns([2, 1, 2])
        cols[0].write(f"**{meta['label']}**")
        cols[1].write("key set" if meta["key_present"] else "no key")
        cols[2].caption(f"`{meta['env_var']}`")

    approved = st.multiselect(
        "Approved for employee data",
        [p for p in providers if p != "mock"],
        default=privacy.get("approved_providers") or [],
        help="Populate this from what your company has actually approved.",
    )
    if mode == "approved_cloud" and not approved:
        st.error("Approved cloud mode with no approved providers blocks every call.")

    retention = st.number_input(
        "Retention (months)", 1, 120, int(privacy.get("retention_months", 12))
    )
    mask = st.checkbox("Mask PII before every call", value=privacy.get("mask_pii", True))
    if not mask:
        st.error(
            "Masking is the primary privacy control now that no model runs locally. "
            "Turning it off sends names and contact details to a third party."
        )

    if st.button("Save privacy settings", type="primary"):
        privacy.update(
            {
                "mode": mode,
                "approved_providers": approved,
                "retention_months": int(retention),
                "mask_pii": mask,
            }
        )
        save_settings(settings)
        st.success("Saved.")

with tab_models:
    llm = settings.setdefault("llm", {})
    st.caption("Switching provider is a configuration change — no code changes.")
    options = [
        "groq/llama-3.3-70b-versatile",
        "gemini/gemini-2.5-flash",
        "nvidia_nim/meta/llama-3.3-70b-instruct",
        "openai/gpt-4o-mini",
        "openai/gpt-4o",
        "mock/fixture",
    ]
    updated = {}
    for agent in ("profile_parser", "jd_analyzer", "equivalence_judge", "reason_writer"):
        current = llm.get(agent, options[0])
        choices = options if current in options else [current] + options
        updated[agent] = st.selectbox(
            agent.replace("_", " ").title(), choices, index=choices.index(current)
        )
    if st.button("Save models", type="primary"):
        llm.update(updated)
        save_settings(settings)
        st.success("Saved.")

with tab_equivalence:
    st.caption(
        "Skill pairs judged by a model, awaiting review. An unreviewed bad call "
        "would otherwise distort every future run."
    )
    equivalence = get_equivalence_store()
    pending = store.equivalences("pending")
    if not pending and not equivalence.pending:
        st.success("Nothing awaiting review.")
    for row in pending:
        cols = st.columns([2, 2, 1, 1, 1])
        cols[0].write(row["skill_a"])
        cols[1].write(row["skill_b"])
        cols[2].write(row["relation"])
        if cols[3].button("Approve", key=f"ok-{row['skill_a']}-{row['skill_b']}"):
            equivalence.approve(row["skill_a"], row["skill_b"])
            store.save_equivalence(
                row["skill_a"],
                row["skill_b"],
                row["relation"],
                row["factor"],
                row["source"],
                "approved",
            )
            st.rerun()
        if cols[4].button("Reject", key=f"no-{row['skill_a']}-{row['skill_b']}"):
            equivalence.reject(row["skill_a"], row["skill_b"])
            store.save_equivalence(
                row["skill_a"], row["skill_b"], "none", 0.0, row["source"], "rejected"
            )
            st.rerun()

with tab_taxonomy:
    st.caption(
        "Editing these files changes scores. Their hash is recorded with every run "
        "so past results stay reproducible."
    )
    which = st.selectbox(
        "File", ["skill_families.yaml", "certifications.yaml", "weight_presets.yaml"]
    )
    content = (DATA_DIR / which).read_text()
    st.code(content, language="yaml")
    parsed = yaml.safe_load(content)
    if which == "weight_presets.yaml":
        for preset in (parsed.get("presets") or {}).values():
            total = sum(preset["weights"].values())
            (st.success if total == 100 else st.error)(f"{preset['name']}: {total}%")
