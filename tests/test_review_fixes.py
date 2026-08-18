"""The things a review found that the whole suite had passed straight over.

Each of these was live and green. They are here so they cannot come back.
"""

from __future__ import annotations

import json
import os
import stat
import sys

import pytest

from overleaf_comments_export import export as export_mod
from overleaf_comments_export.anchors import resolve_anchor
from overleaf_comments_export.model import DocText
from overleaf_comments_export.anchors import build_line_starts
from tests.test_export_wiring import FakeClient, ANCHOR, DOC_ID, DOC_TEXT

URL = "https://www.overleaf.com/project/" + "a" * 24
HIDDEN = "SECRET: this reviewer was filtered out."


class TwoReviewers(FakeClient):
    """One open thread from one person, one resolved thread from another."""

    def get_threads(self, project_id):
        return {
            "t1": {"messages": [{"id": "m1", "content": "Break this sentence up.",
                                 "timestamp": 1_700_000_000_000, "user_id": "u1",
                                 "user": {"name": "Bakhtawar Khan",
                                          "email": "b@example.com"}}],
                   "resolved": False},
            "t2": {"messages": [{"id": "m2", "content": HIDDEN,
                                 "timestamp": 1_700_000_000_000, "user_id": "u2",
                                 "user": {"name": "Hidden Reviewer",
                                          "email": "h@example.com"}}],
                   "resolved": True},
        }

    def get_resolved_thread_ids(self, project_id):
        return ["t2"]

    def get_project_ranges(self, project_id):
        i = DOC_TEXT.index(ANCHOR)
        return [{"id": DOC_ID, "ranges": {
            "comments": [{"op": {"p": i, "c": ANCHOR, "t": "t1"}},
                         {"op": {"p": i, "c": ANCHOR, "t": "t2"}}],
            "changes": []}}]


@pytest.fixture()
def two_reviewers(monkeypatch):
    monkeypatch.setattr(export_mod, "OverleafClient", TwoReviewers)


@pytest.mark.parametrize("kwargs", [
    {"reviewer_filter": ["Bakhtawar Khan"]},
    {"include_resolved": False},
])
def test_filters_reach_the_json_not_just_the_markdown(tmp_path, two_reviewers, kwargs):
    """comments.json used to carry every discussion whatever the filters said,
    so --reviewer and --no-resolved hid a thread from the Markdown and handed
    it over in full in the file next to it."""
    result = export_mod.run_export(project_url=URL, out_dir=tmp_path,
                                   response_letter=True, **kwargs)
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))

    assert HIDDEN not in json.dumps(payload)
    assert sorted(payload["threads"]) == ["t1"]
    assert HIDDEN not in result.markdown_path.read_text(encoding="utf-8")
    assert HIDDEN not in (tmp_path / "response-letter.md").read_text(encoding="utf-8")
    assert HIDDEN not in (tmp_path / "comments.jsonl").read_text(encoding="utf-8")


@pytest.mark.parametrize("kwargs", [
    {"reviewer_filter": ["Bakhtawar Khan"]},
    {"include_resolved": False},
])
def test_the_counts_only_count_what_survived(tmp_path, two_reviewers, kwargs):
    result = export_mod.run_export(project_url=URL, out_dir=tmp_path, **kwargs)
    summary = json.loads(result.json_path.read_text(encoding="utf-8"))["summary"]
    assert summary["thread_count"] == 1
    assert summary["reviewer_count"] == 1, "a filtered-out reviewer was counted"


def test_without_filters_everything_is_still_there(tmp_path, two_reviewers):
    """The fix must not quietly start dropping threads nobody filtered."""
    result = export_mod.run_export(project_url=URL, out_dir=tmp_path)
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert sorted(payload["threads"]) == ["t1", "t2"]
    assert HIDDEN in json.dumps(payload)
    assert payload["summary"]["reviewer_count"] == 2


