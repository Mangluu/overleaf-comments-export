from __future__ import annotations

from overleaf_comments_export.anchors import (
    build_line_starts,
    offset_to_line_col,
    resolve_anchor,
)
from overleaf_comments_export.model import DocText
from overleaf_comments_export.sections import find_headings, nearest_heading


def _doc(text: str) -> DocText:
    line_starts = build_line_starts(text)
    headings = find_headings(text, line_starts)
    return DocText(
        doc_id="d", pathname="main.tex", text=text,
        line_starts=line_starts, headings=headings,
    )


def test_offset_to_line_col_basic():
    text = "hello\nworld\n"
    starts = build_line_starts(text)
    assert offset_to_line_col(starts, 0) == (1, 0)
    assert offset_to_line_col(starts, 4) == (1, 4)
    assert offset_to_line_col(starts, 6) == (2, 0)
    assert offset_to_line_col(starts, 10) == (2, 4)


def test_resolve_anchor_exact():
    text = "the novel framework is here"
    doc = _doc(text)
    idx = text.find("novel framework")
    ro, line, col, stale = resolve_anchor(doc, idx, "novel framework")
    assert ro == idx
    assert (line, col, stale) == (1, idx, False)


def test_resolve_anchor_drift_within_window():
    text = "AAAA the novel framework BBBB"
    doc = _doc(text)
    idx = text.find("novel framework")
    # offset is 3 chars off; window covers it
    ro, line, col, stale = resolve_anchor(doc, idx + 3, "novel framework")
    assert ro == idx and stale is False


def test_resolve_anchor_far_match_marks_stale_but_finds_it():
    # Anchor moved far away; outside the 200-char window. Whole-doc search
    # should still find it but mark stale=True.
    prefix = "X" * 500
    text = prefix + "\nthe novel framework lives here"
    doc = _doc(text)
    ro, line, col, stale = resolve_anchor(doc, 0, "novel framework")
    assert stale is True
    assert text[ro : ro + len("novel framework")] == "novel framework"


def test_resolve_anchor_truly_missing_text():
    text = "no anchor present"
    doc = _doc(text)
    ro, line, col, stale = resolve_anchor(doc, 0, "nonexistent_phrase_zz")
    assert stale is True


def test_find_headings_recognizes_section():
    text = "\\section{Intro}\nbody\n\\subsection{Sub}\nmore\n"
    starts = build_line_starts(text)
    hs = find_headings(text, starts)
    levels = [(h.text, h.level) for h in hs]
    assert ("Intro", 1) in levels
    assert ("Sub", 2) in levels


def test_find_headings_recognizes_abstract_pseudosection():
    text = (
        "\\title{My Paper}\n"
        "\\begin{abstract}\n"
        "abstract body here\n"
        "\\end{abstract}\n"
        "\\section{Intro}\n"
    )
    starts = build_line_starts(text)
    hs = find_headings(text, starts)
    labels = [h.text for h in hs]
    assert any("Abstract" == lbl for lbl in labels)
    # Title pseudo-section also detected
    assert any(lbl.startswith("Title") for lbl in labels)
    assert "Intro" in labels


def test_nearest_heading_returns_enclosing():
    text = "\\section{Method}\nA\nB\n\\subsection{Sub}\nC\n"
    starts = build_line_starts(text)
    hs = find_headings(text, starts)
    # Line 2 is under Method
    assert nearest_heading(hs, 2) == "Method"
    # Line 5 is under Method > Sub
    assert nearest_heading(hs, 5) == "Method > Sub"


def test_nearest_heading_before_first_returns_none():
    text = "before any heading\n\\section{First}\n"
    starts = build_line_starts(text)
    hs = find_headings(text, starts)
    assert nearest_heading(hs, 1) is None
