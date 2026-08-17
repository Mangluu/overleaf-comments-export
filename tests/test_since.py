"""What --since must get right.

The one that matters most is renumbering. Short ids go in file then line
order, so a comment added at the top of the paper shifts every id below it. A
diff keyed on those would say the whole paper is new, every time.
"""

from __future__ import annotations

import json

import pytest

from overleaf_comments_export.since import (compare, load_previous,
                                            render_since, short_ids)


def msg(mid, text, who="Bakhtawar Khan", when="2026-08-01T10:00:00+00:00"):
    return {"id": mid, "role": "comment", "user": {"id": "u1", "name": who},
            "content": text, "timestamp": when, "edited_at": None}


def payload(threads, comments, *, project="p1", changes=None, filters=None):
    return {
        "schema_version": "1.3",
        "project": {"id": project, "title": "A paper"},
        "pulled_at": "2026-08-01T10:00:00+00:00",
        "threads": threads,
        "comments": comments,
        "tracked_changes": changes or [],
        "filters_applied": filters if filters is not None else {"include_open": True},
    }


def thread(tid, messages, resolved=False, resolved_by=None):
    return {"id": tid, "resolved": resolved,
            "resolved_by": {"name": resolved_by} if resolved_by else None,
            "reply_count": max(0, len(messages) - 1), "messages": messages}


def comment(short_id, tid, line, path="paper.tex", heading="Introduction"):
    return {"short_id": short_id, "thread_id": tid, "pathname": path,
            "line": line, "nearest_heading": heading, "enclosing_float": None,
            "anchored_text": f"phrase at {line}", "stale": False}


def test_renumbering_is_not_a_change():
    """The whole reason identity is the thread id and not the short id."""
    old = payload({"t1": thread("t1", [msg("m1", "fix this")])},
                  [comment("C001", "t1", 50)])
    # A new comment lands above it, so the old one becomes C002.
    new = payload(
        {"t1": thread("t1", [msg("m1", "fix this")]),
         "t2": thread("t2", [msg("m2", "and this")])},
        [comment("C001", "t2", 10), comment("C002", "t1", 50)])

    d = compare(old, new)
    assert [c["short_id"] for c in d.new_comments] == ["C001"]
    assert d.new_comments[0]["text"] == "and this"
    assert not d.gone and not d.new_replies


def test_new_reply_on_an_old_thread():
    old = payload({"t1": thread("t1", [msg("m1", "fix this")])},
                  [comment("C001", "t1", 50)])
    new = payload(
        {"t1": thread("t1", [msg("m1", "fix this"),
                             msg("m2", "still not fixed", who="ans.ahmad")])},
        [comment("C001", "t1", 50)])

    d = compare(old, new)
    assert not d.new_comments
    assert len(d.new_replies) == 1
    assert [r["text"] for r in d.new_replies[0]["replies"]] == ["still not fixed"]
    assert d.new_replies[0]["replies"][0]["who"] == "ans.ahmad"


def test_resolved_and_reopened():
    a = thread("t1", [msg("m1", "one")])
    b = thread("t2", [msg("m2", "two")], resolved=True)
    old = payload({"t1": a, "t2": b}, [comment("C001", "t1", 1),
                                       comment("C002", "t2", 2)])
    new = payload(
        {"t1": thread("t1", [msg("m1", "one")], resolved=True, resolved_by="Shivang"),
         "t2": thread("t2", [msg("m2", "two")], resolved=False)},
        [comment("C001", "t1", 1), comment("C002", "t2", 2)])

    d = compare(old, new)
    assert [r["short_id"] for r in d.resolved] == ["C001"]
    assert d.resolved[0]["by"] == "Shivang"
    assert [r["short_id"] for r in d.reopened] == ["C002"]


def test_edited_comment_is_caught():
    """It changes what you must answer without ever looking new."""
    old = payload({"t1": thread("t1", [msg("m1", "cite Smith")])},
                  [comment("C001", "t1", 5)])
    new = payload({"t1": thread("t1", [msg("m1", "cite Smith and Jones")])},
                  [comment("C001", "t1", 5)])

    d = compare(old, new)
    assert len(d.edited) == 1
    assert d.edited[0]["was"] == "cite Smith"
    assert d.edited[0]["now"] == "cite Smith and Jones"
    assert not d.new_comments and not d.new_replies


def test_deleted_thread_is_reported():
    old = payload({"t1": thread("t1", [msg("m1", "drop this section")])},
                  [comment("C001", "t1", 5)])
    new = payload({}, [])

    d = compare(old, new)
    assert len(d.gone) == 1
    assert d.gone[0]["thread_id"] == "t1"


def test_different_filters_suppress_deletions():
    """A thread hidden by --no-resolved has not gone anywhere."""
    old = payload({"t1": thread("t1", [msg("m1", "hi")], resolved=True)},
                  [comment("C001", "t1", 5)],
                  filters={"include_open": True, "include_resolved": True})
    new = payload({}, [], filters={"include_open": True, "include_resolved": False})

    d = compare(old, new)
    assert d.gone == []
    assert d.filters_differ
    assert "filters" in render_since(
        d, project_title="A paper", previous_path="old/comments.json")


