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


def test_a_comment_on_a_position_is_not_stale():
    """Overleaf lets a comment attach to a point rather than a selection, and
    sends those with no anchored text. Nothing has moved and there is nothing
    to check against, so calling them stale is a false alarm. One real paper
    had 74 of 131 comments flagged that way when none of them had moved, which
    hides the ones that genuinely did."""
    from overleaf_comments_export.anchors import build_line_starts, resolve_anchor
    from overleaf_comments_export.model import DocText

    text = "\\section{Method}\nWe crossed three sensory environments.\n"
    doc = DocText(doc_id="d", pathname="p.tex", text=text,
                  line_starts=build_line_starts(text), headings=[])

    at = text.index("three")
    offset, line, col, stale = resolve_anchor(doc, at, "")
    assert stale is False, "an empty anchor was reported as stale"
    assert offset == at, "the position was moved even though nothing was wrong"
    assert line == 2


def test_an_empty_anchor_beyond_the_file_is_still_bounded():
    from overleaf_comments_export.anchors import build_line_starts, resolve_anchor
    from overleaf_comments_export.model import DocText

    text = "short\n"
    doc = DocText(doc_id="d", pathname="p.tex", text=text,
                  line_starts=build_line_starts(text), headings=[])
    offset, _, _, stale = resolve_anchor(doc, 9999, "")
    assert 0 <= offset < len(text)
    assert stale is False


def test_text_that_really_moved_is_still_stale():
    """The fix must not stop reporting the ones that matter."""
    from overleaf_comments_export.anchors import build_line_starts, resolve_anchor
    from overleaf_comments_export.model import DocText

    text = "alpha beta gamma\n"
    doc = DocText(doc_id="d", pathname="p.tex", text=text,
                  line_starts=build_line_starts(text), headings=[])
    _, _, _, stale = resolve_anchor(doc, 0, "text that is gone")
    assert stale is True
