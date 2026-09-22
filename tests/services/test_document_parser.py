"""Column-order extraction — project.md 24 names two-column layouts as a top
parsing risk. This is what makes that mitigation real rather than a comment.

The pure clustering logic is tested directly on synthetic block tuples so it
runs without PyMuPDF installed; one integration test at the bottom exercises
the actual PDF path and is skipped when the 'parsing' extra is not present.
"""

import pytest

from app.services.document_parser import reorder_blocks

PAGE_W, PAGE_H = 600.0, 800.0


def block(x0, y0, x1, y1, text):
    return (x0, y0, x1, y1, text, 0, 0)


# -- the bug this exists to prevent ----------------------------------------


def test_two_columns_are_read_column_by_column_not_interleaved():
    """The failure mode: a naive (y, x) sort interleaves two independent
    columns line by line, corrupting both."""
    blocks = [
        block(40, 40, 250, 60, "LEFT-1"),
        block(300, 40, 560, 60, "RIGHT-1"),
        block(40, 80, 250, 100, "LEFT-2"),
        block(300, 80, 560, 300, "RIGHT-2 (tall block)"),
        block(40, 120, 250, 400, "LEFT-3 (tall block)"),
        block(300, 320, 560, 340, "RIGHT-3"),
    ]
    lines, detected = reorder_blocks(blocks, PAGE_W, PAGE_H)
    assert detected is True
    assert lines == [
        "LEFT-1",
        "LEFT-2",
        "LEFT-3 (tall block)",
        "RIGHT-1",
        "RIGHT-2 (tall block)",
        "RIGHT-3",
    ]


def test_a_heading_between_columns_does_not_get_swallowed():
    """The concrete failure: a later section's heading (e.g. CERTIFICATIONS
    from a short left sidebar) landing mid-document and absorbing everything
    that follows as if it belonged to that section."""
    blocks = [
        block(40, 40, 250, 60, "SKILLS"),
        block(300, 40, 560, 60, "SUMMARY"),
        block(40, 80, 250, 100, "React, SQL"),
        block(40, 120, 250, 140, "CERTIFICATIONS"),
        block(40, 160, 250, 180, "AWS Developer"),
        block(300, 80, 560, 400, "long project text that must stay intact"),
    ]
    lines, _ = reorder_blocks(blocks, PAGE_W, PAGE_H)
    left = lines[: lines.index("SUMMARY")]
    assert left == ["SKILLS", "React, SQL", "CERTIFICATIONS", "AWS Developer"]
    assert "long project text that must stay intact" in lines


# -- must not fire on ordinary single-column text ---------------------------


def test_single_column_with_indented_bullets_is_not_mistaken_for_columns():
    blocks = [
        block(40, 40, 500, 60, "PROFESSIONAL SUMMARY"),
        block(40, 80, 500, 100, "Frontend engineer."),
        block(60, 120, 500, 140, "- Built a component library"),
        block(60, 150, 500, 170, "- Cut page load 40%"),
    ]
    lines, detected = reorder_blocks(blocks, PAGE_W, PAGE_H)
    assert detected is False
    assert lines == [b[4] for b in blocks]


def test_a_single_short_offset_line_does_not_trigger_column_mode():
    """One indented line must not be mistaken for a second column — it has
    only one block, below MIN_COLUMN_BLOCKS."""
    blocks = [
        block(40, 40, 500, 60, "Line one"),
        block(300, 80, 340, 100, "x"),
        block(40, 120, 500, 140, "Line three"),
    ]
    _, detected = reorder_blocks(blocks, PAGE_W, PAGE_H)
    assert detected is False


# -- spanning headers act as separators -------------------------------------


def test_a_full_width_header_separates_two_column_runs():
    blocks = [
        block(40, 0, 560, 20, "Priya Raghavan"),  # spans >60% of page width
        block(40, 40, 250, 200, "LEFT run"),
        block(40, 220, 250, 400, "LEFT run 2"),
        block(300, 40, 560, 200, "RIGHT run"),
        block(300, 220, 560, 400, "RIGHT run 2"),
    ]
    lines, detected = reorder_blocks(blocks, PAGE_W, PAGE_H)
    assert lines[0] == "Priya Raghavan"
    assert detected is True
    assert lines[1:3] == ["LEFT run", "LEFT run 2"]
    assert lines[3:5] == ["RIGHT run", "RIGHT run 2"]


def test_empty_input_returns_empty():
    assert reorder_blocks([], PAGE_W, PAGE_H) == ([], False)


def test_blocks_with_no_text_are_dropped():
    blocks = [block(40, 40, 500, 60, "   "), block(40, 80, 500, 100, "Real text")]
    lines, _ = reorder_blocks(blocks, PAGE_W, PAGE_H)
    assert lines == ["Real text"]


# -- integration: the real PDF path -----------------------------------------


def test_real_two_column_pdf_extracts_in_correct_order(tmp_path):
    fitz = pytest.importorskip("fitz", reason="PyMuPDF ('parsing' extra) not installed")
    from app.services.document_parser import extract

    # PyMuPDF splits a textbox into separate blocks at blank-line paragraph
    # breaks, so realistic section-structured text (like a real resume) is
    # used here rather than plain consecutive lines, which collapse into one
    # block per column and never exercise the clustering logic at all.
    # Content spans a meaningful share of the page height, matching a real
    # resume — a two-line fixture never clears MIN_COLUMN_HEIGHT_RATIO, which
    # exists precisely to reject a stray short offset line as a "column".
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(
        fitz.Rect(40, 40, 250, 780),
        "LEFT\n\nSKILLS\nReact, SQL, Python\n\n"
        "EDUCATION\nB.Tech, CS\n\n"
        "CERTIFICATIONS\nAWS Developer\n\n"
        "LANGUAGES\nEnglish, Hindi",
        fontsize=9,
    )
    page.insert_textbox(
        fitz.Rect(280, 40, 560, 780),
        "RIGHT\n\nSUMMARY\nFrontend engineer with years of experience.\n\n"
        "PROJECTS\nBuilt a component library used widely.\n\n"
        "More project detail goes here across several lines.\n\n"
        "Another paragraph of project history and detail.",
        fontsize=9,
    )
    path = tmp_path / "resume.pdf"
    doc.save(str(path))
    doc.close()

    document = extract(path)
    left_index = document.text.index("SKILLS")
    right_index = document.text.index("SUMMARY")
    assert left_index < right_index
    assert any("Multi-column" in issue for issue in document.issues)
