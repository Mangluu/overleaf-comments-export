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

    # What each download's Content-Disposition names the document, and what
    # /entities lists. Empty by default, so a test opts in to names.
    doc_names: dict = {}
    doc_paths: list = []

    def download_doc_text(self, project_id, doc_id):
        return DOC_TEXT

    def download_doc(self, project_id, doc_id):
        # Text from download_doc_text, which many fakes override.
        return self.download_doc_text(project_id, doc_id), self.doc_names.get(doc_id)

    def get_doc_paths(self, project_id):
        return list(self.doc_paths)


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
#
# Each document's download names its file, and /entities lists the paths. The
# project zip used to be downloaded whole to match files by content, which on
# a paper with large figures meant hundreds of megabytes to learn a few names.

def test_the_filename_comes_from_the_download_when_the_tree_is_empty(tmp_path, monkeypatch):
    """A pasted cookie gets no file tree, and today's overleaf.com page carries
    none either. Every comment used to file under <unknown-...>."""
    class Named(FakeClient):
        doc_names = {DOC_ID: "main.tex"}
        doc_paths = ["paper/main.tex", "paper/refs.bib"]

    monkeypatch.setattr(export_mod, "OverleafClient", Named)
    result = _run(tmp_path)
    import json

    data = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert data["comments"][0]["pathname"] == "paper/main.tex"
    assert "<unknown-" not in result.markdown_path.read_text(encoding="utf-8")


def test_a_bare_name_is_used_when_the_path_list_is_unavailable(tmp_path, monkeypatch):
    class NameOnly(FakeClient):
        doc_names = {DOC_ID: "main.tex"}

    monkeypatch.setattr(export_mod, "OverleafClient", NameOnly)
    import json

    data = json.loads(_run(tmp_path).json_path.read_text(encoding="utf-8"))
    assert data["comments"][0]["pathname"] == "main.tex"


def test_the_placeholder_is_still_used_when_no_name_comes_back(tmp_path, fake_overleaf):
    """FakeClient names nothing. An honest placeholder beats a wrong name."""
    result = _run(tmp_path)
    import json

    data = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert data["comments"][0]["pathname"].startswith("<unknown-")


def test_nothing_more_is_asked_when_the_tree_already_named_everything(tmp_path, monkeypatch):
    asked = []

    class Named(FakeClient):
        def get_project_metadata(self, project_id):
            return {"files": {"any": "shape"}, "name": "Test paper",
                    "rootDocId": DOC_ID, "raw_meta": {}}

        def flatten_files(self, files_root, debug_logger=None):
            return [{"doc_id": DOC_ID, "pathname": "main.tex"}]

        def get_doc_paths(self, project_id):
            asked.append(project_id)
            return []

    monkeypatch.setattr(export_mod, "OverleafClient", Named)
    result = _run(tmp_path)
    assert not asked, "asked for the path list for nothing"
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
    """Names come from the server, in a download header and a path list, and
    nothing checks them before they reach the disk."""
    from overleaf_comments_export.export import safe_relative

    class Escaping(FakeClient):
        doc_names = {DOC_ID: "passwd.tex"}
        doc_paths = ["../../../etc/passwd.tex"]

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


def test_the_spreadsheet_is_written_when_asked(tmp_path, fake_overleaf):
    """The window and the command line both pass this through, and a flag that
    is read but never acted on is exactly the bug this file exists for."""
    openpyxl = pytest.importorskip("openpyxl")
    result = _run(tmp_path, write_xlsx_sheet=True)
    assert result.xlsx_path is not None and result.xlsx_path.exists()

    book = openpyxl.load_workbook(result.xlsx_path)
    assert book.sheetnames == ["Comments", "Replies", "Tracked changes"]
    comments = book["Comments"]
    assert comments.max_row >= 2, "no comment rows"
    assert comments["A1"].value == "Comment"
    assert comments["A2"].value == "C001"
    # A header that scrolls away, or no filters, defeats the point of a sheet.
    assert comments.freeze_panes == "A2"
    assert comments.auto_filter.ref


