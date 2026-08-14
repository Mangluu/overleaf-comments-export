from __future__ import annotations

import re
from bisect import bisect_right

from .model import Float, Heading

# Standard LaTeX sectioning commands.
_HEADING_RE = re.compile(
    r"^\s*\\(?P<cmd>section|subsection|subsubsection|chapter|paragraph|part)\*?\s*"
    r"(?:\[[^\]]*\])?\s*\{(?P<text>.*?)\}",
    re.MULTILINE,
)

# Front-matter / pseudo-sections so comments inside the abstract or near the
# title aren't lumped under "no enclosing section".
_PSEUDO_RE = re.compile(
    r"^\s*\\(?:begin\{(?P<env>abstract|titlepage)\}|"
    r"(?P<cmd>title|maketitle|tableofcontents|frontmatter|mainmatter|backmatter|appendix))"
    r"(?:\s*\{(?P<arg>[^}]*)\})?",
    re.MULTILINE,
)

_LEVEL = {
    "part": -1,
    "chapter": 0,
    "section": 1,
    "subsection": 2,
    "subsubsection": 3,
    "paragraph": 4,
}

_PSEUDO_LEVEL = 1  # treat front-matter pseudo-sections at section level


def find_headings(text: str, line_starts: list[int]) -> list[Heading]:
    """Scan LaTeX source for headings, including title/abstract pseudo-sections.

    line_starts[i] is the char offset of the start of line (i+1); used to
    convert match offsets back into 1-indexed line numbers.
    """
    headings: list[Heading] = []

    for m in _HEADING_RE.finditer(text):
        line_no = bisect_right(line_starts, m.start())
        cmd = m.group("cmd")
        headings.append(
            Heading(line_no=line_no, level=_LEVEL.get(cmd, 99), text=m.group("text").strip())
        )

    for m in _PSEUDO_RE.finditer(text):
        line_no = bisect_right(line_starts, m.start())
        env = m.group("env")
        cmd = m.group("cmd")
        arg = (m.group("arg") or "").strip()
        if env == "abstract":
            label = "Abstract"
        elif env == "titlepage":
            label = "Title page"
        elif cmd == "title":
            label = f"Title: {arg}" if arg else "Title"
        elif cmd == "maketitle":
            label = "Title block"
        elif cmd == "tableofcontents":
            label = "Table of contents"
        elif cmd == "frontmatter":
            label = "Front matter"
        elif cmd == "mainmatter":
            label = "Main matter"
        elif cmd == "backmatter":
            label = "Back matter"
        elif cmd == "appendix":
            label = "Appendix"
        else:
            continue
        headings.append(Heading(line_no=line_no, level=_PSEUDO_LEVEL, text=label))

    headings.sort(key=lambda h: (h.line_no, h.level))
    return headings


def nearest_heading(headings: list[Heading], line_no: int) -> str | None:
    """Return a path like "§ 3.2 Method overview" for the nearest enclosing
    heading at-or-above line_no."""
    enclosing: dict[int, Heading] = {}
    for h in headings:
        if h.line_no > line_no:
            break
        enclosing[h.level] = h
        for deeper in list(enclosing):
            if deeper > h.level:
                enclosing.pop(deeper)
    if not enclosing:
        return None
    parts = [enclosing[lvl].text for lvl in sorted(enclosing)]
    return " > ".join(parts)


# Floats, so a comment on a caption says "Figure 3" rather than a line number.
# `figure*` and `table*` share their counter with the unstarred form, which is
# why the star is stripped rather than treated as a separate kind.
_FLOAT_BEGIN_RE = re.compile(r"\\begin\{(figure|table)\*?\}")
_FLOAT_END_RE = re.compile(r"\\end\{(figure|table)\*?\}")
# Nested floats do exist: subfigure inside figure, and a table inside a figure.
_ANY_BEGIN_RE = re.compile(r"\\begin\{(figure|table|subfigure|subtable)\*?\}")
_ANY_END_RE = re.compile(r"\\end\{(figure|table|subfigure|subtable)\*?\}")
_CAPTION_RE = re.compile(r"\\caption\*?\s*(?:\[[^\]]*\])?\s*\{")
_LABEL_RE = re.compile(r"\\label\s*\{([^}]*)\}")


def _commented_out(text: str, pos: int) -> bool:
    """True when this position sits after an unescaped % on its line."""
    start = text.rfind("\n", 0, pos) + 1
    i = start
    while i < pos:
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == "%":
            return True
        i += 1
    return False


def _balanced_argument(text: str, open_brace: int) -> str:
    """The text inside a {...} that starts here, respecting nesting."""
    depth = 0
    i = open_brace
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace + 1:i]
        i += 1
    return text[open_brace + 1:]


def find_floats(text: str, line_starts: list[int]) -> list[Float]:
    """Every figure and table in the source, numbered as LaTeX would.

    Only captioned floats take a number, because LaTeX only steps the counter
    when there is a caption. An uncaptioned float still gets recorded, so a
    comment inside one can say it is in a figure even when it cannot say which.
    """
    floats: list[Float] = []
    counters = {"figure": 0, "table": 0}

    for m in _FLOAT_BEGIN_RE.finditer(text):
        if _commented_out(text, m.start()):
            continue
        if any(f.start < m.start() < f.end for f in floats):
            continue          # a float inside a float: the outer one wins
        kind = m.group(1)
        end = _matching_end(text, m.end())
        body = text[m.end():end]
        caption, label = _caption_and_label(body)
        if caption is not None:
            counters[kind] += 1
        floats.append(Float(
            kind=kind,
            number=counters[kind] if caption is not None else None,
            caption=caption,
            label=label,
            start=m.start(),
            end=end,
            line_no=bisect_right(line_starts, m.start()),
        ))
    return floats


def _matching_end(text: str, after_begin: int) -> int:
    """Where this float closes, counting nested floats on the way."""
    depth = 1
    i = after_begin
    while i < len(text):
        nxt_begin = _ANY_BEGIN_RE.search(text, i)
        nxt_end = _ANY_END_RE.search(text, i)
        if not nxt_end:
            return len(text)
        if nxt_begin and nxt_begin.start() < nxt_end.start():
            depth += 1
            i = nxt_begin.end()
            continue
        depth -= 1
        if depth == 0:
            return nxt_end.end()
        i = nxt_end.end()
    return len(text)


def _caption_and_label(body: str) -> tuple[str | None, str | None]:
    """The float's own caption and label, ignoring any belonging to something
    nested inside it. A subfigure has its own caption, and a table inside a
    figure has one too, and neither is the caption of the float we are naming."""
    nested: list[tuple[int, int]] = []
    for m in _ANY_BEGIN_RE.finditer(body):
        nested.append((m.start(), _matching_end(body, m.end())))

    def outside_nested(pos: int) -> bool:
        return not any(a < pos < b for a, b in nested)

    caption = None
    for m in _CAPTION_RE.finditer(body):
        if outside_nested(m.start()) and not _commented_out(body, m.start()):
            caption = " ".join(_balanced_argument(body, m.end() - 1).split())
            break
    label = None
    for m in _LABEL_RE.finditer(body):
        if outside_nested(m.start()) and not _commented_out(body, m.start()):
            label = m.group(1).strip()
            break
    return caption, label


def enclosing_float(floats: list[Float], offset: int) -> Float | None:
    """The float containing this offset, if any."""
    for f in floats:
        if f.start <= offset < f.end:
            return f
    return None
