"""Split a resume into sections and project blocks — project.md 7.1 steps 4 to 5."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

HEADINGS = {
    "summary": r"(professional\s+summary|summary|objective|profile\s+summary)",
    "skills": r"(technical\s+skills|skills|technology\s+stack|core\s+competenc\w+)",
    "experience": r"(work\s+experience|professional\s+experience|experience|employment)",
    "projects": r"(projects?|project\s+experience|assignments?)",
    "education": r"(education|academic\s+qualifications?)",
    "certifications": r"(certifications?|licenses?\s*&?\s*certifications?)",
}

HEADING_RE = re.compile(
    r"^\s*(?:" + "|".join(p for p in HEADINGS.values()) + r")\s*:?\s*$",
    re.I | re.M,
)

# "Project 1:" is a block boundary; "Client:" is a field inside one. Treating
# both as boundaries splits every project in two, leaving half the blocks
# dateless and doubling the apparent project count.
PROJECT_RE = re.compile(r"^\s*project\s*\d*\s*[:\-]\s*(.+)$", re.I | re.M)
FALLBACK_PROJECT_RE = re.compile(r"^\s*(?:client|title)\s*[:\-]\s*(.+)$", re.I | re.M)

MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    )
}

# Two-digit years are common on Indian resumes ("Mar'20 - Dec'22"), so both
# widths are accepted and normalised in _year().
DATE_RANGE = re.compile(
    r"([A-Za-z]{3,9})?\s*['\u2018\u2019`]?\s*(\d{4}|\d{2})\s*(?:-|\u2013|\u2014|to|till|until)\s*"
    r"(?:([A-Za-z]{3,9})?\s*['\u2018\u2019`]?\s*(\d{4}|\d{2})|present|current|till\s*date|date|now|ongoing)",
    re.I,
)

TECH_LINE = re.compile(
    r"^\s*(?:tech(?:nology)?\s*stack|technologies|tools?\s*(?:&|and)?\s*tech\w*|environment)\s*[:\-]\s*(.+)$",
    re.I | re.M,
)


@dataclass
class Section:
    name: str
    text: str


@dataclass
class ProjectBlock:
    title: str
    text: str
    start: date | None = None
    end: date | None = None
    dates_approx: bool = False
    tech_line: str = ""
    bullets: list[str] = field(default_factory=list)


def split_sections(text: str) -> dict[str, str]:
    """Regex headings first. An empty result is the signal for an LLM fallback."""
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        return {"body": text}
    sections: dict[str, str] = {}
    if matches[0].start() > 0:
        sections["header"] = text[: matches[0].start()].strip()
    for i, match in enumerate(matches):
        heading = match.group(0).strip().strip(":").lower()
        name = next(
            (key for key, pattern in HEADINGS.items() if re.fullmatch(pattern, heading, re.I)),
            heading,
        )
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[match.end() : end].strip()
    return sections


def parse_date_range(text: str) -> tuple[date | None, date | None, bool]:
    """Returns (start, end, approximate). ``end=None`` means present."""
    match = DATE_RANGE.search(text)
    if not match:
        return None, None, False
    start_month, start_year, end_month, end_year = match.groups()
    approx = start_month is None or (end_year is not None and end_month is None)

    def build(month: str | None, year: str | None, default_month: int) -> date | None:
        if not year:
            return None
        index = MONTHS.get((month or "")[:3].lower(), default_month)
        return date(_year(year), index, 1)

    start = build(start_month, start_year, 6)
    end = build(end_month, end_year, 6) if end_year else None
    return start, end, approx


def _year(raw: str) -> int:
    """Normalise a 2- or 4-digit year. '98 is 1998; '20 is 2020."""
    value = int(raw)
    if value >= 100:
        return value
    return 1900 + value if value > 50 else 2000 + value


def split_projects(text: str) -> list[ProjectBlock]:
    """Split the projects/experience section into one block per project."""
    if not text.strip():
        return []
    matches = list(PROJECT_RE.finditer(text)) or list(FALLBACK_PROJECT_RE.finditer(text))
    blocks: list[ProjectBlock] = []

    if not matches:
        # No explicit markers: treat date-led paragraphs as project boundaries.
        chunks = [c for c in re.split(r"\n\s*\n", text) if c.strip()]
        for i, chunk in enumerate(chunks):
            start, end, approx = parse_date_range(chunk)
            blocks.append(
                ProjectBlock(
                    title=chunk.strip().splitlines()[0][:80] or f"Project {i + 1}",
                    text=chunk.strip(),
                    start=start,
                    end=end,
                    dates_approx=approx,
                    tech_line=_tech_line(chunk),
                    bullets=_bullets(chunk),
                )
            )
        return blocks

    for i, match in enumerate(matches):
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[match.start() : end_pos].strip()
        start, end, approx = parse_date_range(body)
        blocks.append(
            ProjectBlock(
                title=match.group(1).strip()[:80],
                text=body,
                start=start,
                end=end,
                dates_approx=approx,
                tech_line=_tech_line(body),
                bullets=_bullets(body),
            )
        )
    return blocks


def _tech_line(text: str) -> str:
    match = TECH_LINE.search(text)
    return match.group(1).strip() if match else ""


def _bullets(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped[0] in "-•*▪o·" or re.match(r"^\d+[.)]\s", stripped):
            cleaned = stripped.lstrip("-•*▪o·0123456789.) ").strip()
            if len(cleaned) > 10:
                out.append(cleaned)
    return out


def split_skills(text: str) -> list[str]:
    """Flatten a skills section into individual skill names."""
    skills: list[str] = []
    for line in text.splitlines():
        line = re.sub(r"^[^:]{0,40}:", "", line)  # drop "Languages:" style prefixes
        for token in re.split(r"[,;|/]|\s{2,}", line):
            # A line can carry several inline prefixes:
            # "Languages: Python, Java; Frameworks: React".
            token = re.sub(r"^[^:]{0,30}:", "", token)
            cleaned = token.strip().strip("-•*▪· ")
            if 1 < len(cleaned) <= 40 and not cleaned.endswith("."):
                skills.append(cleaned)
    seen: set[str] = set()
    out: list[str] = []
    for skill in skills:
        if skill.lower() not in seen:
            seen.add(skill.lower())
            out.append(skill)
    return out
