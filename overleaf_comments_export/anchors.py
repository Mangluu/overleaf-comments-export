from __future__ import annotations

from bisect import bisect_right

from .model import DocText


def build_line_starts(text: str) -> list[int]:
    """line_starts[i] = char offset where line (i+1) starts. So
    bisect_right(line_starts, offset) gives the 1-indexed line number."""
    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)
    return starts


def offset_to_line_col(line_starts: list[int], offset: int) -> tuple[int, int]:
    """Convert a flat character offset into a 1-indexed (line, column).
    Column is 0-indexed (chars after the line start)."""
    if offset < 0:
        offset = 0
    line_no = bisect_right(line_starts, offset)
    if line_no <= 0:
        line_no = 1
    col = offset - line_starts[line_no - 1]
    return line_no, col


def resolve_anchor(
    doc: DocText, offset: int, anchored_text: str, search_window: int = 200
) -> tuple[int, int, int, bool]:
    """Map an offset+expected-text anchor to (resolved_offset, line, col, stale).

    If text[offset:offset+len(anchored_text)] matches anchored_text, we trust it.
    Otherwise, search +/- search_window characters for the anchored text and
    re-anchor. If still not found, return the original offset's coords and
    mark stale=True."""
    text = doc.text
    n = len(anchored_text)
    if n > 0 and 0 <= offset <= len(text) - n and text[offset : offset + n] == anchored_text:
        line, col = offset_to_line_col(doc.line_starts, offset)
        return offset, line, col, False

    if n > 0:
        # Nearby search
        lo = max(0, offset - search_window)
        hi = min(len(text), offset + search_window + n)
        idx = text.find(anchored_text, lo, hi)
        if idx != -1:
            line, col = offset_to_line_col(doc.line_starts, idx)
            return idx, line, col, False
        # Last-resort whole-document search; mark stale (since it moved far)
        # but still produce a usable line/col rather than guessing.
        idx = text.find(anchored_text)
        if idx != -1:
            line, col = offset_to_line_col(doc.line_starts, idx)
            return idx, line, col, True

    # The bounded offset, not the one Overleaf gave us. --include-source
    # promises that `offset` indexes into the files in source/, and a stale
    # anchor whose text was deleted can carry an offset past the end, which
    # slices to nothing and silently reads as "no context here".
    safe = min(max(offset, 0), max(0, len(text) - 1))
    line, col = offset_to_line_col(doc.line_starts, safe)
    return safe, line, col, True
