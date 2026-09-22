"""PII masking — project.md 20.2.

With no local model, masking is the primary privacy control rather than
defence-in-depth, so it is deterministic first and NER second: the contact
block and every pattern we can match by rule are masked without relying on a
statistical model that is weak on non-Western names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"(?:(?:\+|00)\d{1,3}[\s-]?)?(?:\d[\s-]?){9,13}\d")
URL = re.compile(r"https?://\S+|(?:www\.|linkedin\.com/|github\.com/)\S+", re.I)
# Bounded to date-shaped content. A loose character class here swallows the
# following "Gender:" label, which then leaves the value itself unmasked.
DOB = re.compile(
    r"(?:date of birth|dob|d\.o\.b)\s*[:\-]?\s*(?:"
    r"\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}"
    r"|\d{1,2}\s+[A-Za-z]{3,9},?\s+\d{2,4}"
    r"|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{2,4}"
    r"|\d{4}"
    r")",
    re.I,
)
GENDER = re.compile(r"\b(?:gender|sex)\s*[:\-]?\s*(?:male|female|m|f|other)\b", re.I)
MARITAL = re.compile(r"\b(?:marital status|married|unmarried|single)\b\s*[:\-]?\s*\w*", re.I)
NATIONALITY = re.compile(r"\b(?:nationality|citizenship)\s*[:\-]?\s*\w+", re.I)
ADDRESS = re.compile(r"(?:address|location|residing at|based in)\s*[:\-]?\s*[^\n]{4,80}", re.I)
NAME_LABEL = re.compile(r"^\s*(?:name)\s*[:\-]\s*(.+)$", re.I | re.M)

#: Headings that mark where personal details stop and substance begins.
SECTION_START = re.compile(
    r"^\s*(professional\s+summary|summary|objective|profile|experience|"
    r"work\s+experience|employment|skills|technical\s+skills|education|projects)\b",
    re.I | re.M,
)

COLLEGE = re.compile(
    r"\b(?:[A-Z][\w.&]*\s+){0,4}(?:University|College|Institute of Technology|Polytechnic)\b"
)


@dataclass
class MaskResult:
    text: str
    pii_map: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return self.pii_map.get("name", "")


def mask(text: str, mask_college: bool = True) -> MaskResult:
    """Replace personal details with placeholders, keeping the real values local."""
    pii: dict[str, str] = {}
    counts: dict[str, int] = {}

    def swap(pattern: re.Pattern, token: str, key: str | None = None):
        nonlocal text

        def _replace(match: re.Match) -> str:
            counts[token] = counts.get(token, 0) + 1
            if key and key not in pii:
                pii[key] = match.group(0).strip()
            return f"[{token}]"

        text = pattern.sub(_replace, text)

    # The name is whatever a "Name:" label says, else the first line of the
    # header block before the first real section heading.
    header_end = SECTION_START.search(text)
    header = text[: header_end.start()] if header_end else text[:400]
    labelled = NAME_LABEL.search(header)
    if labelled:
        pii["name"] = labelled.group(1).strip()
    else:
        for line in header.splitlines():
            stripped = line.strip()
            if not stripped or EMAIL.search(stripped) or PHONE.search(stripped):
                continue
            if 2 <= len(stripped.split()) <= 5 and len(stripped) < 60:
                pii["name"] = stripped
                break

    swap(EMAIL, "EMAIL", "email")
    swap(URL, "URL")
    swap(GENDER, "GENDER", "gender")
    swap(DOB, "DOB", "dob")
    swap(MARITAL, "MARITAL", "marital_status")
    swap(NATIONALITY, "NATIONALITY", "nationality")
    swap(ADDRESS, "ADDRESS", "location")
    swap(PHONE, "PHONE", "phone")
    if mask_college:
        swap(COLLEGE, "INSTITUTION")

    name = pii.get("name")
    if name:
        for part in [name] + [p for p in name.split() if len(p) > 2]:
            pattern = re.compile(rf"\b{re.escape(part)}\b", re.I)
            text, hits = pattern.subn("[NAME]", text)
            if hits:
                counts["NAME"] = counts.get("NAME", 0) + hits

    return MaskResult(text=text, pii_map=pii, counts=counts)


def unmask(text: str, pii_map: dict[str, str]) -> str:
    """Restore real values for display in the UI — never for an LLM call."""
    out = text
    for token, key in (
        ("[NAME]", "name"),
        ("[EMAIL]", "email"),
        ("[PHONE]", "phone"),
        ("[ADDRESS]", "location"),
    ):
        if key in pii_map:
            out = out.replace(token, pii_map[key])
    return out


def contains_pii(text: str) -> list[str]:
    """Used by the masking-recall test and as a pre-send assertion."""
    found: list[str] = []
    if EMAIL.search(text):
        found.append("email")
    if PHONE.search(text):
        found.append("phone")
    if DOB.search(text):
        found.append("dob")
    if GENDER.search(text):
        found.append("gender")
    return found