def test_a_different_paper_is_not_compared():
    old = payload({"t1": thread("t1", [msg("m1", "hi")])},
                  [comment("C001", "t1", 5)], project="OTHER")
    new = payload({}, [])

    d = compare(old, new)
    assert not d.comparable
    assert "different paper" in d.summary()
    assert "different paper" in render_since(
        d, project_title="A paper", previous_path="old/comments.json")


def test_nothing_changed_says_so():
    p = payload({"t1": thread("t1", [msg("m1", "hi")])}, [comment("C001", "t1", 5)])
    d = compare(p, json.loads(json.dumps(p)))
    assert not d.anything
    assert "Nothing has changed" in d.summary()
    assert "already seen" in render_since(
        d, project_title="A paper", previous_path="old/comments.json")


def test_new_tracked_changes_keyed_on_the_real_id():
    ch = {"id": "r1", "short_id": "T001", "kind": "insertion",
          "content": "very ", "pathname": "paper.tex", "line": 9,
          "nearest_heading": "Method", "user": {"name": "ans.ahmad"}}
    old = payload({}, [], changes=[ch])
    new = payload({}, [], changes=[
        dict(ch, short_id="T002"),  # renumbered, same range
        {"id": "r2", "short_id": "T001", "kind": "deletion", "content": "old",
         "pathname": "paper.tex", "line": 3, "user": {"name": "ans.ahmad"}},
    ])

    d = compare(old, new)
    assert [c["short_id"] for c in d.new_changes] == ["T001"]
    assert d.new_changes[0]["kind"] == "deletion"


def test_float_beats_heading_in_the_location():
    old = payload({}, [])
    c = comment("C001", "t1", 40)
    c["enclosing_float"] = {"kind": "figure", "number": 3, "label": "fig:x",
                            "caption": "A plot"}
    new = payload({"t1": thread("t1", [msg("m1", "axis label")])}, [c])

    d = compare(old, new)
    assert "Figure 3" in d.new_comments[0]["where"]
    assert "Introduction" not in d.new_comments[0]["where"]


def test_unanchored_thread_still_reported():
    old = payload({}, [])
    new = payload({"t1": thread("t1", [msg("m1", "general note")])}, [])

    d = compare(old, new)
    assert len(d.new_comments) == 1
    assert d.new_comments[0]["short_id"] is None
    out = render_since(d, project_title="A paper", previous_path="p")
    assert "not anchored" in out


def test_render_reads_as_a_document():
    old = payload({"t1": thread("t1", [msg("m1", "fix this")])},
                  [comment("C001", "t1", 50)])
    new = payload(
        {"t1": thread("t1", [msg("m1", "fix this"), msg("m2", "ping")]),
         "t2": thread("t2", [msg("m2b", "and this")])},
        [comment("C001", "t2", 10), comment("C002", "t1", 50)])

    out = render_since(compare(old, new), project_title="A paper",
                       previous_path="last/comments.json")
    assert out.startswith("# What is new — A paper")
    assert "1 new comment" in out          # singular
    assert "1 thread with new replies" in out
    assert "and this" in out and "ping" in out
    assert "last/comments.json" in out


def test_stable_leaves_timestamps_out():
    """Same reason the rest of --stable does: a clean git diff."""
    old = payload({}, [])
    new = payload({"t1": thread("t1", [msg("m1", "hi")])}, [comment("C001", "t1", 5)])
    d = compare(old, new)
    assert "2026-08-01" in render_since(d, project_title="A", previous_path="p")
    assert "2026-08-01" not in render_since(d, project_title="A", previous_path="p",
                                            stable=True)


def test_short_ids_for_the_json():
    old = payload({"t1": thread("t1", [msg("m1", "a")])}, [comment("C001", "t1", 5)])
    new = payload(
        {"t1": thread("t1", [msg("m1", "a")], resolved=True),
         "t2": thread("t2", [msg("m2", "b")])},
        [comment("C001", "t1", 5), comment("C002", "t2", 9)])

    ids = short_ids(compare(old, new))
    assert ids["new_comments"] == ["C002"]
    assert ids["resolved"] == ["C001"]
    assert ids["gone_thread_ids"] == []


def test_long_comments_are_clipped_not_dumped():
    old = payload({}, [])
    new = payload({"t1": thread("t1", [msg("m1", "x" * 900)])},
                  [comment("C001", "t1", 5)])
    out = render_since(compare(old, new), project_title="A", previous_path="p")
    assert "…" in out
    assert "x" * 900 not in out


