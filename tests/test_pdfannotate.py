"""Writing the comments into the PDF Overleaf built.

These build a small PDF, annotate it, and read the annotations back, so the
whole path is exercised rather than the string handling alone.
"""

from __future__ import annotations

import pytest

pymupdf = pytest.importorskip("pymupdf")

from overleaf_comments_export.model import (  # noqa: E402
    AnchoredComment,
    Message,
    SourceContext,
    Thread,
)
from overleaf_comments_export.pdfannotate import (  # noqa: E402
    annotate_pdf,
    context_key,
    rendered_text,
    search_keys,
)

PAGE_ONE = (
    "We crossed three sensory environments in a controlled study of "
    "manual action. The gloves signalled contact but not its character, "
    "which is the distinction that matters here."
)
PAGE_TWO = (
    "The three force profiles did produce distinct perceived workload. "
    "We crossed three sensory environments again in the discussion."
)
SOURCE = (
    "\\section{Method}\n"
    + PAGE_ONE
    + "\n\n\\section{Discussion}\n"
    + PAGE_TWO
    + "\n"
)


def _pdf(*pages: str) -> bytes:
    doc = pymupdf.open()
    for body in pages:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 400, 700), body, fontsize=11)
    return doc.tobytes()


def _comment(short_id, anchor, thread_id, offset=None):
    at = SOURCE.index(anchor) if offset is None else offset
    return AnchoredComment(
        thread_id=thread_id, short_id=short_id, doc_id="d", pathname="main.tex",
        offset=at, anchored_text=anchor, line_no=1, col=1,
        nearest_heading="Method", stale=False, context=SourceContext(anchor=anchor),
    )


def _thread(tid, who, body, resolved=False, uid=None):
    return Thread(id=tid, resolved=resolved, messages=[
        Message(id=f"m{tid}", content=body, timestamp_ms=1000,
                user_id=uid or who, user_name=who)])


def _annots(pdf: bytes):
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    return [(p.number, a.info.get("title"), a.info.get("content"),
             tuple(round(v, 3) for v in (a.colors.get("stroke") or ())))
            for p in doc for a in (p.annots() or [])]


# --- turning source into something findable on the page ---

def test_citations_are_dropped_and_emphasis_kept():
    out = rendered_text("the \\emph{perceived} workload \\cite{hart1988} rose")
    assert "perceived workload" in out
    assert "hart1988" not in out


def test_maths_splits_rather_than_being_guessed_at():
    keys = search_keys("In a $3 \\times 3$ mixed design with 105 participants")
    assert "mixed design with 105 participants" in keys
    assert not any("times" in k for k in keys)


def test_a_short_span_is_found_using_what_follows_it():
    """A comment on one word cannot be located by that word alone."""
    text = "we tested VR against physical interaction in every block"
    key, mark = context_key(text, 10, 12)
    assert key.startswith("VR")
    assert mark == 2               # only "VR" gets marked, not the whole key


# --- the annotations themselves ---

def test_each_person_gets_their_own_colour():
    pdf = _pdf(PAGE_ONE, PAGE_TWO)
    threads = {"t1": _thread("t1", "Bakhtawar", "Break this up."),
               "t2": _thread("t2", "ans.ahmad", "Too conversational.")}
    comments = [_comment("C001", "manual action", "t1"),
                _comment("C002", "distinct perceived workload", "t2")]
    out, placed = annotate_pdf(pdf, SOURCE, comments, threads)
    assert all(p.highlighted for p in placed)
    colours = {who: col for _, who, _, col in _annots(out)}
    assert len(set(colours.values())) == 2, "two people, two colours"


def test_the_comment_text_travels_with_the_highlight():
    pdf = _pdf(PAGE_ONE)
    threads = {"t1": _thread("t1", "Bakhtawar", "Break this sentence up.")}
    out, _ = annotate_pdf(pdf, SOURCE, [_comment("C001", "manual action", "t1")], threads)
    _, who, content, _ = _annots(out)[0]
    assert who == "Bakhtawar"
    assert "Break this sentence up." in content
    assert "\\" not in content, "a PDF string is not TeX and must not be escaped"


