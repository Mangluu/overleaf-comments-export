from __future__ import annotations

import re
from bisect import bisect_right

from .model import Heading

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
