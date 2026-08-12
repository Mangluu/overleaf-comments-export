"""Awkward input, at both ends.

Real papers are not the tidy samples the other tests use. They contain verbatim
blocks, tables, maths, accented names, comments piled on the same sentence, and
occasionally a PDF with no text in it at all. Nothing here should raise, and
nothing should be quietly lost: every comment must come back accounted for,
either marked or with a reason.
"""

from __future__ import annotations

import random
import string

import pytest

from overleaf_comments_export.annotate import annotate_document, to_ascii
from overleaf_comments_export.highlight import apply_highlights
from overleaf_comments_export.model import (
    AnchoredComment,
    Message,
    SourceContext,
    Thread,
)

pymupdf = pytest.importorskip("pymupdf")

from overleaf_comments_export.pdfannotate import annotate_pdf  # noqa: E402

NASTY = r"""\documentclass{article}
\usepackage[utf8]{inputenc}
\begin{document}
\section{Results \& Discussion}
We found that 50\% of trials with $\eta_p^2 = .21$ improved, see \cite{a,b}.
\begin{verbatim}
this is verbatim \not{a} command $x$ 100%
\end{verbatim}
\begin{table}[t]\begin{tabular}{l|r}
A & 1 \\ B & 2 \\
\end{tabular}\end{table}
A footnote\footnote{with \emph{markup} inside} and a ~tilde~ and a \_underscore.
\[ \sum_{i=1}^{n} x_i \]
The naive resume of Zoe Muller cost \$5 \# 3 \^{} 2.
\end{document}
"""


def _c(short_id, anchor, thread_id, text=NASTY, doc_id="d", occurrence=0):
    at = -1
    for _ in range(occurrence + 1):
        at = text.find(anchor, at + 1)
    assert at >= 0, f"{anchor!r} not in the source"
    return AnchoredComment(
        thread_id=thread_id, short_id=short_id, doc_id=doc_id, pathname="main.tex",
        offset=at, anchored_text=anchor, line_no=1, col=1, nearest_heading="Results",
        stale=False, context=SourceContext(anchor=anchor))


def _t(tid, who="A. Reviewer", body="A comment."):
    return Thread(id=tid, messages=[Message(
        id=f"m{tid}", content=body, timestamp_ms=1, user_id=who, user_name=who)])


def _accounted(placed, comments):
    """Every comment came back exactly once, and an unplaced one says why."""
    assert len(placed) == len(comments)
    assert {p.comment.short_id for p in placed} == {c.short_id for c in comments}
    for p in placed:
        assert p.highlighted or p.reason, f"{p.comment.short_id} vanished without a reason"


# --- the LaTeX route ---

@pytest.mark.parametrize("anchor", [
    "Results \\& Discussion",
    "50\\% of trials",
    "$\\eta_p^2 = .21$",
    "this is verbatim \\not{a} command",
    "A & 1",
    "with \\emph{markup} inside",
    "\\sum_{i=1}^{n} x_i",
    "\\$5 \\# 3",
    "improved, see \\cite{a,b}",
])
def test_awkward_spans_never_break_the_document(anchor):
    comments = [_c("C001", anchor, "t1")]
    out, n = annotate_document(NASTY, comments, {"t1": _t("t1")}, style="highlight")
    out.encode("ascii")
    assert out.count("\\begin{document}") == 1
    assert out.count("\\documentclass") == 1
    # Braces must still balance, or the document will not compile.
    assert out.count("{") - out.count("\\{") == out.count("}") - out.count("\\}")


def test_a_pile_of_comments_on_one_sentence():
    """Ten people on the same words is the case that broke soul."""
    anchor = "We found that 50\\% of trials"
    comments = [_c(f"C{i:03}", anchor, f"t{i}") for i in range(10)]
    threads = {f"t{i}": _t(f"t{i}", who=f"Reviewer {i}") for i in range(10)}
    out, placed = apply_highlights(NASTY, comments, threads)
    _accounted(placed, comments)
    out.encode("ascii")


def test_comments_at_the_very_start_and_end_of_the_file():
    text = "\\documentclass{article}\\begin{document}Hello world here.\\end{document}"
    comments = [_c("C001", "Hello world here", "t1", text=text)]
    out, placed = apply_highlights(text, comments, {"t1": _t("t1")})
    _accounted(placed, comments)


