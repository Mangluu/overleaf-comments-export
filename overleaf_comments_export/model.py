from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Message:
    id: str
    content: str
    timestamp_ms: int
    user_id: str
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    edited_at_ms: Optional[int] = None


@dataclass
class Thread:
    id: str
    messages: list[Message] = field(default_factory=list)
    resolved: bool = False
    resolved_at_ms: Optional[int] = None
    resolved_by_user_id: Optional[str] = None


@dataclass
class SourceContext:
    """A compact snippet of LaTeX around an anchor.

    `before` / `after` are short character windows (whitespace-normalized) that
    immediately precede and follow the anchored phrase on the same logical line.
    `anchor` is the exact phrase the comment is attached to. `truncated_before`
    / `truncated_after` indicate whether content was clipped on either side
    (so a renderer can show "…").
    """
    before: str = ""
    anchor: str = ""
    after: str = ""
    truncated_before: bool = False
    truncated_after: bool = False
    line_no: int = 0  # 1-indexed line number the snippet was taken from


@dataclass
class AnchoredComment:
    thread_id: str
    short_id: str  # human-friendly stable id like "C001"
    doc_id: str
    pathname: str
    offset: int
    anchored_text: str
    line_no: int
    col: int
    nearest_heading: Optional[str]
    stale: bool
    context: Optional[SourceContext] = None
    # The figure or table this sits inside, when it sits inside one. Reviewers
    # comment on captions constantly, and a line number in a float says little.
    float_ref: Optional["Float"] = None


@dataclass
class TrackedChange:
    id: str
    short_id: str  # like "T001"
    doc_id: str
    pathname: str
    kind: str  # "insertion" or "deletion"
    content: str
    offset: int
    line_no: int
    col: int
    nearest_heading: Optional[str]
    user_id: Optional[str]
    user_name: Optional[str]
    user_email: Optional[str]
    timestamp_ms: Optional[int]
    context: Optional[SourceContext] = None


@dataclass
class Heading:
    line_no: int
    level: int  # 1=section, 2=subsection, 3=subsubsection
    text: str


@dataclass
class Float:
    """A figure or table environment, and where it sits in the source."""
    kind: str                  # "figure" or "table"
    number: int | None         # as LaTeX would number it, None when uncaptioned
    caption: Optional[str]
    label: Optional[str]
    start: int                 # char offset of \begin
    end: int                   # char offset just past \end
    line_no: int

    def describe(self) -> str:
        """How it should read to someone working through comments."""
        name = self.kind.capitalize()
        head = f"{name} {self.number}" if self.number else f"an unnumbered {self.kind}"
        return f"{head} (`{self.label}`)" if self.label else head


@dataclass
class DocText:
    doc_id: str
    pathname: str
    text: str
    line_starts: list[int]
    headings: list[Heading]
    floats: list["Float"] = field(default_factory=list)
