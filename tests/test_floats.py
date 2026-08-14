"""Saying which figure or table a comment sits in.

Issue #2. Reviewers comment on captions constantly, and a line number inside a
float says very little. The nearest heading is often wrong too, because a float
drifts away from the section it was written next to.
"""

from __future__ import annotations

from overleaf_comments_export.anchors import build_line_starts
from overleaf_comments_export.sections import enclosing_float, find_floats


def _floats(tex: str):
    return find_floats(tex, build_line_starts(tex))


SIMPLE = r"""
\section{Results}
\begin{figure}[htbp]
  \includegraphics{spi.png}
  \caption{Mean rating by condition.}
  \label{fig:spi-by-condition}
\end{figure}
Text after the figure.
"""


def test_a_figure_is_found_numbered_and_named():
    f, = _floats(SIMPLE)
    assert (f.kind, f.number, f.label) == ("figure", 1, "fig:spi-by-condition")
    assert f.caption == "Mean rating by condition."
    assert f.describe() == "Figure 1 (`fig:spi-by-condition`)"


def test_an_anchor_inside_the_float_finds_it_and_one_outside_does_not():
    floats = _floats(SIMPLE)
    assert enclosing_float(floats, SIMPLE.index("Mean rating")) is floats[0]
    assert enclosing_float(floats, SIMPLE.index("Text after")) is None
    assert enclosing_float(floats, SIMPLE.index("Results")) is None


def test_figures_and_tables_count_separately():
    tex = (r"\begin{figure}\caption{A}\end{figure}"
           r"\begin{table}\caption{B}\end{table}"
           r"\begin{figure}\caption{C}\end{figure}")
    got = [(f.kind, f.number) for f in _floats(tex)]
    assert got == [("figure", 1), ("table", 1), ("figure", 2)]


def test_the_starred_form_shares_its_counter():
    """figure* is the two-column form. LaTeX numbers it in the same sequence."""
    tex = (r"\begin{figure}\caption{A}\end{figure}"
           r"\begin{figure*}\caption{B}\end{figure*}")
    assert [(f.kind, f.number) for f in _floats(tex)] == [("figure", 1), ("figure", 2)]


def test_an_uncaptioned_float_takes_no_number():
    """LaTeX only steps the counter for a caption, so neither do we. The float
    is still recorded, so a comment in it can say it is in a figure."""
    tex = (r"\begin{figure}\includegraphics{a.png}\end{figure}"
           r"\begin{figure}\caption{First numbered.}\end{figure}")
    a, b = _floats(tex)
    assert a.number is None and a.describe() == "an unnumbered figure"
    assert b.number == 1, "an uncaptioned float must not consume a number"


def test_a_subfigure_caption_is_not_taken_for_the_whole_figure():
    tex = r"""\begin{figure}
      \begin{subfigure}{.5\textwidth}\caption{the left panel}\label{fig:left}\end{subfigure}
      \begin{subfigure}{.5\textwidth}\caption{the right panel}\label{fig:right}\end{subfigure}
      \caption{Both panels together.}\label{fig:both}
    \end{figure}"""
    f, = _floats(tex)
    assert f.caption == "Both panels together."
    assert f.label == "fig:both"


def test_a_float_nested_in_a_float_does_not_produce_two_entries():
    tex = r"""\begin{figure}
      \begin{table}\caption{inner}\end{table}
      \caption{outer}\label{fig:outer}
    \end{figure}"""
    f, = _floats(tex)
    assert f.kind == "figure" and f.caption == "outer"


def test_a_commented_out_float_is_ignored():
    tex = ("% \\begin{figure}\\caption{not real}\\end{figure}\n"
           "\\begin{figure}\\caption{real}\\end{figure}")
    f, = _floats(tex)
    assert f.caption == "real" and f.number == 1


def test_a_caption_with_braces_inside_it_is_read_whole():
    tex = r"\begin{figure}\caption{The \textbf{bold} bit and $x_{i}$.}\label{f}\end{figure}"
    f, = _floats(tex)
    assert f.caption == r"The \textbf{bold} bit and $x_{i}$."


def test_a_short_caption_option_is_skipped():
    tex = r"\begin{figure}\caption[short]{The long one.}\end{figure}"
    assert _floats(tex)[0].caption == "The long one."


def test_an_unclosed_float_does_not_run_away_or_raise():
    tex = r"\begin{figure}\caption{No end tag here.}"
    f, = _floats(tex)
    assert f.end == len(tex)


def test_a_document_with_no_floats_gives_nothing():
    assert _floats(r"\section{Method}\nJust prose.") == []
    assert enclosing_float([], 5) is None