def test_an_empty_anchor_is_not_guessed_at():
    c = AnchoredComment(thread_id="t1", short_id="C001", doc_id="d", pathname="m.tex",
                        offset=10, anchored_text="", line_no=1, col=1,
                        nearest_heading=None, stale=True, context=SourceContext(anchor=""))
    out, placed = apply_highlights(NASTY, [c], {"t1": _t("t1")})
    _accounted(placed, [c])
    assert not placed[0].highlighted


def test_an_offset_past_the_end_of_the_file():
    c = AnchoredComment(thread_id="t1", short_id="C001", doc_id="d", pathname="m.tex",
                        offset=10 ** 6, anchored_text="anything", line_no=1, col=1,
                        nearest_heading=None, stale=True, context=SourceContext(anchor="x"))
    out, placed = apply_highlights(NASTY, [c], {"t1": _t("t1")})
    assert not placed[0].highlighted


def test_reviewer_text_cannot_break_the_build():
    """A comment is arbitrary text typed by a person. It may be LaTeX."""
    hostile = "\\end{document} $x$ 100% \\input{/etc/passwd} } { \\\\ ~ ^ & #"
    out, _ = annotate_document(
        NASTY, [_c("C001", "improved", "t1")], {"t1": _t("t1", body=hostile)},
        style="highlight")
    out.encode("ascii")
    assert out.count("\\end{document}") == 1, "reviewer text escaped into the document"


def test_random_overlapping_spans_always_balance():
    """Fuzz the overlap handling, which is where the nesting rules bite."""
    rng = random.Random(20260812)
    body = " ".join("".join(rng.choices(string.ascii_lowercase, k=rng.randint(3, 9)))
                    for _ in range(400))
    text = "\\documentclass{article}\n\\begin{document}\n" + body + "\n\\end{document}\n"
    start_of_body = text.index(body)
    for round_no in range(25):
        comments, threads = [], {}
        for i in range(rng.randint(2, 12)):
            a = rng.randint(0, len(body) - 60)
            b = a + rng.randint(5, 60)
            comments.append(AnchoredComment(
                thread_id=f"t{i}", short_id=f"C{i:03}", doc_id="d", pathname="m.tex",
                offset=start_of_body + a, anchored_text=body[a:b], line_no=1, col=1,
                nearest_heading=None, stale=False,
                context=SourceContext(anchor=body[a:b])))
            threads[f"t{i}"] = _t(f"t{i}", who=f"R{i % 3}")
        out, placed = apply_highlights(text, comments, threads)
        _accounted(placed, comments)
        assert out.count("{") - out.count("\\{") == out.count("}") - out.count("\\}"), round_no


# --- the PDF route ---

def _pdf(*pages: str) -> bytes:
    doc = pymupdf.open()
    for body in pages:
        doc.new_page().insert_textbox(pymupdf.Rect(40, 40, 420, 760), body, fontsize=10)
    return doc.tobytes()


def test_a_pdf_with_no_text_in_it_at_all():
    """A scan, or a paper that is one big figure. Nothing to match against."""
    doc = pymupdf.open()
    doc.new_page()
    comments = [_c("C001", "improved", "t1")]
    out, placed = annotate_pdf(doc.tobytes(), {"d": NASTY}, comments, {"t1": _t("t1")})
    _accounted(placed, comments)
    assert not placed[0].highlighted
    assert pymupdf.open(stream=out, filetype="pdf").page_count >= 2, "listing still written"


def test_comments_from_several_source_files():
    """A paper split across files is still one PDF. None may be dropped."""
    intro = "\\section{Introduction}\nThe opening claim needs a citation here.\n"
    method = "\\section{Method}\nParticipants completed three blocks in one sitting.\n"
    pdf = _pdf("The opening claim needs a citation here.",
               "Participants completed three blocks in one sitting.")
    comments = [_c("C001", "opening claim needs a citation", "t1", text=intro, doc_id="a"),
                _c("C002", "completed three blocks", "t2", text=method, doc_id="b")]
    out, placed = annotate_pdf(pdf, {"a": intro, "b": method}, comments,
                               {"t1": _t("t1"), "t2": _t("t2", who="B. Reviewer")})
    _accounted(placed, comments)
    assert all(p.highlighted for p in placed), [p.reason for p in placed]


