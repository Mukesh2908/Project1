"""Skill taxonomy, normalisation and equivalence — project.md 10.1 and 18.3.

LLM-judged equivalences land in a review queue rather than being cached
permanently: one bad call (Java = JavaScript) would otherwise distort every
future run with no way to notice or undo it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from app.config import load_yaml, taxonomy_version

RELATION_FACTORS = {"exact": 1.0, "equivalent": 0.8, "related": 0.5, "none": 0.0}


@lru_cache(maxsize=1)
def _taxonomy() -> dict:
    return load_yaml("skill_families.yaml")


@lru_cache(maxsize=1)
def _synonym_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for skill, meta in (_taxonomy().get("skills") or {}).items():
        index[skill.lower()] = skill
        for synonym in (meta or {}).get("synonyms", []) or []:
            index[synonym.lower()] = skill
    return index


@lru_cache(maxsize=1)
def _relation_index() -> dict[tuple[str, str], str]:
    index: dict[tuple[str, str], str] = {}
    for entry in _taxonomy().get("relations") or []:
        if len(entry) != 3:
            continue
        a, b, relation = entry
        index[(a, b)] = relation
        index[(b, a)] = relation
    return index


@lru_cache(maxsize=1)
def _implied_index() -> list[tuple[str, str]]:
    """(phrase, skill) pairs — 'stored procedure' implies SQL."""
    pairs: list[tuple[str, str]] = []
    for skill, meta in (_taxonomy().get("skills") or {}).items():
        for phrase in (meta or {}).get("implied_by", []) or []:
            pairs.append((phrase.lower(), skill))
    return sorted(pairs, key=lambda p: -len(p[0]))


def normalise(raw: str) -> str:
    """Map a raw mention to its canonical skill name."""
    if not raw:
        return ""
    cleaned = raw.strip().strip(".,;:()")
    return _synonym_index().get(cleaned.lower(), cleaned)


def family_of(skill: str) -> str | None:
    meta = (_taxonomy().get("skills") or {}).get(normalise(skill))
    return (meta or {}).get("group")


def role_adjacency() -> dict[str, list[str]]:
    return {
        family: (meta or {}).get("adjacent", []) or []
        for family, meta in (_taxonomy().get("role_families") or {}).items()
    }


def domain_adjacency() -> dict[str, list[str]]:
    return {
        domain: (meta or {}).get("adjacent", []) or []
        for domain, meta in (_taxonomy().get("domains") or {}).items()
    }


def known_skills() -> list[str]:
    return sorted((_taxonomy().get("skills") or {}).keys())


def find_skills(text: str) -> dict[str, int]:
    """Canonical skills named in ``text``, with occurrence counts.

    Matched spans are consumed longest-alias-first, so "Azure Data Factory"
    claims its whole span and does not also register a bare "Azure". Word
    boundaries that allow '.' and '+' keep "Java" out of "JavaScript" while
    still matching real names like Next.js and C++.
    """
    lowered = text.lower()
    index = _synonym_index()
    spans: list[tuple[int, int, str]] = []
    for alias in sorted(index, key=len, reverse=True):
        for match in re.finditer(rf"(?<![\w.]){re.escape(alias)}(?![\w.])", lowered):
            spans.append((match.start(), match.end(), index[alias]))

    spans.sort(key=lambda s: (-(s[1] - s[0]), s[0]))
    claimed: list[tuple[int, int]] = []
    found: dict[str, int] = {}
    for start, end, canonical in spans:
        if any(start < c_end and end > c_start for c_start, c_end in claimed):
            continue
        claimed.append((start, end))
        found[canonical] = found.get(canonical, 0) + 1
    return found


def implied_skills(text: str) -> set[str]:
    """Skills a phrase demonstrates without naming — project.md 7.1 step 6."""
    lowered = (text or "").lower()
    return {skill for phrase, skill in _implied_index() if phrase in lowered}


@dataclass
class EquivalenceStore:
    """Taxonomy relations plus reviewed LLM judgments."""

    judged: dict[tuple[str, str], str] = field(default_factory=dict)
    pending: dict[tuple[str, str], str] = field(default_factory=dict)
    rejected: set[tuple[str, str]] = field(default_factory=set)

    def relation(self, wanted: str, held: str) -> str:
        a, b = normalise(wanted), normalise(held)
        if a == b:
            return "exact"
        if a.lower() == b.lower():
            return "exact"
        key = (a, b)
        if key in self.rejected:
            return "none"
        taxonomy = _relation_index().get(key)
        if taxonomy:
            return taxonomy
        if key in self.judged:
            return self.judged[key]
        return "none"

    def record_judgment(self, a: str, b: str, relation: str, reviewed: bool = False) -> None:
        key = (normalise(a), normalise(b))
        target = self.judged if reviewed else self.pending
        target[key] = relation
        target[(key[1], key[0])] = relation

    def approve(self, a: str, b: str) -> None:
        key = (normalise(a), normalise(b))
        relation = self.pending.pop(key, None)
        self.pending.pop((key[1], key[0]), None)
        if relation:
            self.judged[key] = relation
            self.judged[(key[1], key[0])] = relation

    def reject(self, a: str, b: str) -> None:
        key = (normalise(a), normalise(b))
        self.pending.pop(key, None)
        self.pending.pop((key[1], key[0]), None)
        self.rejected.add(key)
        self.rejected.add((key[1], key[0]))

    def version(self) -> str:
        from app.config import text_hash

        return text_hash(f"{taxonomy_version()}|{sorted(self.judged.items())}")


def best_match(
    wanted: str,
    cards: dict,
    store: EquivalenceStore | None = None,
) -> tuple[str | None, str, float]:
    """Pick the strongest evidence card for a wanted skill.

    A direct claim always beats related-technology credit, which is what stops
    an Angular card outranking a real React one.
    """
    store = store or EquivalenceStore()
    best: tuple[str | None, str, float] = (None, "none", 0.0)
    for held, _card in cards.items():
        relation = store.relation(wanted, held)
        factor = RELATION_FACTORS.get(relation, 0.0)
        if factor > best[2]:
            best = (held, relation, factor)
        if relation == "exact":
            break
    return best
