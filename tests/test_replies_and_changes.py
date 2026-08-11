from __future__ import annotations

from overleaf_comments_export.anchors import build_line_starts
from overleaf_comments_export.export import _deletion_context, _serialize_thread
from overleaf_comments_export.model import (
    AnchoredComment,
    DocText,
    Message,
    SourceContext,
    Thread,
    TrackedChange,
)
from overleaf_comments_export.render import render_markdown


def _thread_with_replies() -> Thread:
    """Real shape from Overleaf: flat list, oldest first = the comment."""
    return Thread(
        id="t1",
        messages=[
            Message(id="m1", content="this needs a citation", timestamp_ms=1_000,
                    user_id="u1", user_name="Emma Pretty", user_email="emma@x.com"),
            Message(id="m2", content="agree", timestamp_ms=2_000,
                    user_id="u2", user_name="Xinyi Yang", user_email="xinyi@x.com"),
            Message(id="m3", content="like change of what", timestamp_ms=3_000,
                    user_id="u2", user_name="Xinyi Yang", user_email="xinyi@x.com"),
        ],
    )


def _comment(short_id="C001") -> AnchoredComment:
    return AnchoredComment(
        thread_id="t1", short_id=short_id, doc_id="d1", pathname="main.tex",
        offset=0, anchored_text="what changes", line_no=66, col=0,
        nearest_heading="Method", stale=False,
        context=SourceContext(before="RQ2. Inside VR,", anchor="what changes",
                              after="when the gloves", line_no=66),
    )


# ---- replies: JSON ----

def test_serialize_thread_tags_comment_and_replies():
    out = _serialize_thread(_thread_with_replies())
    roles = [m["role"] for m in out["messages"]]
    assert roles == ["comment", "reply", "reply"]
    assert [m["reply_index"] for m in out["messages"]] == [None, 0, 1]
    assert out["reply_count"] == 2


def test_serialize_thread_orders_by_timestamp_not_input_order():
    t = Thread(id="t2", messages=[
        Message(id="b", content="second", timestamp_ms=2_000, user_id="u"),
        Message(id="a", content="first", timestamp_ms=1_000, user_id="u"),
    ])
    out = _serialize_thread(t)
    assert [m["content"] for m in out["messages"]] == ["first", "second"]
    assert out["messages"][0]["role"] == "comment"


def test_serialize_thread_single_message_has_no_replies():
    t = Thread(id="t3", messages=[
        Message(id="a", content="only", timestamp_ms=1, user_id="u"),
    ])
    out = _serialize_thread(t)
    assert out["reply_count"] == 0
    assert out["messages"][0]["role"] == "comment"


def test_serialize_thread_resolves_resolved_by_user():
    t = Thread(id="t4", messages=[], resolved=True, resolved_by_user_id="u9")
    out = _serialize_thread(t, {"u9": {"name": "Ada", "email": "ada@x.com"}})
    assert out["resolved_by"] == {"id": "u9", "name": "Ada", "email": "ada@x.com"}


def test_serialize_thread_resolved_by_none_when_unresolved():
    assert _serialize_thread(Thread(id="t5", messages=[]))["resolved_by"] is None


# ---- replies: Markdown ----

def test_replies_are_indented_under_the_comment():
    md = render_markdown(
        "P", "abc", {"t1": _thread_with_replies()}, [_comment()], [], [],
    )
    body = md.split("**C001**", 1)[1]  # skip the summary block
    lines = [
        ln for ln in body.splitlines()
        if "Emma Pretty" in ln or "Xinyi Yang" in ln
    ]
    assert lines[0].startswith("- **Emma Pretty**")       # the ask
    assert lines[1].startswith("  - ↳ **Xinyi Yang**")    # replies indented
    assert lines[2].startswith("  - ↳ **Xinyi Yang**")


def test_reply_count_shown_in_status_badge():
    md = render_markdown(
        "P", "abc", {"t1": _thread_with_replies()}, [_comment()], [], [],
    )
    assert "2 replies" in md


def test_single_reply_is_singular():
    t = _thread_with_replies()
    t.messages = t.messages[:2]
    md = render_markdown("P", "abc", {"t1": t}, [_comment()], [], [])
    assert "1 reply" in md and "1 replies" not in md


def test_no_reply_marker_when_thread_has_none():
    t = Thread(id="t1", messages=[
        Message(id="m1", content="solo", timestamp_ms=1, user_id="u", user_name="A"),
    ])
    md = render_markdown("P", "abc", {"t1": t}, [_comment()], [], [])
    assert "repl" not in md.split("## Summary")[1].split("\n\n")[0]
    assert "↳" not in md


# ---- tracked deletions keep their context ----

def _doc(text: str) -> DocText:
    return DocText(doc_id="d", pathname="main.tex", text=text,
                   line_starts=build_line_starts(text), headings=[])


def test_deletion_context_shows_deleted_text_as_anchor():
    # The deleted words are NOT in the live doc; they sit between before/after.
    text = "We tested the system with users."
    doc = _doc(text)
    offset = text.index("system")  # the deleted words sat right here
    ctx = _deletion_context(doc, offset=offset, deleted="very carefully ", line_no=1)
    assert ctx.anchor == "very carefully"
    assert ctx.before.endswith("the")
    assert ctx.after.startswith("system")


def test_deletion_context_clamps_out_of_range_offset():
    doc = _doc("short")
    ctx = _deletion_context(doc, offset=9999, deleted="gone", line_no=1)
    assert ctx.anchor == "gone"
    assert ctx.after == ""


def test_deletion_renders_struck_through_with_context():
    ch = TrackedChange(
        id="c1", short_id="T001", doc_id="d1", pathname="main.tex",
        kind="deletion", content="very carefully", offset=15, line_no=1, col=0,
        nearest_heading=None, user_id="u1", user_name="Bob",
        user_email="bob@x.com", timestamp_ms=1_000,
        context=SourceContext(before="We tested the", anchor="very carefully",
                              after="system with users.", line_no=1),
    )
    md = render_markdown("P", "abc", {}, [], [], [ch])
    assert "~~very carefully~~" in md      # struck through, in place
    assert "▸here◂" not in md              # the old placeholder is gone
    assert "- very carefully" in md        # and still in the diff line