@pytest.mark.parametrize("where", ["folder", "file"])
def test_load_previous_takes_a_folder_or_the_file(tmp_path, where):
    p = payload({}, [])
    (tmp_path / "comments.json").write_text(json.dumps(p), encoding="utf-8")
    target = tmp_path if where == "folder" else tmp_path / "comments.json"
    assert load_previous(target) == p


def test_load_previous_survives_a_broken_file(tmp_path):
    (tmp_path / "comments.json").write_text("{not json", encoding="utf-8")
    assert load_previous(tmp_path) is None
    assert load_previous(tmp_path / "nothing-here") is None


# --- the wiring, through run_export itself ---------------------------------
#
# The diff being right is worth nothing if the export never calls it, which is
# exactly how the annotate_style bug survived a full unit suite.

from tests.test_export_wiring import FakeClient  # noqa: E402
from overleaf_comments_export import export as export_mod  # noqa: E402
from overleaf_comments_export.since import SINCE_FILENAME  # noqa: E402

URL = "https://www.overleaf.com/project/" + "a" * 24
BASE_THREADS = FakeClient.get_threads  # held before any monkeypatching of it


@pytest.fixture()
def fake(monkeypatch):
    monkeypatch.setattr(export_mod, "OverleafClient", FakeClient)


def test_first_export_writes_no_diff(tmp_path, fake):
    """There is nothing to compare against, and an empty file would be noise."""
    result = export_mod.run_export(project_url=URL, out_dir=tmp_path)
    assert result.since_path is None
    assert not (tmp_path / SINCE_FILENAME).exists()


def test_second_export_picks_up_the_first_by_itself(tmp_path, fake, monkeypatch):
    """No flag needed. The previous export is sitting in the same folder."""
    export_mod.run_export(project_url=URL, out_dir=tmp_path)

    def with_a_reply(self, project_id):
        threads = BASE_THREADS(self, project_id)
        threads["t1"]["messages"].append({
            "id": "m2", "content": "Any progress on this?",
            "timestamp": 1_700_000_100_000, "user_id": "u2",
            "user": {"name": "ans.ahmad", "email": "a@example.com"}})
        return threads

    monkeypatch.setattr(FakeClient, "get_threads", with_a_reply)
    result = export_mod.run_export(project_url=URL, out_dir=tmp_path)

    assert result.since_path == tmp_path / SINCE_FILENAME
    text = result.since_path.read_text(encoding="utf-8")
    assert "1 thread with new replies" in text
    assert "Any progress on this?" in text


def test_the_json_and_the_brief_both_carry_it(tmp_path, fake, monkeypatch):
    export_mod.run_export(project_url=URL, out_dir=tmp_path)
    monkeypatch.setattr(FakeClient, "get_threads", lambda self, pid: {
        **BASE_THREADS(self, pid),
        "t2": {"messages": [{"id": "mx", "content": "New one.",
                             "timestamp": 1_700_000_200_000, "user_id": "u2",
                             "user": {"name": "ans.ahmad"}}], "resolved": False},
    })
    result = export_mod.run_export(project_url=URL, out_dir=tmp_path)

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    # The new thread has no anchor in the fake project, so it lands in the
    # export as an orphan and carries no short id. What has to hold is that
    # the key exists, is shaped right, and says where it compared against.
    assert set(payload["since"]) >= {"compared_with", "new_comments",
                                     "resolved", "gone_thread_ids"}
    assert payload["since"]["compared_with"].endswith("comments.json")
    assert "New one." in result.since_path.read_text(encoding="utf-8")

    brief = (tmp_path / "agents.md").read_text(encoding="utf-8")
    assert SINCE_FILENAME in brief and "`since`" in brief


def test_no_since_turns_it_off(tmp_path, fake):
    export_mod.run_export(project_url=URL, out_dir=tmp_path)
    result = export_mod.run_export(project_url=URL, out_dir=tmp_path, write_since=False)
    assert result.since_path is None
    assert not (tmp_path / SINCE_FILENAME).exists()


def test_since_pointing_at_another_folder(tmp_path, fake, monkeypatch):
    first = tmp_path / "january"
    export_mod.run_export(project_url=URL, out_dir=first)
    monkeypatch.setattr(FakeClient, "get_threads", lambda self, pid: {
        **BASE_THREADS(self, pid),
        "t2": {"messages": [{"id": "mx", "content": "Added in February.",
                             "timestamp": 1_700_000_200_000, "user_id": "u2",
                             "user": {"name": "ans.ahmad"}}], "resolved": False},
    })
    result = export_mod.run_export(project_url=URL, out_dir=tmp_path / "february",
                                   since=str(first))
    assert "Added in February." in result.since_path.read_text(encoding="utf-8")


def test_since_at_a_path_with_nothing_there_is_an_error(tmp_path, fake):
    """Silently exporting without the comparison the user asked for is worse."""
    with pytest.raises(export_mod.UserFacingError) as e:
        export_mod.run_export(project_url=URL, out_dir=tmp_path,
                              since=str(tmp_path / "not-an-export"))
    assert "No previous export" in str(e.value)
