"""Work out the order LaTeX reads a project in.

A paper split across files is read in the order the root document pulls the
pieces in, and two things depend on that order rather than on any one file.

Section headings, because `main.tex` can say `\\section{Results}` and then
`\\input{results-body}`, so the prose and the heading that names it live in
different files. Read on its own, `results-body.tex` has no heading at all.

Figure and table numbers, because LaTeX counts them straight through the whole
document. Counted per file they restart, and a comment on Figure 2 gets
reported as Figure 1, which is worse than saying nothing: it sends somebody to
the wrong figure.

This module answers only "what order, and did we see everything". Whether a
number can be claimed at all is decided by the caller, because the answer
depends on whether the whole chain was readable.
"""

from __future__ import annotations

import re
from typing import Iterable, Mapping

# \include always takes a .tex file. \input usually does. \subfile is the
# subfiles package, which is common enough in theses to be worth reading.
_INCLUDE_RE = re.compile(r"\\(?:input|include|subfile)\s*\{([^}]*)\}")
# `\input path` without braces is legal TeX and rare in practice. Reading it
# wrong would invent a file, so it is left alone.


def _strip_comments(text: str) -> str:
    """Blank out commented-out text, keeping offsets so nothing shifts.

    A commented `\\input` is not read by LaTeX and must not be read here. An
    escaped \\% is not a comment.
    """
    out = []
    for line in text.split("\n"):
        i, n = 0, len(line)
        while i < n:
            if line[i] == "%" and (i == 0 or line[i - 1] != "\\"):
                line = line[:i] + " " * (n - i)
                break
            i += 1
        out.append(line)
    return "\n".join(out)


def find_includes(text: str) -> list[str]:
    """The files this one pulls in, in the order it pulls them."""
    return [m.group(1).strip() for m in _INCLUDE_RE.finditer(_strip_comments(text))
            if m.group(1).strip()]


def _candidates(ref: str) -> list[str]:
    """What `\\input{sections/intro}` could name on disk.

    TeX lets you leave the extension off, and people write `./` and
    backslashes, so the reference is normalised before matching.
    """
    ref = ref.replace("\\", "/").strip()
    while ref.startswith("./"):
        ref = ref[2:]
    names = [ref] if ref.endswith(".tex") else [f"{ref}.tex", ref]
    return [n for n in names if n]


def _match(ref: str, available: Mapping[str, str]) -> str | None:
    for name in _candidates(ref):
        if name in available:
            return name
    # A project can say `\input{intro}` for a file the tree calls
    # `sections/intro.tex`. Match on the tail, but only when it is unambiguous.
    for name in _candidates(ref):
        hits = [p for p in available if p == name or p.endswith("/" + name)]
        if len(hits) == 1:
            return hits[0]
    return None


def flatten(root: str, texts: Mapping[str, str]
            ) -> tuple[str, list[tuple[str, int, int]], list[str]]:
    """Splice the whole project into the single document LaTeX reads.

    Returns the joined source, a list of (pathname, offset in that file,
    offset in the joined source) marking where each piece landed, and any
    reference that could not be found.

    Whole files are not enough. `\\input` happens at a point, so a file pulled
    in halfway through the root inherits only the headings above that point,
    and its content sits before everything below it. Treating inclusion as
    file-level puts the pieces in the wrong order, which is how a first
    attempt at this gave an included file the heading that came after it.
    """
    parts: list[str] = []
    marks: list[tuple[str, int, int]] = []
    missing: list[str] = []
    depth: set[str] = set()
    total = 0

    def emit(path: str, text: str, lo: int, hi: int) -> None:
        nonlocal total
        marks.append((path, lo, total))
        chunk = text[lo:hi]
        parts.append(chunk)
        total += len(chunk)

    def walk(path: str) -> None:
        nonlocal total
        if path in depth:
            return                   # a ring of includes; LaTeX would fail too
        depth.add(path)
        text = texts[path]
        stripped = _strip_comments(text)
        cursor = 0
        for m in _INCLUDE_RE.finditer(stripped):
            ref = m.group(1).strip()
            if not ref:
                continue
            emit(path, text, cursor, m.start())
            cursor = m.end()
            target = _match(ref, texts)
            if target is None:
                missing.append(ref)
            else:
                walk(target)
                # \include starts a new page, so anything counted per page
                # would reset here. Nothing here counts per page.
        emit(path, text, cursor, len(text))
        depth.discard(path)

    if root not in texts:
        return "", [], [root]
    walk(root)
    return "".join(parts), marks, missing


def locate(marks: list[tuple[str, int, int]], path: str, offset: int) -> int | None:
    """Where a position in one file landed in the joined source."""
    best = None
    for mark_path, lo, at in marks:
        if mark_path == path and lo <= offset:
            if best is None or lo > best[0]:
                best = (lo, at)
    return None if best is None else best[1] + (offset - best[0])


def resolve_order(root: str, texts: Mapping[str, str]) -> tuple[list[str], list[str]]:
    """Files in the order LaTeX reads them, and any reference we could not find.

    `texts` maps pathname to source. Returns (ordered pathnames, unresolved
    references). A non-empty second list means the picture is incomplete, and
    anything counted across the whole document cannot be trusted.
    """
    if root not in texts:
        return [], [root]

    order: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()

    def walk(path: str) -> None:
        # A file that includes itself, directly or in a ring, would recurse
        # forever. LaTeX would also fail; here it just stops.
        if path in seen:
            return
        seen.add(path)
        order.append(path)
        for ref in find_includes(texts[path]):
            target = _match(ref, texts)
            if target is None:
                missing.append(ref)
            else:
                walk(target)

    walk(root)
    return order, missing


def reachable(root: str, texts: Mapping[str, str],
              known_paths: Iterable[str]) -> list[str]:
    """Files named from `root` that we have not read yet.

    Used to fetch the rest of the chain: a file with no comments in it still
    holds figures that decide what number the next one gets.
    """
    known = set(known_paths)
    want: list[str] = []
    seen: set[str] = set()

    def walk(path: str, source: str) -> None:
        if path in seen:
            return
        seen.add(path)
        for ref in find_includes(source):
            target = _match(ref, texts)
            if target is not None:
                walk(target, texts[target])
                continue
            for name in _candidates(ref):
                hits = [p for p in known if p == name or p.endswith("/" + name)]
                if len(hits) == 1 and hits[0] not in want:
                    want.append(hits[0])
                    break

    if root in texts:
        walk(root, texts[root])
    return want