def test_replies_are_carried_too():
    pdf = _pdf(PAGE_ONE)
    t = _thread("t1", "Bakhtawar", "Break this up.")
    t.messages.append(Message(id="m2", content="Agree", timestamp_ms=2000,
                              user_id="ans", user_name="ans.ahmad"))
    out, _ = annotate_pdf(pdf, SOURCE, [_comment("C001", "manual action", "t1")], {"t1": t})
    assert "Agree" in _annots(out)[0][2]


def test_overlapping_comments_get_the_shared_colour():
    """Two people on the same words is one highlight in its own colour, not two
    stacked on top of each other."""
    pdf = _pdf(PAGE_ONE)
    threads = {"t1": _thread("t1", "Bakhtawar", "One."),
               "t2": _thread("t2", "ans.ahmad", "Two.")}
    at = SOURCE.index("signalled contact but not its character")
    comments = [_comment("C001", "signalled contact but not", "t1", at),
                _comment("C002", "contact but not its character", "t2",
                         SOURCE.index("contact but not its character"))]
    out, placed = annotate_pdf(pdf, SOURCE, comments, threads)
    annots = _annots(out)
    assert len(annots) == 3, "left, shared, right"
    assert len({a[3] for a in annots}) == 3, "each part its own colour"
    shared = [a for a in annots if a[1] == "several reviewers"]
    assert len(shared) == 1
    assert "One." in shared[0][2] and "Two." in shared[0][2]


def test_a_repeated_phrase_lands_where_the_source_says():
    """"We crossed three sensory environments" is on both pages. The comment is
    on the second one, and that is where it has to go."""
    pdf = _pdf(PAGE_ONE, PAGE_TWO)
    threads = {"t1": _thread("t1", "Bakhtawar", "Repetition.")}
    at = SOURCE.rindex("We crossed three sensory environments")
    out, placed = annotate_pdf(
        pdf, SOURCE, [_comment("C001", "We crossed three sensory environments", "t1", at)],
        threads)
    assert placed[0].highlighted
    assert _annots(out)[0][0] == 1, "landed on the wrong copy of the phrase"


def test_a_comment_whose_text_has_gone_is_not_guessed_at():
    pdf = _pdf(PAGE_ONE)
    threads = {"t1": _thread("t1", "Bakhtawar", "Stale.")}
    c = _comment("C001", "text that is not there any more", "t1", 5)
    out, placed = annotate_pdf(pdf, SOURCE, [c], threads)
    assert not placed[0].highlighted
    assert "changed" in placed[0].reason
    assert not _annots(out), "nothing may be marked on a guess"


def test_resolved_comments_are_struck_through_in_grey():
    pdf = _pdf(PAGE_ONE)
    threads = {"t1": _thread("t1", "Bakhtawar", "Done.", resolved=True)}
    out, _ = annotate_pdf(pdf, SOURCE, [_comment("C001", "manual action", "t1")], threads)
    doc = pymupdf.open(stream=out, filetype="pdf")
    kinds = [a.type[1] for p in doc for a in (p.annots() or [])]
    assert kinds == ["StrikeOut"]


def test_every_comment_is_listed_even_when_it_could_not_be_placed():
    """Annotations do not print. Someone working on paper must still get them."""
    pdf = _pdf(PAGE_ONE)
    threads = {"t1": _thread("t1", "Bakhtawar", "Found me."),
               "t2": _thread("t2", "ans.ahmad", "Could not place me.")}
    comments = [_comment("C001", "manual action", "t1"),
                _comment("C002", "text that is not there any more", "t2", 5)]
    out, placed = annotate_pdf(pdf, SOURCE, comments, threads)
    doc = pymupdf.open(stream=out, filetype="pdf")
    listing = "".join(doc[p].get_text() for p in range(1, doc.page_count))
    assert "C001" in listing and "C002" in listing
    assert "Found me." in listing and "Could not place me." in listing
    assert "page 1" in listing, "a placed comment says where to look"


def test_the_original_pages_are_left_alone():
    pdf = _pdf(PAGE_ONE, PAGE_TWO)
    threads = {"t1": _thread("t1", "Bakhtawar", "One.")}
    out, _ = annotate_pdf(pdf, SOURCE, [_comment("C001", "manual action", "t1")], threads)
    before, after = pymupdf.open(stream=pdf, filetype="pdf"), pymupdf.open(stream=out, filetype="pdf")
    assert after.page_count > before.page_count, "the listing is appended"
    for i in range(before.page_count):
        assert before[i].get_text() == after[i].get_text()
