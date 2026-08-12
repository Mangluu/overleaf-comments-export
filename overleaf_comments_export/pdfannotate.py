"""Put the comments into the PDF Overleaf already built.

Writing LaTeX and compiling it has two costs. It needs a LaTeX installation,
which most people using Overleaf deliberately do not have, and it needs the
whole project, since a paper does not compile without its class file, its
figures, and its bibliography. Overleaf has already done that work, so the
cheaper route is to take the PDF it produced and write the highlights into it
directly. Nothing to install, nothing to compile, and the result is the paper
exactly as it really looks.

The cost is that a PDF has no idea where the LaTeX source went. The commented
words have to be found by searching the rendered text, and a span that cannot
be found is listed on a page at the end rather than being guessed at.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable, Sequence

from .highlight import (
    DONE_COLOUR,
    MULTI_COLOUR,
    REVIEWER_COLOURS,
    Placement,
    _author_of,
    _popup_text,
    _segment_colour,
    assign_colours,
    segment_spans,
)
from .model import AnchoredComment, Thread

logger = logging.getLogger(__name__)

_RGB = {name: tuple(v / 255 for v in rgb)
        for name, rgb in REVIEWER_COLOURS + [MULTI_COLOUR, DONE_COLOUR]}
_RGB.update({f"{name}dark": tuple(v * 0.78 / 255 for v in rgb)
             for name, rgb in REVIEWER_COLOURS})

# Commands whose argument is not printed where it is written.
_DROPPED = re.compile(
    r"\\(?:cite[a-zA-Z]*|ref|cref|Cref|autoref|eqref|label|footnote|index"
    r"|todo|marginpar)\s*(?:\[[^]]*\])?\{[^{}]*\}"
)
# Commands whose argument IS printed, just in a different font.
_KEPT = re.compile(
    r"\\(?:emph|textbf|textit|textsc|texttt|textrm|textsf|text|mbox|underline"
    r"|section|subsection|subsubsection|paragraph|title|caption|abstract)\s*"
    r"\*?\{([^{}]*)\}"
)
_SPLIT = "\x00"
# Shorter than this matches half the paper, and a highlight on the wrong "VR"
# is worse than no highlight.
MIN_KEY = 6


class PdfAnnotationUnavailable(RuntimeError):
    """PyMuPDF is not installed."""


def _require_pymupdf():
    try:
        import pymupdf  # noqa: F401
        return pymupdf
    except ImportError:  # pragma: no cover - exercised by the install, not tests
        raise PdfAnnotationUnavailable(
            "Putting the comments into the PDF needs one extra piece, PyMuPDF.\n\n"
            "Install it with:\n\n"
            "  pip install 'overleaf-comments-export[pdf]'\n\n"
            "Or export the annotated LaTeX instead and compile it on Overleaf."
        )


def rendered_text(source: str) -> str:
    """Roughly what a stretch of LaTeX looks like once it is typeset.

    Anything whose printed form cannot be predicted, maths above all, becomes a
    split marker rather than a guess, so the search keys either side of it stay
    trustworthy.
    """
    s = _DROPPED.sub(f" {_SPLIT} ", source)
    for _ in range(3):                       # \textbf{\emph{x}} nests
        s, n = _KEPT.subn(r"\1", s)
        if not n:
            break
    s = re.sub(r"\$[^$]*\$", f" {_SPLIT} ", s)
    s = re.sub(r"\\\\|\\[a-zA-Z]+\s*(?:\[[^]]*\])?", f" {_SPLIT} ", s)
    s = s.replace("~", " ")
    s = re.sub(r"\\([&%$#_{}])", r"\1", s)
    s = re.sub(r"[{}]", " ", s)
    return s


def search_keys(source: str) -> list[str]:
    """Searchable runs of printed text, longest first."""
    parts = (re.sub(r"\s+", " ", p).strip() for p in rendered_text(source).split(_SPLIT))
    return sorted({p for p in parts if len(p) >= MIN_KEY}, key=len, reverse=True)


@dataclass
class Hit:
    page: int
    quads: list
    cursor: tuple[int, int]   # where to carry on looking from


def _canonical(s: str) -> str:
    """Letters only, lowercased.

    Typesetting inserts hyphens at line breaks and takes the spaces out, so
    comparing on the letters alone is the only form that survives the journey
    from source to page. `force-feedback` broken as `force-` and `feedback`
    then reads the same either way.
    """
    return re.sub(r"[^0-9a-z]+", "", s.lower())


def _page_index(page) -> tuple[str, list[tuple[int, int, int, object]]]:
    """The page as one comparable string, with a way back to the rectangles.

    Returns the canonical text and, for each word, where it sits in that string
    together with its line and its box.
    """
    out: list[str] = []
    spans: list[tuple[int, int, int, object]] = []
    pos = 0
    for x0, y0, x1, y1, word, block, line, _no in page.get_text("words"):
        c = _canonical(word)
        if not c:
            continue
        import pymupdf

        spans.append((pos, pos + len(c), block * 1000 + line, pymupdf.Rect(x0, y0, x1, y1)))
        out.append(c)
        pos += len(c)
    return "".join(out), spans


def _quads_for(spans, start: int, end: int) -> list:
    """One rectangle per line of text covered, rather than one box around the
    lot, which on a two-column page would swallow the other column."""
    by_line: dict[int, object] = {}
    for s, e, line, rect in spans:
        if s < end and e > start:
            by_line[line] = rect if line not in by_line else by_line[line] | rect
    return [r.quad for _, r in sorted(by_line.items())]


def context_key(text: str, start: int, end: int, reach: int = 200) -> tuple[str, int] | None:
    """A key long enough to find, for a span too short to search for on its own.

    A comment on one word like "VR" cannot be located by that word, which
    occurs on every page. Reading on past the span gives something unique to
    search for, and only the first part of what is found gets marked.
    """
    want = _canonical(_strip(text[start:end]))
    if not want:
        return None
    run = rendered_text(text[start:end + reach]).split(_SPLIT)[0]
    key = re.sub(r"\s+", " ", run).strip()
    if len(_canonical(key)) < MIN_KEY or not _canonical(key).startswith(want):
        return None
    return key, len(want)


def _strip(source: str) -> str:
    return re.sub(r"\s+", " ", rendered_text(source).replace(_SPLIT, " ")).strip()


def _locate(doc, index, keys: Sequence[str], expected_page: int, cursor: tuple[int, int],
            mark_len: int | None = None) -> Hit | None:
    """Find a span in the PDF.

    A phrase can occur many times, and "we crossed three" is not rare in a
    paper about crossing three things. What makes the right one identifiable is
    that comments are handled in the order they appear in the source, and the
    typeset page follows the same order, so the first match at or after the
    last one placed is the one meant. The page the source offset points at only
    breaks ties when nothing lies ahead, which happens when a phrase moved or
    the estimate was off.
    """
    for key in keys:
        needle = _canonical(key)
        if len(needle) < MIN_KEY:
            continue
        found: list[tuple[int, int]] = []
        for number, (text, _spans) in index.items():
            at = text.find(needle)
            while at != -1:
                found.append((number, at))
                at = text.find(needle, at + 1)
        if not found:
            continue
        # Anything before the last comment placed is a different occurrence of
        # the phrase, so drop those; among the rest take whichever is nearest
        # the page the source offset points at.
        ahead = [f for f in found if f >= cursor]
        number, at = min(ahead or found, key=lambda f: (abs(f[0] - expected_page), f))
        end = at + (mark_len or len(needle))
        return Hit(number, _quads_for(index[number][1], at, end), (number, end))
    return None


def annotate_pdf(
    pdf_bytes: bytes,
    sources: dict[str, str] | str,
    comments: Iterable[AnchoredComment],
    threads: dict[str, Thread],
) -> tuple[bytes, list[Placement]]:
    """Return the PDF with the comments in it, and what happened to each one.

    `sources` maps document id to that document's LaTeX. A paper is usually
    written across several files but built into one PDF, so every file that
    carries a comment is matched against the same pages. Passing a single
    string is accepted for the one-file case.
    """
    pymupdf = _require_pymupdf()
    comments = list(comments)
    colours = assign_colours(comments, threads)
    if isinstance(sources, str):
        sources = {c.doc_id: sources for c in comments}

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    placements: dict[str, Placement] = {}
    n_pages = doc.page_count
    index = {p.number: _page_index(p) for p in doc}

    by_doc: dict[str, list[AnchoredComment]] = {}
    for c in comments:
        by_doc.setdefault(c.doc_id, []).append(c)

    # Each file gets its own search position, since one file's order says
    # nothing about where another one was pulled into the document.
    for doc_id in sorted(by_doc, key=lambda d: (by_doc[d][0].pathname, d)):
        text = sources.get(doc_id)
        if text is None:
            for c in by_doc[doc_id]:
                placements[c.short_id] = Placement(c, False, "its source was not exported")
            continue
        _mark_one_source(doc, index, n_pages, text, by_doc[doc_id], threads,
                         colours, placements)

    for c in comments:
        placements.setdefault(c.short_id, Placement(c, False, "could not be found in the PDF"))
    ordered = [placements[c.short_id] for c in comments]
    _append_listing(doc, ordered, threads, colours)
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return out, ordered


def _mark_one_source(doc, index, n_pages, text, comments, threads, colours, placements) -> None:
    """Highlight every comment belonging to one source file."""
    spans: list[tuple[int, int, AnchoredComment]] = []
    for c in comments:
        anchored = c.anchored_text or ""
        if not anchored or text[c.offset:c.offset + len(anchored)] != anchored:
            placements[c.short_id] = Placement(c, False, "the text it was on has changed")
            continue
        spans.append((c.offset, c.offset + len(anchored), c))

    cursor = (0, 0)
    for seg in segment_spans(spans):
        body = text[seg.start:seg.end]
        keys = search_keys(body)
        # Where in the document this is, as a page number.
        expected = min(n_pages - 1, int(seg.start / max(1, len(text)) * n_pages))
        hit = None
        if keys:
            hit = _locate(doc, index, keys, expected, cursor)
        if hit is None:
            extended = context_key(text, seg.start, seg.end)
            if extended:
                key, mark_len = extended
                hit = _locate(doc, index, [key], expected, cursor, mark_len=mark_len)
        if hit is None and not keys:
            for c in seg.comments:
                placements.setdefault(c.short_id, Placement(c, False, "nothing printable to mark"))
            continue
        if hit is None:
            for c in seg.comments:
                placements.setdefault(
                    c.short_id, Placement(c, False, "could not be found in the PDF"))
            continue

        # Only ever forwards. One match in the wrong place would otherwise
        # drag the search back and take every comment after it with it.
        cursor = max(cursor, hit.cursor)
        colour, kind = _segment_colour(seg, threads, colours)
        _, who = _author_of(seg.comments[0], threads)
        if len({_author_of(c, threads)[0] for c in seg.comments}) > 1:
            who = "several reviewers"
        page = doc[hit.page]
        annot = (page.add_strikeout_annot(hit.quads) if kind == "StrikeOut"
                 else page.add_highlight_annot(hit.quads))
        annot.set_colors(stroke=_RGB.get(colour, _RGB["ocehlA"]))
        annot.set_info(title=who, content=_popup_text_plain(seg.comments, threads))
        annot.set_opacity(0.4)
        annot.update()
        for c in seg.comments:
            placements[c.short_id] = Placement(c, True, page=hit.page + 1)


def _popup_text_plain(comments: Sequence[AnchoredComment], threads: dict[str, Thread]) -> str:
    """The same popup text as the LaTeX route, left exactly as written.

    A PDF string is not TeX. Escaping it would show the backslashes, and
    folding it to ASCII would spell a reviewer's name wrong.
    """
    return _popup_text(comments, threads, escape=lambda s: s)


def _append_listing(doc, placements, threads, colours) -> None:
    """A page listing every comment.

    Annotations do not print, and a printed copy that silently loses every
    comment is worse than useless to someone working through them on paper.
    """
    import pymupdf

    lines: list[str] = []
    for p in placements:
        c = p.comment
        _, who = _author_of(c, threads)
        where = c.nearest_heading or c.pathname
        note = (f"page {p.page}" if p.highlighted
                else f"not marked on the page, {p.reason}")
        body = _popup_text_plain([c], threads).split("] ", 1)[-1]
        if body.startswith(f"{who}: "):      # the line above already names them
            body = body[len(who) + 2:]
        lines.append(f"{c.short_id}  {who}  ({note})  -  {where}\n    {body}")

    width, height = pymupdf.paper_size("a4")
    margin, top, bottom = 56, 50, height - 40
    # An entry needs room to be worth starting; below this, turn the page.
    least = 34
    page = y = None

    def new_page():
        nonlocal page, y
        page = doc.new_page(width=width, height=height)
        if y is None:
            page.insert_text((margin, top), "Review comments", fontsize=15, fontname="hebo")
            y = top + 20
        else:
            y = top

    new_page()
    for line in lines:
        for attempt in range(3):
            if y > bottom - least:
                new_page()
            box = pymupdf.Rect(margin, y, width - margin, bottom)
            left = page.insert_textbox(box, line + "\n", fontsize=8.5, fontname="helv")
            if left >= 0:
                y = bottom - left + 6
                break
            # Did not fit. Once on a fresh page, so a very long comment that
            # cannot fit anywhere is trimmed rather than dropped or crashed on.
            if attempt == 0:
                y = bottom                        # force a fresh page
            elif attempt == 1:
                line = line[:1200] + " [...]"
        else:
            logger.warning("A comment was too long for the listing and was cut short.")
