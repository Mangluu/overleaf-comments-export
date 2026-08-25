"""Multi-file papers: the order LaTeX reads them in, and what depends on it.

Two things depend on the whole document rather than on any one file. Which
section a comment sits under, when the heading is in the root and the prose is
in an included file. And what number a figure carries, since LaTeX counts
straight through. Counted per file the numbers restart, and a comment on
Figure 2 came back as Figure 1, which is worse than saying nothing.
"""

from __future__ import annotations

import json

import pytest

from overleaf_comments_export import export as export_mod
from overleaf_comments_export.docorder import (find_includes, flatten, locate,
                                               resolve_order)
from tests.test_export_wiring import FakeClient

URL = "https://www.overleaf.com/project/" + "a" * 24


# --- reading the includes ---------------------------------------------------

def test_every_way_a_paper_pulls_in_a_file():
    text = (r"\input{a}" "\n" r"\include{b}" "\n" r"\subfile{c}" "\n"
            r"\input{sub/dir/d.tex}")
    assert find_includes(text) == ["a", "b", "c", "sub/dir/d.tex"]


def test_a_commented_out_include_is_not_read():
    """LaTeX does not read it, so neither does this. Reading it would invent a
    file and, worse, invent figures that shift every later number."""
    assert find_includes("% \\input{draft}\n\\input{real}") == ["real"]
    assert find_includes("\\input{real} % \\input{draft}") == ["real"]
    # An escaped percent is not a comment.
    assert find_includes(r"100\% \input{real}") == ["real"]


@pytest.mark.parametrize("ref", ["intro", "intro.tex", "./intro", "sections/intro"])
def test_a_reference_finds_its_file_however_it_is_written(ref):
    texts = {"main.tex": "\\input{%s}" % ref, "sections/intro.tex": "x"}
    order, missing = resolve_order("main.tex", texts)
    assert missing == []
    assert order == ["main.tex", "sections/intro.tex"]


def test_a_ring_of_includes_stops_instead_of_recursing():
    texts = {"a.tex": "\\input{b}", "b.tex": "\\input{a}"}
    joined, marks, missing = flatten("a.tex", texts)
    assert missing == []          # both were found; it simply stops


def test_a_file_that_is_not_there_is_reported():
    texts = {"main.tex": "\\input{gone}"}
    _, _, missing = flatten("main.tex", texts)
    assert missing == ["gone"]


# --- the splice -------------------------------------------------------------

def test_an_included_file_lands_where_the_include_sits():
    """Not at the end of the parent. `\\input` happens at a point, and treating
    it as file-level is what gave an included file the heading below it."""
    joined, marks, _ = flatten("main.tex", {"main.tex": "A \\input{b} C", "b.tex": "BBB"})
    assert joined == "A BBB C"
    assert locate(marks, "b.tex", 0) == 2
    assert locate(marks, "main.tex", 12) == 6      # the C, after the splice


# --- what it is all for -----------------------------------------------------

FILES = {
    "d_main": ("main.tex",
               "\\documentclass{article}\n\\begin{document}\n"
               "\\section{Results}\n\\input{results-body}\n"
               "\\begin{figure}\\caption{First}\\label{fig:a}\\end{figure}\n"
               "\\input{extra-figures}\n"
               "\\section{Discussion}\n\\input{discussion-body}\n\\end{document}\n"),
    "d_results": ("results-body.tex", "Task time fell by twelve percent.\n"),
    # No comment in here at all, but its figure still moves the counter on.
    "d_extra": ("extra-figures.tex",
                "\\begin{figure}\\caption{Nobody commented}\\end{figure}\n"),
    "d_disc": ("discussion-body.tex",
               "\\begin{figure}\\caption{Fourth}\\label{fig:d}\\end{figure}\n"
               "The effect is smaller than we expected.\n"),
}
ANCHORS = {"d_results": ("twelve percent", "t1"),
           "d_disc": ("Fourth", "t2"),
           "d_main": ("First", "t3")}


def _threads():
    return {tid: {"resolved": False,
                  "messages": [{"id": f"m{tid}", "content": "note",
                                "timestamp": 1_700_000_000_000, "user_id": "u1",
                                "user": {"name": "R"}}]}
            for _, tid in ANCHORS.values()}


