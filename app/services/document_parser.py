"""Text extraction — project.md 7.1 steps 1 to 2.

PyMuPDF and python-docx are optional: plain text always works, so the pipeline
and its tests run without the parsing extras installed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

MIN_CHARS_PER_PAGE = 200


@dataclass
class ExtractedDocument:
    text: str
    file_hash: str
    file_name: str
    pages: int = 1
    issues: list[str] | None = None

    @property
    def looks_scanned(self) -> bool:
        return len(self.text.strip()) < MIN_CHARS_PER_PAGE * max(1, self.pages)


def sha256_of(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def extract(path: Path | str) -> ExtractedDocument:
    path = Path(path)
    suffix = path.suffix.lower()
    issues: list[str] = []

    if suffix == ".pdf":
        text, pages = _extract_pdf(path, issues)
    elif suffix in (".docx", ".doc"):
        text, pages = _extract_docx(path, issues)
    else:
        text, pages = path.read_text(encoding="utf-8", errors="replace"), 1

    document = ExtractedDocument(
        text=text,
        file_hash=sha256_of(path),
        file_name=path.name,
        pages=pages,
        issues=issues,
    )
    if document.looks_scanned:
        issues.append("Scanned — needs OCR. Excluded from matching until v2 adds OCR.")
    return document


def _extract_pdf(path: Path, issues: list[str]) -> tuple[str, int]:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        issues.append("PyMuPDF is not installed; install the 'parsing' extra to read PDFs.")
        return "", 1
    blocks: list[str] = []
    with fitz.open(path) as document:
        pages = document.page_count
        for page in document:
            # Sorted blocks keep two-column layouts in reading order.
            for block in sorted(page.get_text("blocks"), key=lambda b: (round(b[1]), b[0])):
                if block[4].strip():
                    blocks.append(block[4].strip())
    return "\n".join(blocks), pages


def _extract_docx(path: Path, issues: list[str]) -> tuple[str, int]:
    try:
        import docx
    except ImportError:
        issues.append("python-docx is not installed; install the 'parsing' extra.")
        return "", 1
    document = docx.Document(str(path))
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts), 1