def test_whats_new_cannot_report_a_filtered_thread(tmp_path, two_reviewers,
                                                   monkeypatch):
    """The diff reads comments.json. While that file carried every thread
    regardless of the filters, a reply on a thread the user had filtered out
    came back to them as new feedback, quoted in full."""
    export_mod.run_export(project_url=URL, out_dir=tmp_path, include_resolved=False)

    base = TwoReviewers.get_threads
    reply = "AND THIS REPLY TOO."

    def now_with_a_reply(self, project_id):
        threads = base(self, project_id)
        threads["t2"]["messages"].append({
            "id": "m3", "content": reply, "timestamp": 1_700_000_500_000,
            "user_id": "u2", "user": {"name": "Hidden Reviewer"}})
        return threads

    monkeypatch.setattr(TwoReviewers, "get_threads", now_with_a_reply)
    result = export_mod.run_export(project_url=URL, out_dir=tmp_path,
                                   include_resolved=False)

    text = result.since_path.read_text(encoding="utf-8")
    assert reply not in text
    assert HIDDEN not in text


# --- cancellation says what is actually in the folder ----------------------

def test_stopping_before_any_write_still_promises_an_empty_folder(tmp_path,
                                                                  two_reviewers):
    with pytest.raises(export_mod.ExportCancelled) as e:
        export_mod.run_export(project_url=URL, out_dir=tmp_path,
                              should_cancel=lambda: True)
    assert e.value.written == []


def test_stopping_during_the_extras_admits_what_landed(tmp_path, two_reviewers):
    """The gates inside the annotated-LaTeX and PDF steps fire after the
    comments are already on disk. Both the window and the command line used to
    answer "Nothing was written" regardless."""
    calls = {"n": 0}

    def cancel_once_the_core_files_exist():
        calls["n"] += 1
        return (tmp_path / "comments.json").exists()

    with pytest.raises(export_mod.ExportCancelled) as e:
        export_mod.run_export(project_url=URL, out_dir=tmp_path,
                              annotated_tex=True,
                              should_cancel=cancel_once_the_core_files_exist)

    assert "comments.json" in e.value.written
    assert any(f.startswith("comments-") or f == "comments.md"
               for f in e.value.written)
    # Whatever it names has to actually be there, or the message is a new lie.
    for name in e.value.written:
        assert (tmp_path / name).exists(), f"{name} was claimed but not written"


# --- stale anchors stay inside the file ------------------------------------

def _doc(text: str) -> DocText:
    return DocText(doc_id="d", pathname="p.tex", text=text,
                   line_starts=build_line_starts(text), headings=[])


@pytest.mark.parametrize("offset", [10_000, -5])
def test_a_stale_anchor_offset_stays_inside_the_file(offset):
    """--include-source promises these index into source/. An offset past the
    end slices to nothing, so the context reads as if there were none."""
    doc = _doc("Short document.\n")
    new_offset, line, col, stale = resolve_anchor(doc, offset, "text that is gone")
    assert stale
    assert 0 <= new_offset < len(doc.text)
    assert doc.text[new_offset:new_offset + 1] != ""


def test_a_good_anchor_is_left_alone():
    doc = _doc("alpha beta gamma\n")
    at = doc.text.index("beta")
    assert resolve_anchor(doc, at, "beta") == (at, 1, at, False)


# --- the remembered cookie is not world-readable ---------------------------

@pytest.mark.skipif(sys.platform.startswith("win"),
                    reason="POSIX permission bits do not apply on Windows")
def test_the_settings_file_is_owner_only(tmp_path, monkeypatch):
    """It holds an Overleaf session cookie when "remember" is ticked, and it
    was being written 0644 in a 0755 folder."""
    from overleaf_comments_export import gui

    folder = tmp_path / "settings"
    folder.mkdir()
    monkeypatch.setattr(gui, "CONFIG_PATH", folder / "config.json")
    gui._save_config({"cookie_value": "a-live-session-token"})

    assert stat.S_IMODE(os.stat(folder / "config.json").st_mode) == 0o600
    assert stat.S_IMODE(os.stat(folder).st_mode) == 0o700


# --- second audit round ----------------------------------------------------

