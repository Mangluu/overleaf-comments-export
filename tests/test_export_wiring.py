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

    def __init__(self, base_url: str = "", **kwargs) -> None:
        self.base_url = base_url
        self.cookie_name = kwargs.get("cookie_name")

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

    def download_project_zip(self, project_id):
        return None


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
    return files[0].read_text(encoding="utf-8")


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


# --- naming documents when the file tree is unavailable (issue #4) ---

def _zip_of(files):
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_the_filename_comes_from_the_zip_when_the_tree_is_empty(tmp_path, monkeypatch):
    """The whole point of issue #4: a pasted cookie gets no file tree, and every
    comment used to file under <unknown-...>."""
    class WithZip(FakeClient):
        def download_project_zip(self, project_id):
            return _zip_of({"paper/main.tex": DOC_TEXT})

    monkeypatch.setattr(export_mod, "OverleafClient", WithZip)
    result = _run(tmp_path)
    import json

    data = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert data["comments"][0]["pathname"] == "paper/main.tex"
    assert "<unknown-" not in result.markdown_path.read_text(encoding="utf-8")


def test_the_placeholder_is_still_used_when_the_zip_cannot_help(tmp_path, fake_overleaf):
    """FakeClient returns no zip. An honest placeholder beats a wrong name."""
    result = _run(tmp_path)
    import json

    data = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert data["comments"][0]["pathname"].startswith("<unknown-")


def test_the_zip_is_not_fetched_when_the_tree_already_named_everything(tmp_path, monkeypatch):
    """It is a whole project download. It must not happen for nothing."""
    asked = []

    class Named(FakeClient):
        def get_project_metadata(self, project_id):
            return {"files": {"any": "shape"}, "name": "Test paper",
                    "rootDocId": DOC_ID, "raw_meta": {}}

        def flatten_files(self, files_root, debug_logger=None):
            return [{"doc_id": DOC_ID, "pathname": "main.tex"}]

        def download_project_zip(self, project_id):
            asked.append(project_id)
            return _zip_of({"main.tex": DOC_TEXT})

    monkeypatch.setattr(export_mod, "OverleafClient", Named)
    result = _run(tmp_path)
    assert not asked, "downloaded the whole project for nothing"
    import json

    assert json.loads(result.json_path.read_text(encoding="utf-8"))["comments"][0]["pathname"] == "main.tex"


def test_a_folder_that_cannot_be_written_says_so_plainly(tmp_path, fake_overleaf, monkeypatch):
    """Picking an unwritable folder is an ordinary mistake, not a crash. It used
    to surface as a raw PermissionError with an Errno in it.

    The refusal is simulated rather than made with chmod, because chmod on a
    directory does not stop writes on Windows and the check is the same code on
    every platform anyway.
    """
    from overleaf_comments_export.client import UserFacingError

    real_write = Path.write_text

    def refuse(self, *args, **kwargs):
        if self.name == ".oce-write-test":
            raise PermissionError(13, "Permission denied")
        return real_write(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", refuse)
    with pytest.raises(UserFacingError) as excinfo:
        _run(tmp_path)
    message = str(excinfo.value)
    assert "Nothing can be written" in message
    assert str(tmp_path) in message, "the message must name the folder"
    assert "Errno" not in message


def test_a_writable_folder_is_left_exactly_as_it_was(tmp_path, fake_overleaf):
    """The check writes a probe file. It must not survive."""
    _run(tmp_path)
    assert not (tmp_path / ".oce-write-test").exists()


# --- writing the source out, so an assistant can read more than a window ---

def test_the_source_is_written_and_the_offsets_point_into_it(tmp_path, fake_overleaf):
    """The whole reason for this option: `offset` has to be a valid index into
    the file that gets written, or an assistant cannot use it."""
    import json

    result = _run(tmp_path, include_source=True)
    written = list((tmp_path / "source").rglob("*.tex"))
    assert len(written) == 1
    text = written[0].read_text(encoding="utf-8")
    assert text == DOC_TEXT, "the file must be byte for byte what the offsets index"

    comment = json.loads(result.json_path.read_text(encoding="utf-8"))["comments"][0]
    at = comment["offset"]
    assert text[at:at + len(comment["anchored_text"])] == comment["anchored_text"]
    assert text.splitlines()[comment["line"] - 1].strip(), "the line number is off"


def test_no_source_is_written_unless_it_was_asked_for(tmp_path, fake_overleaf):
    _run(tmp_path)
    assert not (tmp_path / "source").exists()


def test_the_agent_brief_says_whether_the_source_is_there(tmp_path, fake_overleaf):
    result = _run(tmp_path, include_source=True)
    with_source = result.agents_path.read_text(encoding="utf-8")
    assert "source/" in with_source
    assert "--include-source" not in with_source, "it is there, do not tell them to ask for it"

    other = tmp_path / "without"
    _run(other)
    without = (other / "agents.md").read_text(encoding="utf-8")
    assert "--include-source" in without, "it should say how to get the source"


def test_a_project_path_cannot_escape_the_export_folder(tmp_path, monkeypatch):
    """Since the zip fallback, a filename can come from a zip member name, and
    those are allowed to say ../../elsewhere."""
    from overleaf_comments_export.export import safe_relative

    class Escaping(FakeClient):
        def download_project_zip(self, project_id):
            return _zip_of({"../../../etc/passwd.tex": DOC_TEXT})

    monkeypatch.setattr(export_mod, "OverleafClient", Escaping)
    _run(tmp_path, include_source=True)
    written = [p for p in tmp_path.rglob("*") if p.is_file()]
    for path in written:
        assert tmp_path in path.parents or path.parent == tmp_path or tmp_path in path.resolve().parents
    assert not (tmp_path.parent / "etc").exists(), "it wrote outside the export folder"
    # as_posix(): a Path prints with backslashes on Windows, and the point
    # here is the shape of the path rather than the separator.
    assert safe_relative("../../etc/passwd", "d").as_posix() == "etc/passwd"
    assert safe_relative("/etc/passwd", "d").as_posix() == "etc/passwd"
    assert safe_relative("sections/intro.tex", "d").as_posix() == "sections/intro.tex"
    assert safe_relative("C:\\Windows\\system32\\evil.tex", "d").as_posix() == "Windows/system32/evil.tex"
    # Whatever comes in, the result must be relative. An absolute path joined
    # to the output folder replaces it, which is the escape this prevents.
    for hostile in ("/etc/passwd", "../../etc/passwd", "C:/Windows/evil.tex",
                    "\\\\server\\share\\evil.tex", "....//....//etc", ""):
        assert not safe_relative(hostile, "d").is_absolute(), hostile
