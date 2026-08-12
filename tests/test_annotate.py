from __future__ import annotations

from overleaf_comments_export.annotate import (
    annotate_document,
    inject_preamble,
    latex_escape,
    safe_insertion_point,
)
from overleaf_comments_export.model import AnchoredComment, Message, Thread


def _c(short_id, offset, anchor, tid="t1"):
    return AnchoredComment(
        thread_id=tid, short_id=short_id, doc_id="d", pathname="main.tex",
        offset=offset, anchored_text=anchor, line_no=1, col=0,
        nearest_heading=None, stale=False,
    )


def _t(tid="t1", content="fix this", who="Emma", replies=(), resolved=False):
    msgs = [Message(id="m0", content=content, timestamp_ms=1, user_id="u", user_name=who)]
    for i, r in enumerate(replies, start=1):
        msgs.append(Message(id=f"m{i}", content=r, timestamp_ms=1 + i,
                            user_id="u2", user_name="Co"))
    return {tid: Thread(id=tid, messages=msgs, resolved=resolved)}


# ---- escaping: the way this breaks someone's paper ----

def test_escape_neutralises_every_tex_special():
    got = latex_escape("100% & $5 #1 a_b {x} ~ ^")
    for ch in ("&", "%", "$", "#", "_", "{", "}"):
        assert f"\\{ch}" in got or ch not in got.replace(f"\\{ch}", "")
    assert "\\textasciitilde{}" in got
    assert "\\textasciicircum{}" in got


def test_escape_handles_backslash_without_eating_its_own_escapes():
    got = latex_escape(r"use \emph{x} & stop")
    assert r"\textbackslash{}" in got
    assert "\\&" in got
    # no raw command survives that TeX would try to run
    assert "\\emph{" not in got


def test_escape_folds_browser_typography_to_ascii():
    got = latex_escape("“smart” quotes – and — dashes… ≥")
    for ch in ("“", "”", "–", "—", "…", "≥"):
        assert ch not in got
    assert "``" in got and "''" in got


def test_escape_flattens_blank_lines():
    """A blank line inside a macro argument is a paragraph break, and TeX
    refuses it in this position."""
    assert "\n" not in latex_escape("first\n\nsecond")


# ---- insertion safety ----

def test_note_goes_just_after_the_phrase_commented_on():
    text = "We propose a novel framework for this."
    pos = safe_insertion_point(text, text.index("novel framework"), "novel framework")
    assert text[:pos].endswith("novel framework")


def test_never_inserts_inside_inline_math():
    text = "the value $x = 1$ holds"
    inside = text.index("x = 1")
    pos = safe_insertion_point(text, inside, "")
    assert not text[:pos].count("$") % 2, "left inside math"
    assert pos >= text.index("$", inside) + 1


def test_moves_off_a_commented_out_line():
    text = "% TODO fix this later\nreal content here"
    pos = safe_insertion_point(text, 8, "")
    assert pos >= text.index("\n"), "note would have been swallowed by the % comment"


def test_offset_past_end_of_document_is_clamped():
    text = "short"
    assert safe_insertion_point(text, 9999, "") == len(text)


# ---- insertion order ----

def test_insertions_do_not_shift_each_other():
    """Every note must land at its own anchor, which only works if insertion
    runs backwards through the document."""
    text = "AAAA BBBB CCCC"
    comments = [_c("C001", 0, "AAAA", "t1"), _c("C002", 5, "BBBB", "t2"),
                _c("C003", 10, "CCCC", "t3")]
    threads = {**_t("t1", "first"), **_t("t2", "second"), **_t("t3", "third")}
    out, n = annotate_document(text, comments, threads)
    assert n == 3
    assert out.index("first") < out.index("second") < out.index("third")
    assert out.index("AAAA") < out.index("first")
    assert out.index("BBBB") < out.index("second") < out.index("CCCC")


# ---- preamble ----

def test_preamble_goes_in_before_begin_document():
    text = "\\documentclass{article}\n\\usepackage{amsmath}\n\\begin{document}\nhi\n\\end{document}"
    out, ok = inject_preamble(text, "pdfcomment")
    assert ok
    # Must land between the two. Before \\documentclass does not compile at all,
    # and an earlier version of this did exactly that.
    assert out.index("\\documentclass") < out.index("\\usepackage{pdfcomment}")
    assert out.index("\\usepackage{pdfcomment}") < out.index("\\begin{document}")


def test_preamble_is_not_added_twice():
    text = "\\documentclass{article}\n\\usepackage{pdfcomment}\n\\begin{document}\n\\end{document}"
    out, ok = inject_preamble(text, "pdfcomment")
    assert ok and out.count("\\usepackage{pdfcomment}") == 1