def test_counts_are_over_threads_not_anchors(tmp_path, monkeypatch):
    """A project whose ranges cannot be read has threads and no anchors. It
    reported thread_count 1 with open_count 0, so the one open thread was
    invisible, and the Markdown beside it said something different."""
    import re

    class NoRanges(FakeClient):
        def get_threads(self, project_id):
            return {
                "t1": {"messages": [{"id": "m1", "content": "Open one.",
                                     "timestamp": 1_700_000_000_000, "user_id": "u1",
                                     "user": {"name": "R"}}], "resolved": False},
                "t2": {"messages": [{"id": "m2", "content": "Done one.",
                                     "timestamp": 1_700_000_000_000, "user_id": "u1",
                                     "user": {"name": "R"}}], "resolved": True},
            }

        def get_resolved_thread_ids(self, project_id):
            return ["t2"]

        def get_project_ranges(self, project_id):
            return []

    monkeypatch.setattr(export_mod, "OverleafClient", NoRanges)
    result = export_mod.run_export(project_url=URL, out_dir=tmp_path)

    summary = json.loads(result.json_path.read_text(encoding="utf-8"))["summary"]
    assert (summary["thread_count"], summary["open_count"],
            summary["resolved_count"]) == (2, 1, 1)

    # And the Markdown has to agree, since it is the same export.
    md = result.markdown_path.read_text(encoding="utf-8")
    for key in ("thread_count", "open_count", "resolved_count"):
        in_md = int(re.search(rf"^{key}: (\d+)$", md, re.M).group(1))
        assert in_md == summary[key], f"{key}: json {summary[key]}, markdown {in_md}"


def test_two_reviewers_whose_names_slug_the_same_both_get_a_report(tmp_path,
                                                                   monkeypatch):
    """"A B" and "A-B" both slug to "a-b", and the second report replaced the
    first without a word."""
    class TwoNames(FakeClient):
        def get_threads(self, project_id):
            return {
                "t1": {"messages": [{"id": "m1", "content": "From the first.",
                                     "timestamp": 1_700_000_000_000, "user_id": "u1",
                                     "user": {"name": "A B"}}], "resolved": False},
                "t2": {"messages": [{"id": "m2", "content": "From the second.",
                                     "timestamp": 1_700_000_000_000, "user_id": "u2",
                                     "user": {"name": "A-B"}}], "resolved": False},
            }

        def get_resolved_thread_ids(self, project_id):
            return []

        def get_project_ranges(self, project_id):
            return []

    monkeypatch.setattr(export_mod, "OverleafClient", TwoNames)
    export_mod.run_export(project_url=URL, out_dir=tmp_path, per_reviewer_reports=True)

    written = sorted(p.name for p in (tmp_path / "by-reviewer").glob("*.md"))
    assert len(written) == 2, f"one report was overwritten: {written}"
    both = "\n".join((tmp_path / "by-reviewer" / n).read_text(encoding="utf-8")
                     for n in written)
    assert "From the first." in both and "From the second." in both


def test_a_reviewer_report_counts_only_that_reviewer(tmp_path, two_reviewers):
    """Every one of these files used to carry whole-project totals in its
    front matter, so a report headed with one name claimed all the threads."""
    import re

    export_mod.run_export(project_url=URL, out_dir=tmp_path, per_reviewer_reports=True)
    for path in (tmp_path / "by-reviewer").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert int(re.search(r"^thread_count: (\d+)$", text, re.M).group(1)) == 1, path.name
        assert int(re.search(r"^reviewer_count: (\d+)$", text, re.M).group(1)) == 1, path.name


def test_a_title_with_quotes_in_it_still_parses(tmp_path, two_reviewers):
    """A paper really can be called `A "quoted" paper`, and it ended the YAML
    scalar early and made the whole front matter unreadable."""
    yaml = pytest.importorskip("yaml")
    result = export_mod.run_export(project_url=URL, out_dir=tmp_path,
                                   project_title='A "quoted" paper: it\'s fine')
    front = result.markdown_path.read_text(encoding="utf-8").split("---")[1]
    assert yaml.safe_load(front)["project_title"] == 'A "quoted" paper: it\'s fine'
