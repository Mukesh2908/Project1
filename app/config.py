"""Settings loading and content hashing.

Taxonomy and equivalence hashes are recorded with every run: editing a YAML
file changes scores, and without a version stamp old runs would silently stop
being reproducible (project.md 18.2).
"""

from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
DATA_DIR = APP_DIR / "data"
SETTINGS_PATH = APP_DIR / "settings.yaml"
STORAGE_DIR = Path(os.environ.get("PME_STORAGE_DIR", ROOT_DIR / "storage"))

#: Provider prefixes LiteLLM understands, and whether the free tier of each may
#: train on submitted prompts. Used for the warning shown in Settings.
PROVIDERS = {
    "gemini": {"label": "Google Gemini", "free_tier_trains": True},
    "groq": {"label": "Groq", "free_tier_trains": True},
    "nvidia_nim": {"label": "NVIDIA NIM", "free_tier_trains": True},
    "openai": {"label": "OpenAI", "free_tier_trains": False},
    "mock": {"label": "Mock (fixtures)", "free_tier_trains": False},
}

API_KEY_ENV = {
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "nvidia_nim": "NVIDIA_NIM_API_KEY",
    "openai": "OPENAI_API_KEY",
}


@lru_cache(maxsize=1)
def load_settings() -> dict[str, Any]:
    with open(SETTINGS_PATH) as handle:
        return yaml.safe_load(handle) or {}


def reload_settings() -> dict[str, Any]:
    load_settings.cache_clear()
    return load_settings()


def save_settings(settings: dict[str, Any]) -> None:
    with open(SETTINGS_PATH, "w") as handle:
        yaml.safe_dump(settings, handle, sort_keys=False)
    load_settings.cache_clear()


@lru_cache(maxsize=4)
def load_yaml(name: str) -> dict[str, Any]:
    with open(DATA_DIR / name) as handle:
        return yaml.safe_load(handle) or {}


def file_hash(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def taxonomy_version() -> str:
    return file_hash(DATA_DIR / "skill_families.yaml")


def weights_hash(weights: dict) -> str:
    return text_hash(repr(sorted(weights.items())))


def provider_of(model: str) -> str:
    """``groq/llama-3.3-70b`` -> ``groq``."""
    return model.split("/", 1)[0] if "/" in model else model


def storage_path(*parts: str) -> Path:
    path = STORAGE_DIR.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