def test_a_source_file_that_was_not_exported_is_reported_not_dropped():
    comments = [_c("C001", "improved", "t1", doc_id="missing")]
    _, placed = annotate_pdf(_pdf("nothing relevant"), {"d": NASTY}, comments, {"t1": _t("t1")})
    _accounted(placed, comments)
    assert "not exported" in placed[0].reason


def test_many_comments_stay_quick():
    """200 comments over 40 pages must not take minutes."""
    import time

    sentences = [f"Sentence number {i} describes a distinct finding of the study."
                 for i in range(200)]
    text = "\\begin{document}\n" + "\n\n".join(sentences) + "\n\\end{document}"
    pdf = _pdf(*["\n\n".join(sentences[i:i + 5]) for i in range(0, 200, 5)])
    comments = [_c(f"C{i:03}", sentences[i][:40], f"t{i}", text=text) for i in range(200)]
    threads = {f"t{i}": _t(f"t{i}", who=f"R{i % 4}") for i in range(200)}
    began = time.monotonic()
    _, placed = annotate_pdf(pdf, {"d": text}, comments, threads)
    took = time.monotonic() - began
    _accounted(placed, comments)
    assert sum(1 for p in placed if p.highlighted) > 190
    assert took < 60, f"took {took:.1f}s"


def test_accented_names_and_text_survive_the_pdf_route():
    """A PDF string is not TeX, so nothing here needs escaping, but it must not
    raise either."""
    src = "\\begin{document}\nThe naive resume was reviewed carefully.\n\\end{document}"
    t = Thread(id="t1", messages=[Message(
        id="m", content="Résumé needs an accent — see Müller & Søren’s point.",
        timestamp_ms=1, user_id="u", user_name="Zoë Müller")])
    out, placed = annotate_pdf(_pdf("The naive resume was reviewed carefully."),
                               {"d": src}, [_c("C001", "resume was reviewed", "t1", text=src)],
                               {"t1": t})
    assert placed[0].highlighted
    doc = pymupdf.open(stream=out, filetype="pdf")
    annot = next(a for p in doc for a in (p.annots() or []))
    assert "Müller" in annot.info["content"]


def test_to_ascii_never_returns_anything_unprintable():
    rng = random.Random(7)
    sample = "".join(chr(rng.randrange(0x20, 0x2FFF)) for _ in range(4000))
    out = to_ascii(sample)
    out.encode("ascii")


def test_a_comment_far_too_long_for_a_page_is_trimmed_not_dropped():
    """Reviewers paste whole paragraphs, and once a whole draft reply."""
    huge = "This needs rewriting because " * 900
    src = "\\begin{document}\nThe opening claim needs support.\n\\end{document}"
    out, placed = annotate_pdf(
        _pdf("The opening claim needs support."), {"d": src},
        [_c("C001", "opening claim needs support", "t1", text=src)],
        {"t1": _t("t1", body=huge)})
    assert placed[0].highlighted
    doc = pymupdf.open(stream=out, filetype="pdf")
    listing = "".join(doc[i].get_text() for i in range(1, doc.page_count))
    assert "C001" in listing and "This needs rewriting" in listing


def test_the_listing_pages_cleanly_for_a_lot_of_comments():
    src = "\\begin{document}\n" + "\n\n".join(
        f"Finding number {i} is reported in this sentence." for i in range(120)
    ) + "\n\\end{document}"
    comments = [_c(f"C{i:03}", f"Finding number {i} is reported", f"t{i}", text=src)
                for i in range(120)]
    threads = {f"t{i}": _t(f"t{i}", who=f"R{i % 3}", body=f"Point {i}. " * 12)
               for i in range(120)}
    out, placed = annotate_pdf(_pdf("nothing here"), {"d": src}, comments, threads)
    _accounted(placed, comments)
    doc = pymupdf.open(stream=out, filetype="pdf")
    listing = "".join(doc[i].get_text() for i in range(1, doc.page_count))
    for i in (0, 47, 119):
        assert f"C{i:03}" in listing, f"C{i:03} fell off the listing"
