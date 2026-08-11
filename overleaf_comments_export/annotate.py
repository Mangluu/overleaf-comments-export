"""Write a copy of the LaTeX source with the comments embedded in it.

Compiling the result gives a PDF that carries the review comments, which is
what https://github.com/overleaf/overleaf/issues/1126 has been asking for.

The whole job is putting text someone typed into a browser into a .tex file
without breaking the build, so most of this module is about escaping and about
choosing a safe place to insert.
"""

from __future__ import annotations

import re
from typing import Iterable, Literal

from .model import AnchoredComment, Thread

AnnotateStyle = Literal["pdfcomment", "todonotes"]

# Characters that mean something to TeX and have to be neutralised. This is one
# translation table applied in a single pass on purpose: replacing them one
# after another would re-escape the braces that the replacements themselves
# introduce, turning \textbackslash{} into \textbackslash\{\}.
_LATEX_SPECIALS = str.maketrans({
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
})

# Typography a reviewer's browser inserts for them, folded to ASCII so the file
# still builds under plain pdflatex without inputenc.
_UNICODE_FOLD = {
    "‘": "`", "’": "'", "“": "``", "”": "''",
    "–": "--", "—": "---", "…": "...", " ": " ",
    "→": "->", "↳": "->", "≥": ">=", "≤": "<=",
    "×": "x", "•": "-", "▸": "", "◂": "",
}

_PREAMBLE = {
    "pdfcomment": "\\usepackage{pdfcomment}",
    "todonotes": "\\usepackage[textsize=footnotesize,color=yellow!40]{todonotes}",
}

_DOCUMENTCLASS_RE = re.compile(r"^[^%\n]*\\documentclass", re.MULTILINE)
_BEGIN_DOC_RE = re.compile(r"^[^%\n]*\\begin\{document\}", re.MULTILINE)


def latex_escape(text: str) -> str:
    """Make arbitrary human text safe to drop into a .tex file."""
    for bad, good in _UNICODE_FOLD.items():
        text = text.replace(bad, good)
    text = text.translate(_LATEX_SPECIALS)
    # A note is a single run of text. Blank lines inside it would start a new
    # paragraph, which TeX will not accept in this position.
    return " ".join(text.split())


def _comment_text(c: AnchoredComment, thread: Thread | None) -> str:
    """The note as it should read in the PDF, including any replies."""
    parts = [f"[{c.short_id}]"]
    if thread and thread.messages:
        ordered = sorted(thread.messages, key=lambda m: m.timestamp_ms)
        first = ordered[0]
        who = first.user_name or first.user_email or "reviewer"
        parts.append(f"{who}: {first.content or ''}")
        for reply in ordered[1:]:
            rwho = reply.user_name or reply.user_email or "reply"
            parts.append(f"| Reply ({rwho}): {reply.content or ''}")
    if thread and thread.resolved:
        parts.append("| resolved")
    return latex_escape(" ".join(p for p in parts if p.strip()))


def _macro(style: AnnotateStyle, body: str, author: str) -> str:
    if style == "todonotes":
        return "\\todo{" + body + "}"
    return "\\pdfcomment[author={" + latex_escape(author) + "}]{" + body + "}"


def _in_math(text: str, pos: int) -> bool:
    """True if `pos` sits inside inline math.

    Counts unescaped dollar signs before it. Odd means we are inside. This
    misses display math written with \\[ \\], which is handled by never
    inserting inside a line that opens one.
    """
    count = 0
    i = 0
    while i < pos:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "$":
            count += 1
        i += 1
    return count % 2 == 1


def _escape_math(text: str, pos: int) -> int:
    """Move `pos` past the end of the inline math it is sitting in."""
    i = pos
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == "$":
            return i + 1
        i += 1
    return len(text)


def _line_bounds(text: str, pos: int) -> tuple[int, int]:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return start, len(text) if end == -1 else end


def _commented_out(text: str, pos: int) -> bool:
    """True if `pos` is after an unescaped % on its line, so anything inserted
    there would be swallowed by a LaTeX comment."""
    start, _ = _line_bounds(text, pos)
    i = start
    while i < pos:
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == "%":
            return True
        i += 1
    return False


def safe_insertion_point(text: str, offset: int, anchored_text: str) -> int:
    """Where to put the note so the file still compiles.

    Prefers just after the phrase the comment was attached to. Steps out of
    inline math, and off the end of a commented-out line, because a note in
    either place breaks the build or vanishes.
    """
    pos = max(0, min(offset, len(text)))
    if anchored_text and text[pos : pos + len(anchored_text)] == anchored_text:
        pos += len(anchored_text)
    if _in_math(text, pos):
        pos = _escape_math(text, pos)
    if _commented_out(text, pos):
        _, end = _line_bounds(text, pos)
        pos = end
    return pos


def inject_preamble(text: str, style: AnnotateStyle) -> tuple[str, bool]:
    """Add the package this style needs. Returns the text and whether it was
    added. A fragment with no preamble of its own is left alone, since the
    package belongs in whichever file pulls it in."""
    package = _PREAMBLE[style]
    if package in text:
        return text, True
    m = _BEGIN_DOC_RE.search(text) or _DOCUMENTCLASS_RE.search(text)
    if not m:
        return text, False
    if _BEGIN_DOC_RE.search(text):
        at = m.start()
        return text[:at] + package + "\n" + text[at:], True
    line_end = text.find("\n", m.end())
    at = len(text) if line_end == -1 else line_end + 1
    return text[:at] + package + "\n" + text[at:], True


def annotate_document(
    text: str,
    comments: Iterable[AnchoredComment],
    threads: dict[str, Thread],
    *,
    style: AnnotateStyle = "pdfcomment",
) -> tuple[str, int]:
    """Return the source with a note at each comment, and how many were placed.

    Insertions run from the end of the document backwards so that each one
    cannot move the offsets of the ones still to come.
    """
    placed: list[tuple[int, str]] = []
    for c in comments:
        thread = threads.get(c.thread_id)
        body = _comment_text(c, thread)
        if not body:
            continue
        author = "reviewer"
        if thread and thread.messages:
            first = min(thread.messages, key=lambda m: m.timestamp_ms)
            author = first.user_name or first.user_email or author
        placed.append(
            (safe_insertion_point(text, c.offset, c.anchored_text),
             _macro(style, body, author))
        )

    # Latest first. Ties keep a stable order so output does not wobble.
    placed.sort(key=lambda p: (-p[0], p[1]))
    out = text
    for pos, macro in placed:
        out = out[:pos] + macro + out[pos:]

    out, _ = inject_preamble(out, style)
    return out, len(placed)
