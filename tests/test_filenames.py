"""Naming a document from the project zip when the file tree is unavailable.

Issue #4. The socket call needs a browser, so anyone who pasted a cookie never
had a file tree, and the project page no longer reliably carries one. Every
comment then files under `<unknown-...>`, which on a multi-file paper loses the
grouping completely.
"""

from __future__ import annotations

import io
import zipfile

from overleaf_comments_export.filenames import index_zip, name_for

MAIN = "\\documentclass{article}\n\\begin{document}\nThe opening claim.\n\\end{document}\n"
INTRO = "\\section{Introduction}\nParticipants completed three blocks.\n"


def _zip(files: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_a_document_is_named_by_what_is_in_it():
    index = index_zip(_zip({"main.tex": MAIN, "sections/intro.tex": INTRO}))
    assert name_for(index, MAIN) == "main.tex"
    assert name_for(index, INTRO) == "sections/intro.tex"


def test_line_endings_and_a_missing_final_newline_do_not_matter():
    """The zip and the document download disagree about both, and neither
    difference means the two are different files."""
    index = index_zip(_zip({"main.tex": MAIN.replace("\n", "\r\n")}))
    assert name_for(index, MAIN) == "main.tex"
    assert name_for(index, MAIN.rstrip("\n")) == "main.tex"
    assert name_for(index, MAIN + "\n\n") == "main.tex"


def test_trailing_whitespace_does_not_matter():
    index = index_zip(_zip({"main.tex": MAIN}))
    padded = "\n".join(line + "   " for line in MAIN.split("\n"))
    assert name_for(index, padded) == "main.tex"


def test_two_identical_files_are_left_unnamed():
    """Which document id belongs to which is unknowable from here, and a wrong
    filename is worse than an honest placeholder."""
    index = index_zip(_zip({"a.tex": MAIN, "copies/b.tex": MAIN}))
    assert name_for(index, MAIN) is None


def test_text_that_is_in_no_file_is_unnamed():
    index = index_zip(_zip({"main.tex": MAIN}))
    assert name_for(index, "something else entirely") is None


def test_binary_and_oversized_members_are_skipped_not_fatal():
    index = index_zip(_zip({
        "main.tex": MAIN,
        "figures/plot.png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 4096,
        "data.csv": "a,b,c\n1,2,3\n",
    }))
    assert name_for(index, MAIN) == "main.tex"
    assert all(not p.endswith(".png") for paths in index.values() for p in paths)


def test_a_file_that_is_not_utf8_does_not_stop_the_rest():
    index = index_zip(_zip({"legacy.tex": "caf\xe9".encode("latin-1"), "main.tex": MAIN}))
    assert name_for(index, MAIN) == "main.tex"


def test_a_corrupt_zip_gives_nothing_rather_than_raising():
    assert index_zip(b"not a zip at all") == {}
    assert name_for({}, MAIN) is None


def test_the_bib_and_class_files_are_indexed_too():
    """A comment cannot live in them, but naming them costs nothing and a
    project that keeps its text in an .Rnw should still work."""
    index = index_zip(_zip({"refs.bib": "@article{a,title={T}}", "paper.Rnw": INTRO}))
    assert name_for(index, "@article{a,title={T}}") == "refs.bib"
    assert name_for(index, INTRO) == "paper.Rnw"
