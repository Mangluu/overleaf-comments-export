"""Work out what a document is called when the file tree does not say.

Comments arrive attached to a document id. Turning that into `main.tex` needs
names, and the file tree that used to carry them is no longer on the project
page. Two things Overleaf does still send are enough.

Every document download names its file, in Content-Disposition. That has been
true since the download route itself was added, in Overleaf's
DocumentUpdaterController.getDoc, so wherever the tool can read a document at
all, the name comes with it. And /project/:id/entities lists every path in the
project, without saying which id is which. A name that ends only one path is
that path.

This replaced downloading the whole project zip to match files by content,
which on a paper with large figures meant hundreds of megabytes to learn a few
names. The browser extension does the same, in placeDocs and
fileNameFromDisposition, and a test runs both over the same cases.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from urllib.parse import unquote

_ENCODED = re.compile(r"filename\*\s*=\s*([^']*)'[^']*'([^;\s]+)", re.I)
_QUOTED = re.compile(r'filename\s*=\s*"((?:[^"\\]|\\.)*)"', re.I)
_BARE = re.compile(r"filename\s*=\s*([^;\s]+)", re.I)


def name_from_disposition(header: str | None) -> str | None:
    """The file name a Content-Disposition header gives, or None.

    The encoded form is the exact name, so it wins when both are sent, which
    is what Overleaf does for any name that is not plain ASCII. The standard
    library's email parser prefers the plain form, which turns résumé.tex into
    r?sum?.tex.
    """
    value = header or ""
    encoded = _ENCODED.search(value)
    if encoded:
        try:
            return unquote(encoded.group(2), encoding=encoded.group(1) or "utf-8",
                           errors="strict")
        except (LookupError, UnicodeDecodeError):
            pass                              # malformed: the plain form may still do
    quoted = _QUOTED.search(value)
    if quoted:
        return re.sub(r"\\(.)", r"\1", quoted.group(1)) or None
    bare = _BARE.search(value)
    return bare.group(1) if bare else None


def place_docs(names: dict[str, str | None], doc_paths: list[str]) -> dict[str, str]:
    """Each document's path, from its file name and the project's path list.

    A name that ends exactly one path is that path. With no path list the bare
    name is kept, which still beats an id. Two files with one name are kept
    apart by id, not guessed between, since nothing here says which id lives in
    which folder.
    """
    paths_by_name: dict[str, list[str]] = defaultdict(list)
    for path in doc_paths:
        paths_by_name[path.rsplit("/", 1)[-1]].append(path)
    times_seen = Counter(name for name in names.values() if name)
    placed: dict[str, str] = {}
    for doc_id, name in names.items():
        if not name:
            continue
        paths = paths_by_name.get(name, [])
        if len(paths) == 1:
            placed[doc_id] = paths[0]
        elif len(paths) > 1 or times_seen[name] > 1:
            placed[doc_id] = f"{name} [{doc_id[-6:]}]"
        else:
            placed[doc_id] = name
    return placed
