"""The highlighting path: what happens when comments share text, and what
happens when the text cannot be highlighted at all."""

from __future__ import annotations

from overleaf_comments_export.annotate import annotate_document, safe_insertion_point
from overleaf_comments_export.highlight import (
    apply_highlights, assign_colours, segment_spans, span_is_safe,
)
from overleaf_comments_export.model import AnchoredComment, Message, Thread


def _c(sid, text, phrase, tid):
    return AnchoredComment(
        thread_id=tid, short_id=sid, doc_id="d", pathname="p.tex",
        offset=text.index(phrase), anchored_text=phrase, line_no=1, col=0,
        nearest_heading="Method", stale=False)


def _t(tid, who, uid, body="a comment", resolved=False):
    return {tid: Thread(id=tid, resolved=resolved, messages=[
        Message(id="m", content=body, timestamp_ms=1, user_id=uid, user_name=who)])}


# ---- overlapping comments, which soul cannot nest ----

def test_two_people_on_overlapping_text_produce_three_segments():
    text = "participants wore the same HaptX gloves during every task"
    cs = [_c("C001", text, "the same HaptX gloves", "t1"),
          _c("C002", text, "HaptX gloves during", "t2")]
    th = {**_t("t1", "Emma", "u1"), **_t("t2", "Xinyi", "u2")}
    out, placed = apply_highlights(text, cs, th)
    assert out.count("\\pdfmarkupcomment") == 3
    assert "ocehlMulti" in out, "the shared part needs its own colour"
    assert all(p.highlighted for p in placed)


def test_one_person_twice_on_overlapping_text_uses_a_darker_shade():
    """The case a single reviewer commenting twice on the same words. It must
    not look like a second person, and must not look like a single comment."""
    text = "the sensory quality of the interaction was rated by participants"
    cs = [_c("C001", text, "the sensory quality of the interaction", "t1"),
          _c("C002", text, "quality of the interaction was rated", "t2")]
    th = {**_t("t1", "Emma", "u1"), **_t("t2", "Emma", "u1")}  # same user id
    out, placed = apply_highlights(text, cs, th)
    assert "ocehlAdark" in out, "doubling by one person should darken, not switch colour"
    assert "ocehlMulti" not in out, "one person is not several people"
    assert "2 comments on this text" in out


def test_three_comments_on_one_phrase_all_appear_in_the_popup():
    text = "the effect was significant across conditions"
    cs = [_c("C001", text, "the effect was significant", "t1"),
          _c("C002", text, "effect was significant across", "t2"),
          _c("C003", text, "was significant across conditions", "t3")]
    th = {**_t("t1", "Emma", "u1"), **_t("t2", "Xinyi", "u2"), **_t("t3", "Ana", "u3")}
    out, _ = apply_highlights(text, cs, th)
    for sid in ("C001", "C002", "C003"):
        assert sid in out


def test_a_comment_inside_another_is_split_not_nested():
    text = "an outer span containing an inner one inside it"
    cs = [_c("C001", text, "an outer span containing an inner one inside it", "t1"),
          _c("C002", text, "an inner one", "t2")]
    th = {**_t("t1", "Emma", "u1"), **_t("t2", "Xinyi", "u2")}
    out, _ = apply_highlights(text, cs, th)
    body = out[out.index("\\pdfmarkupcomment"):]
    # soul crashes on nesting, so no markup macro may contain another
    first_open = body.index("{", body.index("]"))
    assert "\\pdfmarkupcomment" not in body[first_open:body.index("}", first_open)]


def test_segments_cover_every_boundary():
    spans = [(0, 10, "a"), (5, 15, "b")]
    segs = segment_spans([(s, e, c) for s, e, c in spans])
    assert [(s.start, s.end) for s in segs] == [(0, 5), (5, 10), (10, 15)]


# ---- spans that cannot be highlighted ----

def test_maths_cannot_be_highlighted():
    text = r"the value $\eta_p^2 = 0.21$ was reported"
    ok, why = span_is_safe(text, text.index("$"), text.index("was"))
    assert not ok and "maths" in why


def test_a_latex_command_cannot_be_highlighted():
    text = r"a \textbf{bold} word"
    ok, why = span_is_safe(text, 2, text.index(" word"))
    assert not ok and "command" in why


def test_a_paragraph_break_cannot_be_crossed():
    text = "first para\n\nsecond para"
    assert not span_is_safe(text, 0, len(text))[0]


def test_a_percent_sign_cannot_be_highlighted():
    ok, why = span_is_safe("we saw 50% of them", 0, 18)
    assert not ok and "percent" in why


def test_unhighlightable_comments_are_reported_not_lost():
    text = r"the value $x=1$ here"
    cs = [_c("C001", text, "$x=1$", "t1")]
    out, placed = apply_highlights(text, cs, _t("t1", "Emma", "u1"))
    assert placed[0].highlighted is False
    assert "maths" in placed[0].reason
    assert "C001" in out, "it should still be pinned nearby"


def test_a_comment_whose_text_has_gone_is_listed_but_never_guessed_at():
    """Guessing a position dropped a note inside \\usepackage once. Never again."""
    text = "\\documentclass{article}\n\\usepackage[utf8]{inputenc}\n\\begin{document}\nbody\n\\end{document}"
    c = AnchoredComment(thread_id="t1", short_id="C001", doc_id="d", pathname="p.tex",
                        offset=40, anchored_text="text that is gone", line_no=1,
                        col=0, nearest_heading=None, stale=True)
    out, placed = apply_highlights(text, [c], _t("t1", "Emma", "u1"))
    assert placed[0].highlighted is False
    assert out == text, "nothing may be written when the position is unknown"
    assert "\\usepackage[utf8]{inputenc}" in out


# ---- never corrupt the document ----

def test_a_pin_never_splits_a_command():
    text = "\\begin{document}\nsee \\textbf{this} here\n\\end{document}"
    inside = text.index("textbf") + 3          # halfway through the command name
    pos = safe_insertion_point(text, inside, "")
    assert not text[:pos].endswith("\\tex"), "left inside a control word"
    assert text[pos - 1] in " {}\n" or text[:pos].endswith("textbf")


def test_nothing_is_ever_written_into_the_preamble():
    text = "\\documentclass{article}\n\\usepackage{amsmath}\n\\begin{document}\nbody\n\\end{document}"
    assert safe_insertion_point(text, 5, "") >= text.index("\\begin{document}")


# ---- colours ----

def test_colours_are_stable_between_runs():
    text = "alpha beta"
    cs = [_c("C001", text, "alpha", "t1"), _c("C002", text, "beta", "t2")]
    th = {**_t("t1", "Emma", "u1"), **_t("t2", "Xinyi", "u2")}
    assert assign_colours(cs, th) == assign_colours(list(reversed(cs)), th)


def test_the_same_person_under_two_display_names_keeps_one_colour():
    text = "alpha beta"
    cs = [_c("C001", text, "alpha", "t1"), _c("C002", text, "beta", "t2")]
    th = {**_t("t1", "Emma", "u1"), **_t("t2", "Emma Pretty", "u1")}  # same id
    assert len(set(assign_colours(cs, th).values())) == 1


def test_the_legend_and_the_list_are_both_added():
    text = "\\documentclass{article}\n\\begin{document}\n\\maketitle\nalpha here\n\\end{document}"
    out, _ = annotate_document(text, [_c("C001", text, "alpha", "t1")],
                               _t("t1", "Emma", "u1"))
    assert "Review comments" in out          # the list at the end
    assert "\\colorbox" in out               # the legend
    assert out.index("\\colorbox") < out.index("\\section*{Review comments}")
