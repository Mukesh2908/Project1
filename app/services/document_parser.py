"""Text extraction — project.md 7.1 steps 1 to 2.

PyMuPDF and python-docx are optional: plain text always works, so the pipeline
and its tests run without the parsing extras installed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

MIN_CHARS_PER_PAGE = 200

#: A block this wide relative to the page is a header/footer that crosses the
#: full layout, not a column — project.md 24 names two-column layouts as a top
#: parsing risk.
SPAN_WIDTH_RATIO = 0.6
#: Horizontal gap that separates genuine columns from ordinary bullet
#: indentation. Relative to page width rather than a fixed point value,
#: because a column gutter is usually 3-6% of the page while a bullet indent
#: (10-20pt) is roughly 1-3% — a fixed threshold either misses narrow real
#: gutters or false-fires on wide indentation depending on page size.
MIN_GUTTER_PT = 20.0
GUTTER_WIDTH_RATIO = 0.05
MIN_COLUMN_BLOCKS = 2
#: A cluster must cover a meaningful vertical span to count as a column —
#: guards against one wide indented line being mistaken for a second column.
MIN_COLUMN_HEIGHT_RATIO = 0.15


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


@dataclass
class TextBlock:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def width(self) -> float:
        return self.x1 - self.x0


def _cluster_by_x(blocks: list[TextBlock], gap: float) -> list[list[TextBlock]]:
    """Group blocks left to right, splitting wherever a wide gap separates them."""
    if not blocks:
        return []
    ordered = sorted(blocks, key=lambda b: b.x0)
    clusters: list[list[TextBlock]] = [[ordered[0]]]
    cluster_max_x1 = ordered[0].x1
    for block in ordered[1:]:
        if block.x0 - cluster_max_x1 >= gap:
            clusters.append([block])
            cluster_max_x1 = block.x1
        else:
            clusters[-1].append(block)
            cluster_max_x1 = max(cluster_max_x1, block.x1)
    return clusters


def _is_genuine_multi_column(clusters: list[list[TextBlock]], page_height: float) -> bool:
    """At least two clusters must look like real columns, not stray indentation."""
    if len(clusters) < 2 or not page_height:
        return False
    qualifying = 0
    for cluster in clusters:
        if len(cluster) < MIN_COLUMN_BLOCKS:
            continue
        y_span = max(b.y1 for b in cluster) - min(b.y0 for b in cluster)
        if y_span / page_height >= MIN_COLUMN_HEIGHT_RATIO:
            qualifying += 1
    return qualifying >= 2


def reorder_blocks(
    raw_blocks: list[tuple], page_width: float, page_height: float
) -> tuple[list[str], bool]:
    """Text blocks in reading order, handling side-by-side columns.

    A naive sort by (y, x) interleaves two columns line by line: a block in
    the right column at y=40 sorts before a block in the left column at
    y=200, so the two columns' text is shuffled together roughly at random.
    That is not just garbled text — it can push a later section's heading
    (say CERTIFICATIONS, from a left sidebar) into the middle of the main
    column's text, which then silently swallows everything after it as
    certification entries. This is normative, testable behaviour rather than
    a comment claiming block-order handles it (v3.0's original claim, which
    did not).

    A full-width block (a name banner, a section divider) is treated as a
    separator: it flushes whatever column run came before it, so a header
    between two column runs cannot be absorbed into either one.

    Returns (ordered text lines, whether columns were detected) so the caller
    can surface the uncertainty rather than hide it (project.md 2.7).
    """
    blocks = [
        TextBlock(b[0], b[1], b[2], b[3], b[4].strip())
        for b in raw_blocks
        if len(b) >= 5 and b[4].strip()
    ]
    if not blocks:
        return [], False

    ordered: list[str] = []
    columns_detected = False
    pending: list[TextBlock] = []

    def flush_pending() -> None:
        nonlocal columns_detected
        if not pending:
            return
        gap = max(MIN_GUTTER_PT, page_width * GUTTER_WIDTH_RATIO)
        clusters = _cluster_by_x(pending, gap)
        if _is_genuine_multi_column(clusters, page_height):
            columns_detected = True
            for cluster in sorted(clusters, key=lambda c: min(b.x0 for b in c)):
                for block in sorted(cluster, key=lambda b: b.y0):
                    ordered.append(block.text)
        else:
            for block in sorted(pending, key=lambda b: (round(b.y0), b.x0)):
                ordered.append(block.text)
        pending.clear()

    for block in sorted(blocks, key=lambda b: b.y0):
        if block.width >= page_width * SPAN_WIDTH_RATIO:
            flush_pending()
            ordered.append(block.text)
        else:
            pending.append(block)
    flush_pending()

    return ordered, columns_detected


def _extract_pdf(path: Path, issues: list[str]) -> tuple[str, int]:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        issues.append("PyMuPDF is not installed; install the 'parsing' extra to read PDFs.")
        return "", 1
    lines: list[str] = []
    any_columns = False
    with fitz.open(path) as document:
        pages = document.page_count
        for page in document:
            page_lines, columns_detected = reorder_blocks(
                page.get_text("blocks"), page.rect.width, page.rect.height
            )
            lines.extend(page_lines)
            any_columns = any_columns or columns_detected
    if any_columns:
        issues.append(
            "Multi-column layout detected and reordered column by column — "
            "verify section order if results look off."
        )
    return "\n".join(lines), pages


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