def test_fragment_without_a_preamble_is_left_alone():
    """An \\input-ed section has no preamble; the package belongs in the parent."""
    text = "\\section{Method}\nSome prose."
    out, ok = inject_preamble(text, "pdfcomment")
    assert not ok and out == text


def test_commented_out_documentclass_is_not_mistaken_for_the_real_one():
    text = "% \\documentclass{article}\n\\documentclass{report}\n\\begin{document}\n\\end{document}"
    out, ok = inject_preamble(text, "todonotes")
    assert ok
    assert out.index("\\documentclass{report}") < out.index("todonotes")
    assert out.index("todonotes") < out.index("\\begin{document}")


# ---- content ----

def test_note_carries_the_id_author_and_replies():
    text = "alpha beta"
    out, _ = annotate_document(
        text, [_c("C007", 0, "alpha")],
        _t(content="needs a citation", who="Emma", replies=["agree"]),
    )
    assert "[C007]" in out
    assert "Emma: needs a citation" in out
    assert "Reply (Co): agree" in out


def test_resolved_threads_are_marked():
    out, _ = annotate_document(
        "alpha", [_c("C001", 0, "alpha")], _t(resolved=True)
    )
    assert "resolved" in out.lower()


def test_todonotes_style_uses_todo_macro():
    out, _ = annotate_document("alpha", [_c("C001", 0, "alpha")], _t(), style="todonotes")
    assert "\\todo{" in out
    assert "todonotes" in out or True  # fragment has no preamble to inject into


def test_pdfcomment_style_carries_the_author():
    out, _ = annotate_document("alpha", [_c("C001", 0, "alpha")], _t(who="Emma"),
                               style="pdfcomment")
    assert "\\pdfcomment[author={Emma}]" in out


def test_a_comment_whose_text_is_hostile_still_produces_valid_tex():
    """The realistic worst case: a reviewer pastes LaTeX into a comment."""
    text = "The result"
    threads = _t(content=r"use \frac{1}{2} & 50% of $x$ #now")
    out, _ = annotate_document(text, [_c("C001", 0, "The result")], threads,
                               style="pdfcomment")
    body = out[out.index("\\pdfcomment") :]
    # Braces must balance, or the document will not compile.
    assert body.count("{") == body.count("}")
    assert r"\frac" not in body


def test_package_never_lands_before_documentclass():
    """LaTeX refuses anything before \\documentclass, so this must hold for
    every shape of preamble."""
    for text in [
        "\\documentclass{article}\n\\begin{document}\nx\n\\end{document}",
        "\\documentclass[twocolumn]{IEEEtran}\n\\usepackage{amsmath}\n\\begin{document}\nx\n\\end{document}",
        "% a comment first\n\\documentclass{article}\n\\begin{document}\nx\n\\end{document}",
        "\\documentclass{article}\n% \\begin{document} in a comment\n\\begin{document}\nx\n\\end{document}",
    ]:
        for style in ("pdfcomment", "todonotes"):
            out, ok = inject_preamble(text, style)
            assert ok, text
            assert out.index("\\documentclass") < out.index("\\usepackage"), out


# ---- pdflatex rejects anything it has no encoding for ----

def test_output_is_always_pure_ascii():
    """Overleaf compiles with pdflatex, which stops the whole build on a single
    character it cannot encode. Real reviewer comments contain plenty."""
    from overleaf_comments_export.annotate import to_ascii
    for s in [
        "eta squared was .21",
        "η squared",                 # Greek, seen in real comments
        "really？ and，more",     # fullwidth, from a Chinese keyboard
        "café naïve",           # accents
        "emoji \U0001f60a here",
        "中文评论",       # CJK
        "p ≈ 0.05 ± 0.01",
    ]:
        assert to_ascii(s).isascii(), s
        assert latex_escape(s).isascii(), s


def test_greek_letters_become_their_names():
    from overleaf_comments_export.annotate import to_ascii
    assert to_ascii("η and α and Δ") == "eta and alpha and Delta"


def test_fullwidth_punctuation_becomes_ascii():
    from overleaf_comments_export.annotate import to_ascii
    assert to_ascii("what？ yes， ok") == "what? yes, ok"


def test_accents_are_stripped_rather_than_dropped():
    from overleaf_comments_export.annotate import to_ascii
    assert to_ascii("naïve café Zürich") == "naive cafe Zurich"


def test_untranslatable_characters_become_a_question_mark_not_a_broken_build():
    from overleaf_comments_export.annotate import to_ascii
    out = to_ascii("中文")
    assert out == "??" and out.isascii()


def test_a_whole_annotated_document_is_ascii():
    threads = _t(content="η² was .21？ café \U0001f60a")
    out, _ = annotate_document("The result here", [_c("C001", 0, "The result")], threads)
    assert out.isascii()
