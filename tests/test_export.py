from __future__ import annotations

from overleaf_comments_export.export import (
    _extract_context,
    _iter_doc_ranges,
    _slug_reviewer,
    _thread_matches_reviewer,
    _to_ms,
)
from overleaf_comments_export.anchors import build_line_starts
from overleaf_comments_export.model import DocText, Message, Thread


def _doc(text: str) -> DocText:
    return DocText(
        doc_id="d", pathname="main.tex", text=text,
        line_starts=build_line_starts(text), headings=[],
    )


# ---- _to_ms ----

def test_to_ms_int():
    assert _to_ms(1700000000000) == 1700000000000


def test_to_ms_numeric_string():
    assert _to_ms("1700000000000") == 1700000000000


def test_to_ms_iso8601_z():
    ms = _to_ms("2026-03-10T13:07:34.911Z")
    assert ms is not None and ms > 0


def test_to_ms_iso8601_no_tz():
    ms = _to_ms("2026-03-10T13:07:34")
    assert ms is not None


def test_to_ms_none_and_empty():
    assert _to_ms(None) is None
    assert _to_ms("") is None


def test_to_ms_garbage():
    assert _to_ms("not a date") is None


# ---- _iter_doc_ranges shapes ----

def test_iter_doc_ranges_list_form():
    payload = [
        {"id": "d1", "ranges": {"comments": [{"op": {"p": 0, "c": "x", "t": "t1"}}], "changes": []}},
    ]
    out = list(_iter_doc_ranges(payload))
    assert out == [("d1", [{"op": {"p": 0, "c": "x", "t": "t1"}}], [])]


def test_iter_doc_ranges_dict_form():
    payload = {"docs": [{"id": "d1", "ranges": {"comments": [], "changes": []}}]}
    out = list(_iter_doc_ranges(payload))
    assert out == [("d1", [], [])]


def test_iter_doc_ranges_empty():
    assert list(_iter_doc_ranges(None)) == []
    assert list(_iter_doc_ranges([])) == []


# ---- _extract_context ----

def test_extract_context_centers_on_anchor():
    text = "AAA the novel framework BBB"
    doc = _doc(text)
    idx = text.find("novel framework")
    ctx = _extract_context(doc, idx, "novel framework", 1)
    assert ctx.anchor == "novel framework"
    assert "AAA the" in ctx.before
    assert "BBB" in ctx.after
    # No truncation on a tiny string
    assert ctx.truncated_before is False
    assert ctx.truncated_after is False


def test_extract_context_truncates_long_text():
    text = "X" * 500 + " the novel framework " + "Y" * 500
    doc = _doc(text)
    idx = text.find("novel framework")
    ctx = _extract_context(doc, idx, "novel framework", 1)
    assert ctx.truncated_before is True
    assert ctx.truncated_after is True
    assert len(ctx.before) <= 200  # capped well below the wide capture window


def test_extract_context_handles_empty_doc():
    doc = _doc("")
    ctx = _extract_context(doc, 0, "anything", 1)
    assert ctx.anchor == "anything"


# ---- reviewer filter ----

def test_thread_matches_reviewer_substring():
    thread = Thread(
        id="t1",
        messages=[
            Message(id="m1", content="hi", timestamp_ms=1, user_id="u1",
                    user_name="Emma Pretty", user_email="emma@x.com"),
        ],
    )
    assert _thread_matches_reviewer(thread, ["emma"]) is True
    assert _thread_matches_reviewer(thread, ["EMMA"]) is True  # case-insensitive
    assert _thread_matches_reviewer(thread, ["bob"]) is False


def test_thread_matches_reviewer_empty_filter_passes_all():
    thread = Thread(id="t1", messages=[])
    assert _thread_matches_reviewer(thread, []) is True
    assert _thread_matches_reviewer(thread, ["", "  "]) is True


def test_slug_reviewer_safe_chars_only():
    assert _slug_reviewer("Emma Pretty") == "emma-pretty"
    assert _slug_reviewer("yxy.xinyi.yang") == "yxy-xinyi-yang"
    assert _slug_reviewer("Bob@example.com") == "bob-example-com"
    assert _slug_reviewer("") == "reviewer"  # fallback
