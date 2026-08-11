from __future__ import annotations

from overleaf_comments_export.model import (
    AnchoredComment,
    Message,
    SourceContext,
    Thread,
)
from overleaf_comments_export.render import render_response_letter


def _thread(tid, author, body, resolved=False, reply=None):
    msgs = [
        Message(id=f"{tid}m1", content=body, timestamp_ms=1_000, user_id=author,
                user_name=author.title(), user_email=f"{author}@x.com")
    ]
    if reply:
        msgs.append(
            Message(id=f"{tid}m2", content=reply, timestamp_ms=2_000, user_id="co",
                    user_name="Co Author", user_email="co@x.com")
        )
    return Thread(id=tid, messages=msgs, resolved=resolved)


def _comment(tid, short_id, line=10, heading="Introduction", anchor="some phrase"):
    return AnchoredComment(
        thread_id=tid, short_id=short_id, doc_id="d1", pathname="main.tex",
        offset=0, anchored_text=anchor, line_no=line, col=0,
        nearest_heading=heading, stale=False,
        context=SourceContext(before="a", anchor=anchor, after="b", line_no=line),
    )


def test_letter_has_a_slot_for_every_open_comment():
    threads = {
        "t1": _thread("t1", "emma", "needs a citation"),
        "t2": _thread("t2", "emma", "unclear phrasing"),
    }
    md = render_response_letter(
        "My Paper", "abc", threads, [_comment("t1", "C001"), _comment("t2", "C002")]
    )
    assert "C001" in md and "C002" in md
    assert md.count("**Response:**") == 2
    assert md.count("**Change made:**") == 2
    assert "2 point(s) to address" in md


def test_letter_groups_by_who_raised_the_point():
    threads = {
        "t1": _thread("t1", "emma", "point one"),
        "t2": _thread("t2", "xinyi", "point two"),
    }
    md = render_response_letter(
        "P", "abc", threads, [_comment("t1", "C001"), _comment("t2", "C002")]
    )
    assert "## Emma — 1 point(s)" in md
    assert "## Xinyi — 1 point(s)" in md


def test_letter_skips_resolved_comments():
    threads = {
        "t1": _thread("t1", "emma", "already handled", resolved=True),
        "t2": _thread("t2", "emma", "still open"),
    }
    md = render_response_letter(
        "P", "abc", threads, [_comment("t1", "C001"), _comment("t2", "C002")]
    )
    assert "C002" in md
    assert "C001" not in md
    assert "1 point(s) to address" in md


def test_letter_includes_the_discussion_so_far():
    threads = {"t1": _thread("t1", "emma", "the ask", reply="we could cite Smith")}
    md = render_response_letter("P", "abc", threads, [_comment("t1", "C001")])
    assert "**Discussion so far:**" in md
    assert "we could cite Smith" in md
    assert "↳ Co Author" in md


def test_letter_carries_location_and_quote():
    threads = {"t1": _thread("t1", "emma", "vague")}
    md = render_response_letter(
        "P", "abc", threads,
        [_comment("t1", "C001", line=42, heading="Method", anchor="novel framework")],
    )
    assert "§ Method" in md
    assert "`main.tex` line 42" in md
    assert "“novel framework”" in md


def test_letter_with_nothing_open_says_so():
    threads = {"t1": _thread("t1", "emma", "done", resolved=True)}
    md = render_response_letter("P", "abc", threads, [_comment("t1", "C001")])
    assert "No open comments" in md
    assert "**Response:**" not in md


def test_letter_survives_a_comment_whose_thread_is_missing():
    md = render_response_letter("P", "abc", {}, [_comment("gone", "C001")])
    assert "No open comments" in md


def test_letter_hides_unmapped_filenames():
    """A reader of the letter should never see "<unknown-6a21dec…>"."""
    threads = {"t1": _thread("t1", "emma", "vague")}
    c = _comment("t1", "C001", line=42)
    c.pathname = "<unknown-6a21dec6cb39c30917f5c477>"
    md = render_response_letter("P", "abc", threads, [c])
    assert "unknown-" not in md
    assert "line 42" in md
