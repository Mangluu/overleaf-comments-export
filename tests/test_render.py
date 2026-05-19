from __future__ import annotations

from overleaf_comments_export.model import (
    AnchoredComment,
    Message,
    SourceContext,
    Thread,
    TrackedChange,
)
from overleaf_comments_export.render import render_markdown


def _basic_thread(resolved: bool = False) -> Thread:
    return Thread(
        id="t1",
        resolved=resolved,
        messages=[
            Message(id="m1", content="Needs a citation.", timestamp_ms=1700000000000,
                    user_id="u1", user_name="Alice", user_email="alice@x.edu"),
        ],
    )


def _basic_comment() -> AnchoredComment:
    return AnchoredComment(
        thread_id="t1", short_id="C001", doc_id="d1", pathname="main.tex",
        offset=10, anchored_text="novel framework", line_no=42, col=5,
        nearest_heading="Method", stale=False,
        context=SourceContext(
            before="We propose a ",
            anchor="novel framework",
            after=" based on X.",
            line_no=42,
        ),
    )


def test_render_includes_yaml_frontmatter():
    md = render_markdown(
        "Test Paper", "abc",
        threads={"t1": _basic_thread()},
        anchored=[_basic_comment()],
        orphan_threads=[],
        changes=[],
    )
    assert md.startswith("---\n")
    assert "schema_version: 1.3" in md
    assert 'project_title: "Test Paper"' in md
    assert "companion_json: comments.json" in md
    assert "companion_agents: agents.md" in md


def test_compact_render_has_inline_anchor_marker():
    md = render_markdown(
        "Test", "abc",
        threads={"t1": _basic_thread()},
        anchored=[_basic_comment()],
        orphan_threads=[],
        changes=[],
        mode="compact",
    )
    # Inline highlight via ▸…◂
    assert "▸novel framework◂" in md
    # No code fence in compact
    assert "```tex" not in md


def test_detailed_render_uses_code_fence():
    md = render_markdown(
        "Test", "abc",
        threads={"t1": _basic_thread()},
        anchored=[_basic_comment()],
        orphan_threads=[],
        changes=[],
        mode="detailed",
    )
    assert "```tex" in md
    assert "▸ novel framework" in md


def test_render_groups_same_line_comments():
    """Two comments on the same (file, line) should share ONE context block."""
    c1 = _basic_comment()
    c2 = AnchoredComment(
        thread_id="t1", short_id="C002", doc_id="d1", pathname="main.tex",
        offset=20, anchored_text="another phrase", line_no=42, col=20,
        nearest_heading="Method", stale=False,
        context=SourceContext(
            before="and ", anchor="another phrase", after=" later",
            line_no=42,
        ),
    )
    md = render_markdown(
        "Test", "abc",
        threads={"t1": _basic_thread()},
        anchored=[c1, c2],
        orphan_threads=[],
        changes=[],
        mode="compact",
    )
    # Single "Line 42 — 2 comments" header for the group
    assert "**Line 42** — 2 comments" in md


def test_render_skips_per_file_heading_when_only_one_file():
    """The "## main.tex" wrapper should not appear when there's just one file."""
    md = render_markdown(
        "Test", "abc",
        threads={"t1": _basic_thread()},
        anchored=[_basic_comment()],
        orphan_threads=[],
        changes=[],
    )
    assert "\n## main.tex\n" not in md
    assert "## Table of contents" not in md  # also skipped for 1 file


def test_render_resolved_shows_in_status():
    md = render_markdown(
        "Test", "abc",
        threads={"t1": _basic_thread(resolved=True)},
        anchored=[_basic_comment()],
        orphan_threads=[],
        changes=[],
    )
    assert "_resolved_" in md


def test_humanize_user_from_email_dotted():
    """yxy.xinyi.yang@gmail.com → 'Yxy Xinyi Yang' in render."""
    thread = Thread(
        id="t1",
        messages=[
            Message(id="m1", content="hi", timestamp_ms=1700000000000,
                    user_id="u1", user_name=None,
                    user_email="firstname.lastname@x.com"),
        ],
    )
    md = render_markdown(
        "Test", "abc",
        threads={"t1": thread},
        anchored=[
            AnchoredComment(
                thread_id="t1", short_id="C001", doc_id="d1",
                pathname="main.tex", offset=0, anchored_text="x",
                line_no=1, col=0, nearest_heading=None, stale=False,
            )
        ],
        orphan_threads=[],
        changes=[],
    )
    assert "Firstname Lastname" in md


def test_tracked_change_compact_render():
    ch = TrackedChange(
        id="ch1", short_id="T001", doc_id="d1", pathname="main.tex",
        kind="insertion", content="New sentence.", offset=0, line_no=10,
        col=0, nearest_heading="Intro", user_id="u1", user_name="Bob",
        user_email="bob@x.edu", timestamp_ms=1700100000000,
    )
    md = render_markdown(
        "Test", "abc",
        threads={},
        anchored=[],
        orphan_threads=[],
        changes=[ch],
    )
    assert "T001" in md
    assert "insertion" in md
    assert "+ New sentence." in md
