"""Naming a document when the file tree is unavailable.

Issue #4. The socket call needs a browser, so anyone who pasted a cookie never
had a file tree, and today's project page carries none for anybody. Every
comment then filed under `<unknown-...>`, which on a multi-file paper loses the
grouping completely. Each download names its file, and /entities lists the
paths, so neither the zip nor a guess is needed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from overleaf_comments_export.filenames import name_from_disposition, place_docs

HEADERS = [
    'attachment; filename="main.tex"',
    "attachment; filename=main.tex",
    # What Overleaf sends for a name that is not plain ASCII. The exact form wins.
    "attachment; filename=\"r?sum?.tex\"; filename*=UTF-8''r%C3%A9sum%C3%A9.tex",
    "attachment; filename*=UTF-8''%E4%B8%AD%E6%96%87.tex",
    'attachment; filename="say \\"hi\\".tex"',
    "attachment; filename*=UTF-8''%E0%A4.tex; filename=\"fallback.tex\"",   # malformed escape
    "",
    "attachment",
]


def test_a_name_is_read_from_every_form_the_header_takes():
    assert [name_from_disposition(h) for h in HEADERS] == [
        "main.tex", "main.tex", "résumé.tex", "中文.tex", 'say "hi".tex',
        "fallback.tex", None, None]
    assert name_from_disposition(None) is None


PLACE_CASES = [
    # Names and paths line up one to one.
    ({"a": "main.tex", "b": "method.tex"}, ["main.tex", "sections/method.tex"]),
    # Two files called intro.tex: kept apart by id, never merged or guessed.
    ({"c": "intro.tex", "d": "intro.tex"}, ["sections/intro.tex", "appendix/intro.tex"]),
    # No path list at all: the bare name.
    ({"e": "method.tex"}, []),
    # A name the list does not know: still the bare name.
    ({"f": "notes.tex"}, ["main.tex"]),
    # A download that named nothing is left out, for the placeholder to cover.
    ({"g": None, "h": "main.tex"}, ["main.tex"]),
]


def test_a_name_is_given_its_folder_when_only_one_path_ends_in_it():
    placed = place_docs(*PLACE_CASES[0])
    assert placed == {"a": "main.tex", "b": "sections/method.tex"}


def test_two_files_with_one_name_are_kept_apart():
    placed = place_docs(*PLACE_CASES[1])
    assert placed["c"] != placed["d"]
    assert placed["c"].startswith("intro.tex [") and placed["d"].startswith("intro.tex [")


def test_without_a_path_list_the_bare_name_is_kept():
    assert place_docs(*PLACE_CASES[2]) == {"e": "method.tex"}
    assert place_docs(*PLACE_CASES[4]) == {"h": "main.tex"}


@pytest.mark.skipif(shutil.which("node") is None, reason="node runs the extension's own code")
def test_the_extension_and_the_cli_name_files_the_same_way():
    """Two copies of one rule drift apart unless something holds them together."""
    core = Path(__file__).resolve().parent.parent / "browser-extension" / "src" / "export-core.js"
    script = ("const core = require(process.argv[1]);"
              "const { headers, places } = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
              "process.stdout.write(JSON.stringify({"
              "  names: headers.map((h) => core.fileNameFromDisposition(h)),"
              "  placed: places.map(([names, paths]) => core.placeDocs(names, paths)) }));")
    out = json.loads(subprocess.run(
        ["node", "-e", script, str(core)],
        input=json.dumps({"headers": HEADERS, "places": PLACE_CASES}),
        capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    assert out["names"] == [name_from_disposition(h) for h in HEADERS]
    assert out["placed"] == [place_docs(names, paths) for names, paths in PLACE_CASES]