class MultiFile(FakeClient):
    unreadable: set[str] = set()

    def get_threads(self, project_id):
        return _threads()

    def get_resolved_thread_ids(self, project_id):
        return []

    def get_project_metadata(self, project_id):
        return {"files": {"docs": []}, "name": "Paper",
                "rootDocId": "d_main", "raw_meta": {}}

    def flatten_files(self, files_root, debug_logger=None):
        return [{"doc_id": d, "pathname": p} for d, (p, _) in FILES.items()]

    def get_project_ranges(self, project_id):
        return [{"id": d, "ranges": {
            "comments": [{"op": {"p": FILES[d][1].index(txt), "c": txt, "t": tid}}],
            "changes": []}} for d, (txt, tid) in ANCHORS.items()]

    def download_doc_text(self, project_id, doc_id):
        if doc_id in self.unreadable:
            raise RuntimeError("cannot read this one")
        return FILES[doc_id][1]


@pytest.fixture()
def multi(monkeypatch):
    MultiFile.unreadable = set()
    monkeypatch.setattr(export_mod, "OverleafClient", MultiFile)


def _comments(tmp_path):
    result = export_mod.run_export(project_url=URL, out_dir=tmp_path)
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    return {c["short_id"]: c for c in payload["comments"]}


def test_figure_numbers_run_through_the_whole_paper(tmp_path, multi):
    """The bug in #12. Counted per file these were Figure 1 and Figure 1."""
    by_path = {c["pathname"]: c for c in _comments(tmp_path).values()}
    assert by_path["main.tex"]["enclosing_float"]["number"] == 1
    # 2 is in extra-figures.tex, which carries no comment and was never
    # downloaded until this feature went in. Miss it and this reads 2.
    assert by_path["discussion-body.tex"]["enclosing_float"]["number"] == 3


def test_a_comment_in_an_included_file_gets_its_section(tmp_path, multi):
    """The heading is in main.tex and the prose is not, so on its own the
    included file has no heading at all."""
    by_path = {c["pathname"]: c for c in _comments(tmp_path).values()}
    assert by_path["results-body.tex"]["nearest_heading"] == "Results"
    assert by_path["discussion-body.tex"]["nearest_heading"] == "Discussion"


def test_the_section_is_the_one_above_the_include_not_below_it(tmp_path, multi):
    """results-body is pulled in under Results, and Discussion comes after.
    A first attempt at this handed it Discussion, because it carried the whole
    parent file's headings across instead of only those above the include."""
    by_path = {c["pathname"]: c for c in _comments(tmp_path).values()}
    assert by_path["results-body.tex"]["nearest_heading"] != "Discussion"


def test_an_unreadable_file_means_no_numbers_rather_than_wrong_ones(tmp_path,
                                                                    multi):
    """Missing sends nobody anywhere. Wrong sends them to the wrong figure."""
    MultiFile.unreadable = {"d_extra"}
    numbers = [c["enclosing_float"]["number"]
               for c in _comments(tmp_path).values() if c["enclosing_float"]]
    assert numbers and all(n is None for n in numbers), numbers


def test_a_single_file_paper_is_unaffected(tmp_path, monkeypatch):
    """The common case must not change, and must not fetch anything extra."""
    text = ("\\section{Method}\n"
            "\\begin{figure}\\caption{Only}\\label{fig:o}\\end{figure}\n"
            "We crossed three sensory environments in a controlled study.\n")

    class Single(FakeClient):
        def get_threads(self, project_id):
            return {"t1": {"resolved": False, "messages": [
                {"id": "m1", "content": "note", "timestamp": 1_700_000_000_000,
                 "user_id": "u1", "user": {"name": "R"}}]}}

        def get_resolved_thread_ids(self, project_id):
            return []

        def get_project_metadata(self, project_id):
            return {"files": {"docs": []}, "name": "P", "rootDocId": "d1",
                    "raw_meta": {}}

        def flatten_files(self, files_root, debug_logger=None):
            return [{"doc_id": "d1", "pathname": "main.tex"}]

        def get_project_ranges(self, project_id):
            return [{"id": "d1", "ranges": {"comments": [
                {"op": {"p": text.index("Only"), "c": "Only", "t": "t1"}}],
                "changes": []}}]

        def download_doc_text(self, project_id, doc_id):
            return text

    monkeypatch.setattr(export_mod, "OverleafClient", Single)
    c = list(_comments(tmp_path).values())[0]
    assert c["enclosing_float"]["number"] == 1
    assert c["nearest_heading"] == "Method"
