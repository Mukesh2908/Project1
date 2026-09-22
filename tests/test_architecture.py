"""Architectural invariants — project.md 6 and 23.1.

Dropping FastAPI (decision D13) removed the HTTP boundary that used to keep the
services UI-agnostic. These tests are what keeps that seam real: without them,
a single ``import streamlit`` inside a service would make the whole engine
unusable from the CLI, the eval harness or any future API.
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"

PURE_PACKAGES = ["scoring"]
UI_FREE_PACKAGES = ["scoring", "services", "schemas", "models", "ai", "retrieval"]
FORBIDDEN_IN_SCORING = {"streamlit", "sqlalchemy", "litellm", "instructor", "requests", "httpx"}


def modules_in(package: str) -> list[Path]:
    return sorted((APP / package).rglob("*.py"))


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("package", UI_FREE_PACKAGES)
def test_no_streamlit_outside_the_ui(package: str):
    offenders = [p for p in modules_in(package) if "streamlit" in imported_roots(p)]
    assert not offenders, (
        f"Streamlit imported outside app/ui: {[str(p) for p in offenders]}. "
        "The services must stay usable from the CLI and the eval harness."
    )


@pytest.mark.parametrize("package", PURE_PACKAGES)
def test_scoring_is_pure(package: str):
    for path in modules_in(package):
        forbidden = imported_roots(path) & FORBIDDEN_IN_SCORING
        assert not forbidden, (
            f"{path} imports {forbidden}. app/scoring must stay free of I/O, "
            "databases and model calls so every score is reproducible."
        )


def test_scoring_does_not_read_files_or_call_out():
    """No file, network or clock access inside the scoring functions."""
    banned = {"open", "input", "print"}
    for path in modules_in("scoring"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in banned, f"{path} calls {node.func.id}()"


def test_every_llm_call_goes_through_the_provider():
    """No service may reach litellm or instructor directly (project.md 19.1)."""
    for package in ("services", "scoring"):
        for path in modules_in(package):
            roots = imported_roots(path)
            assert "litellm" not in roots and "instructor" not in roots, (
                f"{path} imports a model library directly. All calls go through "
                "app/ai/provider.py, which enforces the privacy allowlist."
            )
