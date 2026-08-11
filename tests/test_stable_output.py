from __future__ import annotations

import json
import re

from overleaf_comments_export.export import _build_structured_json
from overleaf_comments_export.model import (
    AnchoredComment,
    Message,
    SourceContext,
    Thread,
)
from overleaf_comments_export.render import render_markdown, render_response_letter

ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


def _threads():
    return {
        "t1": Thread(id="t1", messages=[
            Message(id="m1", content="needs a citation", timestamp_ms=1_000,
                    user_id="u1", user_name="Emma", user_email="emma@x.com")]),
        "t2": Thread(id="t2", messages=[
            Message(id="m2", content="unclear", timestamp_ms=2_000,
                    user_id="u2", user_name="Xinyi", user_email="x@x.com")]),
    }


def _comments():
    return [
        AnchoredComment(thread_id="t1", short_id="C001", doc_id="d", pathname="main.tex",
            offset=0, anchored_text="alpha", line_no=10, col=0,
            nearest_heading="Intro", stale=False,
            context=SourceContext(before="a", anchor="alpha", after="b", line_no=10)),
        AnchoredComment(thread_id="t2", short_id="C002", doc_id="d", pathname="main.tex",
            offset=50, anchored_text="beta", line_no=20, col=0,
            nearest_heading="Method", stale=False,
            context=SourceContext(before="c", anchor="beta", after="d", line_no=20)),
    ]


# ---- the whole point: re-running must not change the file ----

def test_stable_markdown_is_byte_identical_across_runs():
    a = render_markdown("P", "abc", _threads(), _comments(), [], [], stable=True)
    b = render_markdown("P", "abc", _threads(), _comments(), [], [], stable=True)
    assert a == b


def test_stable_markdown_carries_no_timestamp():
    md = render_markdown("P", "abc", _threads(), _comments(), [], [], stable=True)
    assert "pulled_at" not in md
    header = md.split("---", 2)[1]
    assert not ISO_DATE.search(header)


def test_default_markdown_still_records_when_it_was_pulled():
    md = render_markdown("P", "abc", _threads(), _comments(), [], [])
    assert "pulled_at:" in md


def test_stable_response_letter_is_identical_across_runs():
    a = render_response_letter("P", "abc", _threads(), _comments(), stable=True)
    b = render_response_letter("P", "abc", _threads(), _comments(), stable=True)
    assert a == b
    assert "Draft generated" not in a
    assert "2 point(s) to address" in a


def test_default_response_letter_keeps_the_date():
    assert "Draft generated" in render_response_letter(
        "P", "abc", _threads(), _comments()
    )


# ---- ordering must not depend on dict insertion order ----

def _json(threads, stable=True):
    return json.dumps(_build_structured_json(
        project_id="abc", project_title="P", threads=threads,
        anchored=_comments(), changes=[], orphan_threads=[],
        doc_id_to_path={"d": "main.tex"}, open_count=2, resolved_count=0,
        stale_count=0, threads_raw={}, ranges_payload=None, stable=stable,
    ), sort_keys=False, default=str)


def test_json_is_identical_whatever_order_threads_arrived_in():
    forward = _threads()
    reverse = {k: forward[k] for k in reversed(list(forward))}
    assert list(forward) != list(reverse)  # genuinely different insertion order
    assert _json(forward) == _json(reverse)


def test_stable_json_has_no_pulled_at():
    assert "pulled_at" not in _json(_threads(), stable=True)
    assert "pulled_at" in _json(_threads(), stable=False)


def test_orphan_ids_are_sorted():
    payload = _build_structured_json(
        project_id="abc", project_title="P", threads=_threads(),
        anchored=[], changes=[],
        orphan_threads=[Thread(id="zzz"), Thread(id="aaa"), Thread(id="mmm")],
        doc_id_to_path={}, open_count=0, resolved_count=0, stale_count=0,
        threads_raw={}, ranges_payload=None, stable=True,
    )
    assert payload["orphan_thread_ids"] == ["aaa", "mmm", "zzz"]


def test_reviewer_ranking_breaks_ties_by_name_not_insertion_order():
    """Two reviewers with one comment each must always list in the same order."""
    one = {
        "t1": Thread(id="t1", messages=[Message(id="a", content="x", timestamp_ms=1,
                     user_id="u1", user_name="Zoe")]),
        "t2": Thread(id="t2", messages=[Message(id="b", content="y", timestamp_ms=2,
                     user_id="u2", user_name="Adam")]),
    }
    two = {k: one[k] for k in reversed(list(one))}
    a = render_markdown("P", "abc", one, [], [], [], stable=True)
    b = render_markdown("P", "abc", two, [], [], [], stable=True)
    assert a == b
    assert "Adam (1), Zoe (1)" in a
