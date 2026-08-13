"""Work out what a document is called when Overleaf will not say.

Comments arrive attached to a document id. Turning that into `main.tex` needs
the project's file tree, and there are two ways to get one. The socket call
needs pyoverleaf, which needs a browser, so it is unavailable to anyone who
pasted a cookie. The project page used to carry the tree in a meta tag and no
longer reliably does. When both come up empty every comment is filed under
`<unknown-6a21dec…>`, which on a multi-file paper loses the grouping entirely.

The zip Overleaf will hand over on request has the real names in it. It does
not say which document id each file came from, but we have already downloaded
the text of every document that carries a comment, and a file is identified
perfectly well by what is in it.
"""

from __future__ import annotations

import io
import logging
import zipfile

logger = logging.getLogger(__name__)

# Only worth reading out of the zip. A figure cannot hold a comment, and some
# projects carry a hundred megabytes of them.
TEXT_SUFFIXES = (".tex", ".bib", ".txt", ".cls", ".sty", ".bst", ".md", ".Rnw")
# A file larger than this is not a document somebody is commenting on, and
# reading it would only cost memory.
MAX_MEMBER_BYTES = 8 * 1024 * 1024


def _canonical(text: str) -> str:
    """Content with the differences that do not matter taken out.

    The zip and the document download disagree about line endings and about
    whether the file ends in a newline, and neither difference means the two
    are different files.
    """
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n")).strip()


def index_zip(data: bytes) -> dict[str, list[str]]:
    """Map canonical content to the paths holding it.

    A list, because a project can genuinely contain two identical files, and
    guessing between them is worse than admitting we cannot tell.
    """
    index: dict[str, list[str]] = {}
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        logger.warning("The project zip could not be opened: %s", e)
        return {}
    for info in archive.infolist():
        if info.is_dir() or not info.filename.lower().endswith(tuple(
                s.lower() for s in TEXT_SUFFIXES)):
            continue
        if info.file_size > MAX_MEMBER_BYTES:
            continue
        try:
            raw = archive.read(info)
        except Exception as e:  # a corrupt member must not lose the rest
            logger.warning("Skipped %s in the project zip: %s", info.filename, e)
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        index.setdefault(_canonical(text), []).append(info.filename)
    return index


def name_for(index: dict[str, list[str]], text: str) -> str | None:
    """The path whose contents are this text, if exactly one file matches."""
    matches = index.get(_canonical(text))
    if not matches:
        return None
    if len(matches) > 1:
        # Two files with identical contents. Which document id belongs to which
        # is genuinely unknowable from here, and a wrong filename is worse than
        # an honest placeholder.
        logger.info("Several files share this content, so it is left unnamed: %s", matches)
        return None
    return matches[0]
