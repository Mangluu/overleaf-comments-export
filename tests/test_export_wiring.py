"""End-to-end run_export against a fake Overleaf.

The unit tests exercise the renderers directly, which is why a bug where
run_export ignored the requested annotation style survived every one of them:
each piece worked, the wiring between them did not. These tests drive the same
entry point the window and the command line use.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from overleaf_comments_export import export as export_mod

DOC_ID = "doc1"
DOC_TEXT = (
    "\\documentclass{article}\n"
    "\\begin{document}\n"
    "\\section{Method}\n"
    "We crossed three sensory environments in a controlled study.\n"
    "\\end{document}\n"
)
ANCHOR = "three sensory environments"


class FakeClient:
    """Only the surface run_export actually touches."""

    def __init__(self, base_url: str = "") -> None:
        self.base_url = base_url

    def connect(self, browser=None, cookie_value=None):
        return None

    def get_threads(self, project_id):
        return {
            "t1": {
                "messages": [
                    {
                        "id": "m1",
                        "content": "Break this sentence up.",
                        "timestamp": 1_700_000_000_000,
                        "user_id": "u1",
                        "user": {"name": "Bakhtawar Khan", "email": "b@example.com"},
                    }
                ],
                "resolved": False,
            }
        }

    def get_resolved_thread_ids(self, project_id):
        return []

    def get_project_metadata(self, project_id):
        return {"files": None, "name": "Test paper", "rootDocId": DOC_ID, "raw_meta": {}}

    def flatten_files(self, files_root, debug_logger=None):
        return []

    def get_project_ranges(self, project_id):
        return [
            {
                "id": DOC_ID,
                "ranges": {
                    "comments": [
                        {"op": {"p": DOC_TEXT.index(ANCHOR), "c": ANCHOR, "t": "t1"}}
                    ],
                    "changes": [],
                },
            }
        ]

    def download_doc_text(self, project_id, doc_id):
        return DOC_TEXT


@pytest.fixture()
def fake_overleaf(monkeypatch):
    monkeypatch.setattr(export_mod, "OverleafClient", FakeClient)


def _run(tmp_path: Path, **kwargs):
    return export_mod.run_export(
        project_url="https://www.overleaf.com/project/" + "a" * 24,
        out_dir=tmp_path,
        annotated_tex=True,
        **kwargs,
    )


def _annotated_after(tmp_path: Path, style: str) -> str:
    _run(tmp_path, annotate_style=style)
    return _annotated(tmp_path)


def _annotated(tmp_path: Path) -> str:
    files = list((tmp_path / "annotated").rglob("*.tex"))
    assert len(files) == 1, files
    return files[0].read_text()


def test_default_style_highlights_the_commented_words(tmp_path, fake_overleaf):
    """The default has to be the highlight style. run_export used to hard-code
    pdfcomment here, so the window produced pins no matter what."""
    _run(tmp_path)
    tex = _annotated(tmp_path)
    assert "\\pdfmarkupcomment" in tex, "the commented words were not highlighted"
    assert "\\definecolor{ocehl" in tex
    assert ANCHOR in tex


@pytest.mark.parametrize(
    "style, marker",
    [
        ("highlight", "\\pdfmarkupcomment"),
        ("pdfcomment", "\\pdfcomment["),
        ("todonotes", "\\todo{"),
    ],
)
def test_every_style_is_reachable(tmp_path, fake_overleaf, style, marker):
    """Each choice the command line offers has to actually produce that style."""
    tex = _annotated_after(tmp_path, style)
    assert marker in tex
    # A style must not quietly produce a different one, which is the bug these
    # tests exist for.
    if style != "highlight":
        assert "\\pdfmarkupcomment" not in tex


def test_unknown_style_falls_back_rather_than_crashing(tmp_path, fake_overleaf):
    _run(tmp_path, annotate_style="nonsense")
    assert "\\pdfmarkupcomment" in _annotated(tmp_path)


def test_annotated_output_is_ascii(tmp_path, fake_overleaf):
    """Overleaf builds with pdflatex, which stops on anything it cannot encode."""
    _run(tmp_path)
    _annotated(tmp_path).encode("ascii")


def test_gui_defaults_match(tmp_path, fake_overleaf):
    """The window calls run_export without naming a style, so its default is
    the only thing standing between a user and the wrong output."""
    import inspect

    sig = inspect.signature(export_mod.run_export)
    assert sig.parameters["annotate_style"].default == "highlight"