def test_no_spreadsheet_unless_asked(tmp_path, fake_overleaf):
    result = _run(tmp_path)
    assert result.xlsx_path is None
    assert not (tmp_path / "comments.xlsx").exists()


def test_the_window_can_ask_for_one(tmp_path, fake_overleaf):
    """The window builds run_export's arguments by hand, so a new option can
    be added to the export and never reach it."""
    import inspect
    from overleaf_comments_export import gui

    source = inspect.getsource(gui.App._start_export if hasattr(gui.App, "_start_export")
                               else gui.App)
    assert "write_xlsx_sheet=" in source, "the window never passes it on"


def test_the_viewer_is_written_when_asked(tmp_path, fake_overleaf):
    result = _run(tmp_path, write_viewer=True)
    assert result.viewer_path is not None and result.viewer_path.exists()
    page = result.viewer_path.read_text(encoding="utf-8")
    assert "<html" in page and "C001" in page


def test_no_viewer_unless_asked(tmp_path, fake_overleaf):
    assert _run(tmp_path).viewer_path is None


def test_the_window_can_ask_for_the_viewer(tmp_path, fake_overleaf):
    import inspect
    from overleaf_comments_export import gui
    assert "write_viewer=" in inspect.getsource(gui.App), "the window never passes it on"


def test_a_reviewer_named_like_a_windows_device_still_gets_a_file():
    """Windows refuses con.md and nul.md whatever the extension, and the failed
    write ended the whole export. Con is a real first name."""
    from overleaf_comments_export.export import _slug_reviewer
    for name in ("Con", "aux", "NUL", "com1", "Lpt9"):
        slug = _slug_reviewer(name)
        assert slug.endswith("-reviewer"), (name, slug)
    assert _slug_reviewer("Con O'Brien") == "con-obrien"
    assert _slug_reviewer("Connor") == "connor"


# --- which server a link points at ------------------------------------------

def test_the_server_is_the_one_the_link_names():
    """A self-hosted link already names its server. Without --base-url as well,
    every request went to overleaf.com, where the project does not exist."""
    from overleaf_comments_export.client import base_url_for
    pid = "a" * 24
    assert base_url_for(f"https://latex.example.edu/project/{pid}") == "https://latex.example.edu"
    assert base_url_for(f"http://localhost:8080/project/{pid}/") == "http://localhost:8080"
    assert base_url_for(f"latex.example.edu/project/{pid}") == "https://latex.example.edu"
    # overleaf.com in any of its spellings is the canonical address, so a link
    # without www does not put every request through a redirect.
    for link in (f"https://www.overleaf.com/project/{pid}", f"https://overleaf.com/project/{pid}",
                 f"https://WWW.Overleaf.com/project/{pid}", "", None, "not a link"):
        assert base_url_for(link) == "https://www.overleaf.com", link


def _server_used(tmp_path, monkeypatch, **kwargs):
    from overleaf_comments_export import export as export_mod
    seen = {}

    class Spy(FakeClient):
        def __init__(self, base_url="", **kw):
            seen["base_url"] = base_url
            super().__init__(base_url, **kw)

    monkeypatch.setattr(export_mod, "OverleafClient", Spy)
    export_mod.run_export(out_dir=tmp_path, **kwargs)
    return seen["base_url"]


def test_a_self_hosted_link_is_exported_from_its_own_server(tmp_path, monkeypatch):
    used = _server_used(tmp_path, monkeypatch,
                        project_url="https://latex.example.edu/project/" + "a" * 24)
    assert used == "https://latex.example.edu"


def test_a_server_named_explicitly_still_wins(tmp_path, monkeypatch):
    used = _server_used(tmp_path, monkeypatch,
                        project_url="https://www.overleaf.com/project/" + "a" * 24,
                        base_url="https://mirror.example.org")
    assert used == "https://mirror.example.org"


def test_the_command_line_no_longer_assumes_overleaf_com():
    from overleaf_comments_export import __main__ as cli
    import inspect
    assert "default=None" in inspect.getsource(cli).split('"--base-url"', 1)[1].split(")", 1)[0]
