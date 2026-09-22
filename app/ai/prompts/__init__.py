"""Versioned prompts. The version is stored with every LLM output so a prompt
change re-runs only what it affects (project.md 19.1)."""

from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=16)
def load_prompt(name: str) -> str:
    return (PROMPT_DIR / f"{name}_v1.md").read_text()
