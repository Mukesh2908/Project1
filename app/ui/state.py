"""Shared Streamlit helpers.

Session state holds identifiers only — never scores. Anything derived is
recomputed from the store, so a stale rerun cannot show a number that no longer
follows from the data.
"""

from __future__ import annotations

import streamlit as st

from app.ai.provider import AIProvider, LiteLLMProvider, MockProvider
from app.config import load_settings
from app.models.store import Store
from app.schemas.enums import VERDICT_LABELS, VERDICT_STYLE
from app.services.skill_engine import EquivalenceStore

PAGE_ICON = "◆"


def page(title: str, subtitle: str = "") -> None:
    st.set_page_config(
        page_title=f"{title} · Profile Match Engine", page_icon=PAGE_ICON, layout="wide"
    )
    st.title(title)
    if subtitle:
        st.caption(subtitle)
    privacy_banner()


@st.cache_resource
def get_store() -> Store:
    return Store()


@st.cache_resource
def get_equivalence_store() -> EquivalenceStore:
    return EquivalenceStore()


def get_provider() -> AIProvider:
    if st.session_state.get("use_mock"):
        return _mock_provider()
    return LiteLLMProvider()


def _mock_provider() -> MockProvider:
    from app.ai.demo_provider import build_mock_provider

    return build_mock_provider()


def models() -> dict[str, str]:
    return dict(load_settings().get("llm", {}))


def privacy_banner() -> None:
    """The privacy mode is always visible — it decides where resume text goes."""
    privacy = load_settings().get("privacy", {})
    mode = privacy.get("mode", "dummy_data_only")
    if mode == "dummy_data_only":
        st.info(
            "**Privacy mode: dummy data only.** Any configured provider may be used, "
            "and real profile data is blocked in code. Switch to `approved_cloud` in "
            "Settings once your company has approved providers for employee data.",
            icon="🔒",
        )
    else:
        approved = ", ".join(privacy.get("approved_providers") or []) or "none configured"
        st.warning(
            f"**Privacy mode: approved cloud.** Real profile data may be sent to: "
            f"{approved}. PII is masked before every call.",
            icon="🔒",
        )


def verdict_chip(verdict: str) -> str:
    """Symbol plus label, never colour alone — project.md 17.3."""
    style = VERDICT_STYLE.get(verdict, {})
    return f"{style.get('symbol', '')} {VERDICT_LABELS.get(verdict, verdict)}"


def style_verdict(value: str) -> str:
    for verdict, style in VERDICT_STYLE.items():
        if VERDICT_LABELS[verdict] in str(value):
            return f"background-color: {style['colour']}; color: {style['text']}"
    return ""


def current_jd_id(store: Store) -> str | None:
    """The JD in play, surviving a browser refresh.

    Streamlit session state is lost on reload, so falling back to the most
    recent stored JD stops a refresh silently discarding the user's work.
    """
    if st.session_state.get("jd_id"):
        return st.session_state["jd_id"]
    jds = store.list_jds()
    if not jds:
        return None
    latest = max(jds, key=lambda j: j.get("created_at") or "")
    st.session_state["jd_id"] = latest["jd_id"]
    return latest["jd_id"]


def current_run_id(store: Store) -> str | None:
    """The run in play, likewise surviving a refresh."""
    if st.session_state.get("run_id"):
        return st.session_state["run_id"]
    runs = store.list_runs()
    if not runs:
        return None
    st.session_state["run_id"] = runs[0]["run_id"]
    st.session_state.setdefault("jd_id", runs[0]["jd_id"])
    st.session_state.setdefault("jd_version", runs[0]["jd_version"])
    return runs[0]["run_id"]


def require(condition: bool, message: str) -> bool:
    if not condition:
        st.warning(message)
    return condition
