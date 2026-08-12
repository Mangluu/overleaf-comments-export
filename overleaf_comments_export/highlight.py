"""Highlight the commented text itself, with the comment attached to it.

A note floating in the margin, or a pin sitting at a point, does not tell you
*which words* were being talked about. Highlighting the span does, and PDF
supports it natively: a text markup annotation carries a popup, so hovering the
highlight shows the comment.

Two things make this harder than it sounds.

`soul`, which pdfcomment uses to draw markup across line breaks, cannot nest.
Two comments on overlapping text cannot simply be wrapped one inside the other,
so the text is cut into disjoint segments first and each segment is wrapped
once, carrying every comment that covers it.

And soul reconstructs the text it highlights, so it fails on anything that is
not plain words. Those spans fall back to a pin at the start, and are listed at
the end of the document so nothing is silently lost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .annotate import latex_escape, safe_insertion_point, to_ascii
from .model import AnchoredComment, Thread

# Distinct, light enough to read black text through, and distinguishable for
# the most common colour vision deficiencies.
REVIEWER_COLOURS = [
    ("ocehlA", (255, 236, 140)),   # warm yellow
    ("ocehlB", (160, 225, 255)),   # light blue
    ("ocehlC", (185, 240, 190)),   # light green
    ("ocehlD", (240, 200, 255)),   # light purple
    ("ocehlE", (255, 215, 165)),   # light orange
    ("ocehlF", (200, 230, 230)),   # pale teal
]
MULTI_COLOUR = ("ocehlMulti", (255, 180, 170))   # more than one person here
DONE_COLOUR = ("ocehlDone", (215, 215, 215))     # resolved

# A span longer than this is more likely to be a mis-anchored comment than a
# real quotation, and highlighting half a page helps nobody.
MAX_SPAN = 600

# Characters that mean the span cannot be handed to soul as plain text.
_UNSAFE = set("\\%$&{}#~^")


@dataclass
class Placement:
    """One comment, and what we managed to do with it."""
    comment: AnchoredComment
    highlighted: bool
    reason: str = ""
    page: int | None = None   # 1-based, when it went into a PDF


@dataclass
class Segment:
    start: int
    end: int
    comments: list[AnchoredComment] = field(default_factory=list)


def _author_of(c: AnchoredComment, threads: dict[str, Thread]) -> tuple[str, str]:
    """(stable key, display name). Keyed on user id, because Overleaf shows the
    same person under different names once they change their profile."""
    t = threads.get(c.thread_id)
    if t and t.messages:
        first = min(t.messages, key=lambda m: m.timestamp_ms)
        return (first.user_id or first.user_name or "?",
                first.user_name or first.user_email or "reviewer")
    return ("?", "reviewer")


def assign_colours(
    comments: Sequence[AnchoredComment], threads: dict[str, Thread]
) -> dict[str, str]:
    """A colour per person, stable between runs and independent of order."""
    keys = sorted({_author_of(c, threads)[0] for c in comments})
    return {k: REVIEWER_COLOURS[i % len(REVIEWER_COLOURS)][0]
            for i, k in enumerate(keys)}


def segment_spans(spans: list[tuple[int, int, AnchoredComment]]) -> list[Segment]:
    """Cut overlapping spans into disjoint segments.

    Every boundary of every span becomes a cut point, so a segment is covered
    by a fixed set of comments. This is what lets two comments share text
    without nesting, which soul cannot do.
    """
    if not spans:
        return []
    edges = sorted({e for s, t, _ in spans for e in (s, t)})
    out: list[Segment] = []
    for start, end in zip(edges, edges[1:]):
        covering = [c for s, t, c in spans if s < end and t > start]
        if covering:
            out.append(Segment(start, end, covering))
    return out


def span_is_safe(text: str, start: int, end: int) -> tuple[bool, str]:
    """Whether this stretch of source can be wrapped in a markup macro."""
    if end <= start:
        return False, "the span is empty"
    body = text[start:end]
    if not body.strip():
        return False, "the span is only whitespace"
    if len(body) > MAX_SPAN:
        return False, "the span is too long to highlight"
    if "\n\n" in body or "\r\n\r\n" in body:
        return False, "the span crosses a paragraph break"
    bad = _UNSAFE.intersection(body)
    if bad:
        if "$" in bad:
            return False, "the span contains maths"
        if "\\" in bad:
            return False, "the span contains a LaTeX command"
        if "%" in bad:
            return False, "the span contains a percent sign"
        return False, "the span contains LaTeX syntax"
    return True, ""


# Below this a partial highlight is more distracting than helpful, and the
# comment is better served by a pin.
MIN_TRIM = 12

# Arguments that LaTeX writes out to a file and reads back, for a contents
# page, a running head, or a list of figures. Markup put inside one of these
# travels with it and breaks on the way back, so a comment on a heading gets a
# pin beside it instead.
_FRAGILE = ("section", "subsection", "subsubsection", "paragraph",
            "subparagraph", "caption", "title", "thanks", "footnote", "chapter")


def in_fragile_argument(text: str, pos: int, limit: int = 400) -> bool:
    """Whether this position sits inside the braces of a heading or a caption."""
    depth = 0
    i = pos - 1
    stop = max(0, pos - limit)
    while i >= stop:
        ch = text[i]
        if ch in "{}" and (i == 0 or text[i - 1] != "\\"):
            if ch == "}":
                depth += 1
            elif depth:
                depth -= 1
            else:
                head = text[max(0, i - 20):i]
                name = re.search(r"\\([a-zA-Z]+)\*?$", head)
                return bool(name and name.group(1) in _FRAGILE)
        i -= 1
    return False


def trim_to_safe(text: str, start: int, end: int) -> tuple[int, int] | None:
    """The longest stretch inside this span that can be highlighted.

    Reviewers comment on maths and on commands constantly, and refusing the
    whole span for one `$x$` in the middle of a sentence loses the one thing a
    highlight is for, showing which words are meant. So take the longest run of
    ordinary text within the span instead of nothing at all.
    """
    body = text[start:end]
    best: tuple[int, int] | None = None
    run = 0
    for i, ch in enumerate(body + "\0"):
        if ch not in _UNSAFE and ch != "\0" and not body.startswith("\n\n", i):
            run += 1
            continue
        if run:
            s, e = start + i - run, start + i
            # Whole words only, or the highlight starts mid-word and reads as
            # a mistake.
            while s < e and not text[s].isspace() and s > start and not text[s - 1].isspace():
                s += 1
            while e > s and not text[e - 1].isspace() and e < end and not text[e].isspace():
                e -= 1
            if e - s >= MIN_TRIM and text[s:e].strip() and (best is None or e - s > best[1] - best[0]):
                best = (s, e)
        run = 0
    if best is None:
        return None
    s, e = best
    s += len(text[s:e]) - len(text[s:e].lstrip())
    e -= len(text[s:e]) - len(text[s:e].rstrip())
    if e - s > MAX_SPAN:
        # A comment on a whole paragraph. Mark its opening sentence rather than
        # colouring half a page, which is what the reader needs to find it.
        window = text[s:s + MAX_SPAN]
        cut = max(window.rfind(". "), window.rfind("? "), window.rfind("! "))
        e = s + (cut + 1 if cut >= MIN_TRIM else window.rfind(" "))
    if in_fragile_argument(text, s):
        return None
    ok, _ = span_is_safe(text, s, e)
    return (s, e) if ok else None


def _popup_text(comments: Sequence[AnchoredComment], threads: dict[str, Thread],
                escape=latex_escape) -> str:
    """What the reader sees on hover. Self-identifying, because most PDF
    readers paint every popup the same colour whatever the annotation says.

    `escape` is how the text is made safe for wherever it is going. Writing
    into LaTeX means escaping and folding to ASCII. Writing into a PDF means
    neither, and doing it anyway would turn Muller into Muller and Soren into
    a question mark.
    """
    parts: list[str] = []
    if len(comments) > 1:
        parts.append(f"{len(comments)} comments on this text.")
    for c in comments:
        t = threads.get(c.thread_id)
        _, who = _author_of(c, threads)
        state = "RESOLVED. " if (t and t.resolved) else ""
        body = ""
        if t and t.messages:
            ordered = sorted(t.messages, key=lambda m: m.timestamp_ms)
            body = ordered[0].content or ""
            for reply in ordered[1:]:
                rname = reply.user_name or reply.user_email or "reply"
                body += f" | Reply ({rname}): {reply.content or ''}"
        parts.append(f"[{c.short_id}] {state}{who}: {body}")
    return escape(" ".join(parts))


def _segment_colour(
    seg: Segment, threads: dict[str, Thread], colours: dict[str, str]
) -> tuple[str, str]:
    """(colour name, markup kind) for a segment.

    One person, one comment  -> their colour.
    One person, several      -> their colour, darkened, so doubling is visible.
    Several people           -> the shared colour, since no single person owns it.
    All resolved             -> grey, struck through.
    """
    if all((threads.get(c.thread_id) and threads[c.thread_id].resolved)
           for c in seg.comments):
        return DONE_COLOUR[0], "StrikeOut"
    live = [c for c in seg.comments
            if not (threads.get(c.thread_id) and threads[c.thread_id].resolved)]
    keys = {_author_of(c, threads)[0] for c in live}
    if len(keys) > 1:
        return MULTI_COLOUR[0], "Highlight"
    key = next(iter(keys))
    base = colours.get(key, REVIEWER_COLOURS[0][0])
    if len(live) > 1:
        return base + "dark", "Highlight"
    return base, "Highlight"


def colour_definitions(colours: dict[str, str]) -> str:
    """The xcolor definitions the document needs, including the darker shade
    used when one person comments twice on the same words."""
    lines = []
    for name, (r, g, b) in REVIEWER_COLOURS + [MULTI_COLOUR, DONE_COLOUR]:
        lines.append(f"\\definecolor{{{name}}}{{RGB}}{{{r},{g},{b}}}")
        if name.startswith("ocehl") and name not in (MULTI_COLOUR[0], DONE_COLOUR[0]):
            dr, dg, db = (max(0, int(v * 0.78)) for v in (r, g, b))
            lines.append(f"\\definecolor{{{name}dark}}{{RGB}}{{{dr},{dg},{db}}}")
    return "\n".join(lines)


def legend(colours: dict[str, str], names: dict[str, str]) -> str:
    """A key, so a reader knows whose colour is whose without being told."""
    if not colours:
        return ""
    swatches = []
    for key, colour in sorted(colours.items(), key=lambda kv: names.get(kv[0], "")):
        who = latex_escape(names.get(key, "reviewer"))
        swatches.append(f"\\colorbox{{{colour}}}{{\\strut~{who}~}}")
    swatches.append(f"\\colorbox{{{MULTI_COLOUR[0]}}}{{\\strut~more than one comment~}}")
    swatches.append(f"\\colorbox{{{DONE_COLOUR[0]}}}{{\\strut~resolved~}}")
    return (
        "\\begin{center}\\fbox{\\parbox{0.92\\linewidth}{\\small\n"
        "\\textbf{Review comments.} Highlighted text carries a comment. "
        "Click or hover a highlight to read it. Every comment is also listed "
        "at the end of this document.\\\\[3pt]\n"
        + " \\quad ".join(swatches)
        + "\n}}\\end{center}\n"
    )


def summary(placements: Sequence[Placement], threads: dict[str, Thread]) -> str:
    """Every comment, in order, including any that could not be highlighted.

    PDF readers do not print annotations, so without this the printed paper
    would carry no comments at all.
    """
    if not placements:
        return ""
    rows = []
    for p in placements:
        c = p.comment
        _, who = _author_of(c, threads)
        t = threads.get(c.thread_id)
        body = ""
        if t and t.messages:
            ordered = sorted(t.messages, key=lambda m: m.timestamp_ms)
            body = ordered[0].content or ""
            for reply in ordered[1:]:
                rname = reply.user_name or reply.user_email or "reply"
                body += f" \\emph{{Reply, {latex_escape(rname)}:}} {latex_escape(reply.content or '')}"
        where = latex_escape(c.nearest_heading or "")
        quote = latex_escape((c.anchored_text or "").strip()[:120])
        note = "" if p.highlighted else f" \\textbf{{Not highlighted:}} {latex_escape(p.reason)}."
        state = " \\textbf{Resolved.}" if (t and t.resolved) else ""
        rows.append(
            f"\\item[{latex_escape(c.short_id)}] {latex_escape(who)}"
            + (f", {where}" if where else "")
            + (f". On \\emph{{``{quote}''}}" if quote else "")
            + f".{state}{note}\\\\\n{latex_escape(body) if not body.startswith(' ') else body}"
        )
    return (
        "\n\\clearpage\n\\section*{Review comments}\n"
        "\\addcontentsline{toc}{section}{Review comments}\n"
        "\\begin{description}\n" + "\n".join(rows) + "\n\\end{description}\n"
    )


def markup_macro(colour: str, kind: str, author: str, body: str, quoted: str) -> str:
    return (
        f"\\pdfmarkupcomment[markup={kind},color={colour},"
        f"author={{{latex_escape(author)}}}]{{{quoted}}}{{{body}}}"
    )


def pin_macro(author: str, body: str, colour: str = "") -> str:
    """A note at a point, for a comment whose text cannot be highlighted.

    Carries the writer's colour like a highlight does, so a comment on a
    section heading still reads as theirs.
    """
    opts = f"author={{{latex_escape(author)}}},icon=Comment"
    if colour:
        opts += f",color={colour}"
    # The icon is drawn with no width of its own, so without the space after it
    # the next word is printed on top of it.
    return f"\\pdfcomment[{opts}]{{{body}}}\\hspace{{1.1em}}"


def apply_highlights(
    text: str,
    comments: Iterable[AnchoredComment],
    threads: dict[str, Thread],
) -> tuple[str, list[Placement]]:
    """Wrap each commented span, and pin whatever cannot be wrapped.

    Returns the new source and what happened to every comment.
    """
    comments = list(comments)
    colours = assign_colours(comments, threads)

    spans: list[tuple[int, int, AnchoredComment]] = []
    placements: dict[str, Placement] = {}
    unplaced: list[AnchoredComment] = []

    for c in comments:
        anchored = c.anchored_text or ""
        start = c.offset
        end = start + len(anchored)
        if not anchored or text[start:end] != anchored:
            # The text moved or was never recorded. There is nothing to wrap,
            # and guessing a position drops the note into whatever happens to
            # be at that offset, so this one is only listed at the end.
            placements[c.short_id] = Placement(c, False, "the text it was on has changed")
            continue
        spans.append((start, end, c))

    segments = segment_spans(spans)

    # Every change to the text, as (start, end, replacement). A pin is an
    # insertion, so start == end. They are collected against the ORIGINAL
    # offsets and applied together from the end backwards, because applying
    # them in two passes leaves the second pass working from stale positions,
    # which once put a pin inside another comment's popup.
    edits: list[tuple[int, int, str]] = []
    covered: list[tuple[int, int]] = []

    for seg in segments:
        ok, reason = span_is_safe(text, seg.start, seg.end)
        mark_start, mark_end, partial = seg.start, seg.end, False
        if not ok:
            trimmed = trim_to_safe(text, seg.start, seg.end)
            if trimmed is None:
                for c in seg.comments:
                    if c.short_id not in placements or placements[c.short_id].highlighted:
                        placements[c.short_id] = Placement(c, False, reason)
                        if c not in unplaced:
                            unplaced.append(c)
                continue
            mark_start, mark_end = trimmed
            partial = True
        colour, kind = _segment_colour(seg, threads, colours)
        _, who = _author_of(seg.comments[0], threads)
        if len({_author_of(c, threads)[0] for c in seg.comments}) > 1:
            who = "several reviewers"
        body = _popup_text(seg.comments, threads)
        if partial:
            # Say so, rather than let the reader think the comment was only
            # about the part we could colour.
            body = latex_escape("(The comment covers a little more than is "
                                "highlighted here.) ") + body
        quoted = to_ascii(text[mark_start:mark_end])
        edits.append((mark_start, mark_end,
                      markup_macro(colour, kind, who, body, quoted)))
        covered.append((mark_start, mark_end))
        for c in seg.comments:
            placements.setdefault(c.short_id, Placement(c, True))

    # A span we could not highlight still gets a pin next to it, so it is
    # visible in the PDF and not only in the list at the end.
    for c in unplaced:
        key, who = _author_of(c, threads)
        pos = safe_insertion_point(text, min(c.offset, len(text)), "")
        # Never land inside a stretch that is about to be replaced.
        for start, end in covered:
            if start < pos < end:
                pos = end
        t = threads.get(c.thread_id)
        pin_colour = DONE_COLOUR[0] if (t and t.resolved) else colours.get(key, "")
        edits.append((pos, pos,
                      pin_macro(who, _popup_text([c], threads), pin_colour)))

    for start, end, replacement in sorted(edits, key=lambda e: (-e[0], -e[1])):
        text = text[:start] + replacement + text[end:]

    ordered = [placements[c.short_id] for c in comments if c.short_id in placements]
    return text, ordered
