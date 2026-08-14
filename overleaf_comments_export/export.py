from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import __version__
from .anchors import build_line_starts, resolve_anchor
from .annotate import ANNOTATE_STYLES, annotate_document
from .client import OverleafClient, UserFacingError, parse_project_id
from .filenames import index_zip, name_for
from .model import (
    AnchoredComment,
    DocText,
    Message,
    SourceContext,
    Thread,
    TrackedChange,
)
from .render import render_markdown, render_response_letter
from .sections import find_headings, nearest_heading

SCHEMA_VERSION = "1.3"
# Characters of surrounding text captured on either side of an anchor. The
# renderer clips this to ~70 chars for compact mode and shows the full window
# for detailed mode, so the larger capture costs us at most a few KB per
# project but gives detailed mode actual extra context to show.
CONTEXT_CHARS_BEFORE = 160
CONTEXT_CHARS_AFTER = 160

logger = logging.getLogger("overleaf_comments_export")


def _to_ms(value: Any) -> int | None:
    """Accept ms-int, numeric string, or ISO 8601 string. Return ms since epoch."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
            return int(s)
        try:
            iso = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            return None
    return None

ProgressCallback = Callable[[str], None]
# Returns True when the user has asked for the export to stop.
CancelCheck = Callable[[], bool]


class ExportCancelled(Exception):
    """The user asked for the export to stop.

    Not an error. Nothing is half-written when this is raised, because the
    checks sit between steps rather than inside them.
    """


def _noop_progress(_: str) -> None:
    pass


def _stop_if_asked(should_cancel: CancelCheck | None) -> None:
    """Cooperative cancellation.

    A network call already in flight cannot be interrupted from here, and
    neither can reading a browser's cookie store, so the checks sit at every
    step boundary and inside the loops that do the repeated work. In practice
    that is where an export spends its time, so stopping takes effect within a
    document rather than at the very end.
    """
    if should_cancel is not None and should_cancel():
        raise ExportCancelled()


@dataclass
class ExportResult:
    project_id: str
    markdown_path: Path
    json_path: Path
    log_path: Path
    thread_count: int
    open_count: int
    resolved_count: int
    tracked_change_count: int
    stale_anchor_count: int
    jsonl_path: Path | None = None
    by_reviewer_dir: Path | None = None
    agents_path: Path | None = None
    response_letter_path: Path | None = None
    annotated_dir: Path | None = None
    annotated_pdf_path: Path | None = None
    source_dir: Path | None = None


def _build_user_map(threads_raw: dict[str, Any]) -> dict[str, dict[str, str]]:
    users: dict[str, dict[str, str]] = {}
    for thread in threads_raw.values():
        if not isinstance(thread, dict):
            continue
        for msg in thread.get("messages", []) or []:
            uid = msg.get("user_id") or msg.get("userId")
            if not uid:
                continue
            user = msg.get("user") or {}
            name = (
                user.get("name")
                or " ".join(
                    p for p in [user.get("first_name"), user.get("last_name")] if p
                ).strip()
                or None
            )
            email = user.get("email")
            existing = users.setdefault(str(uid), {})
            if name and not existing.get("name"):
                existing["name"] = name
            if email and not existing.get("email"):
                existing["email"] = email
    return users


def _parse_threads(threads_raw: dict[str, Any]) -> dict[str, Thread]:
    out: dict[str, Thread] = {}
    for tid, t in threads_raw.items():
        if not isinstance(t, dict):
            continue
        messages: list[Message] = []
        for m in t.get("messages", []) or []:
            user = m.get("user") or {}
            name = (
                user.get("name")
                or " ".join(
                    p for p in [user.get("first_name"), user.get("last_name")] if p
                ).strip()
                or None
            )
            messages.append(
                Message(
                    id=str(m.get("id") or m.get("_id") or ""),
                    content=m.get("content") or "",
                    timestamp_ms=_to_ms(m.get("timestamp")) or 0,
                    user_id=str(m.get("user_id") or m.get("userId") or ""),
                    user_name=name,
                    user_email=user.get("email"),
                    edited_at_ms=_to_ms(m.get("edited_at")),
                )
            )
        out[tid] = Thread(
            id=tid,
            messages=messages,
            resolved=bool(t.get("resolved", False)),
            resolved_at_ms=_to_ms(t.get("resolved_at")),
            resolved_by_user_id=(
                str(t["resolved_by_user_id"]) if t.get("resolved_by_user_id") else None
            ),
        )
    return out


def safe_relative(pathname: str, doc_id: str) -> Path:
    """A project path turned into something safe to write inside the export.

    The name reaches us from Overleaf's file tree or, when that is unavailable,
    from a member name inside the project zip. Zip entries are allowed to say
    `../../elsewhere`, and a path like that would write outside the folder the
    user chose. Overleaf is not hostile, but writing files is not the place to
    rely on that.
    """
    if pathname.startswith("<unknown-"):
        return Path(f"unknown-{doc_id}.tex")
    parts = [
        part for part in Path(pathname.replace("\\", "/")).parts
        if part not in ("..", ".", "/") and not part.endswith(":")
    ]
    return Path(*parts) if parts else Path(f"unknown-{doc_id}.tex")


def _build_doc_text(doc_id: str, pathname: str, text: str) -> DocText:
    # Always extract LaTeX headings — the doc text we get from Overleaf IS
    # LaTeX, even when our file-tree mapping fell back to "<unknown-...>".
    line_starts = build_line_starts(text)
    headings = find_headings(text, line_starts)
    return DocText(
        doc_id=doc_id,
        pathname=pathname,
        text=text,
        line_starts=line_starts,
        headings=headings,
    )


_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_ws(s: str) -> str:
    return _WHITESPACE_RE.sub(" ", s).strip()


def _extract_context(
    doc: DocText,
    offset: int,
    anchored_text: str,
    line_no: int,
    *,
    before: int = CONTEXT_CHARS_BEFORE,
    after: int = CONTEXT_CHARS_AFTER,
) -> SourceContext:
    """Build a compact char-window snippet around the anchor.

    Slices `before` chars before the offset and `after` chars after the
    end of the anchored text. Newlines/extra whitespace are collapsed so the
    snippet renders on a single line. If we couldn't resolve `anchored_text`
    to a slice of the doc, the anchor field is the original phrase verbatim.
    """
    text = doc.text
    n_text = len(text)
    if n_text == 0:
        return SourceContext(anchor=anchored_text, line_no=line_no)

    n_anchor = len(anchored_text)
    end_offset = offset + n_anchor

    # If the doc text doesn't match at offset, we still want a useful snippet
    # — center on whatever's at `offset`.
    actual_anchor = anchored_text
    if not (
        n_anchor > 0
        and 0 <= offset <= n_text - n_anchor
        and text[offset:end_offset] == anchored_text
    ):
        # Fall back to whatever's at the offset (anchored_text may be empty
        # or stale). Use a short clip so we still bound the snippet.
        if n_anchor == 0:
            anchor_clip_len = min(40, max(0, n_text - offset))
            actual_anchor = text[offset : offset + anchor_clip_len]
            end_offset = offset + anchor_clip_len
        # If anchored_text was non-empty but didn't match, keep it as the
        # nominal anchor — the inline renderer will show it in brackets.

    before_slice = text[max(0, offset - before) : offset]
    after_slice = text[end_offset : min(n_text, end_offset + after)]

    return SourceContext(
        before=_normalize_ws(before_slice),
        anchor=_normalize_ws(actual_anchor) if actual_anchor else anchored_text,
        after=_normalize_ws(after_slice),
        truncated_before=offset > before,
        truncated_after=end_offset < n_text - after,
        line_no=line_no,
    )


def _deletion_context(doc: DocText, offset: int, deleted: str, line_no: int) -> SourceContext:
    """Context for a tracked deletion.

    The deleted text is no longer in the document, so it can't be located by
    offset — it *is* the anchor, sitting between the surrounding live text.
    """
    text = doc.text
    offset = max(0, min(offset, len(text)))
    return SourceContext(
        before=_normalize_ws(text[max(0, offset - CONTEXT_CHARS_BEFORE) : offset]),
        anchor=_normalize_ws(deleted),
        after=_normalize_ws(text[offset : offset + CONTEXT_CHARS_AFTER]),
        truncated_before=offset > CONTEXT_CHARS_BEFORE,
        truncated_after=offset + CONTEXT_CHARS_AFTER < len(text),
        line_no=line_no,
    )


def _thread_matches_reviewer(thread: Thread | None, reviewer_filter: list[str]) -> bool:
    """True if the thread has at least one message from any reviewer in the
    filter list. `reviewer_filter` is a list of case-insensitive substrings
    matched against the message author's name OR email."""
    if not reviewer_filter or thread is None:
        return True
    needles = [r.lower().strip() for r in reviewer_filter if r and r.strip()]
    if not needles:
        return True
    for msg in thread.messages:
        hay = " ".join(
            x for x in (msg.user_name, msg.user_email, msg.user_id) if x
        ).lower()
        if any(n in hay for n in needles):
            return True
    return False


def _change_matches_reviewer(change: TrackedChange, reviewer_filter: list[str]) -> bool:
    if not reviewer_filter:
        return True
    needles = [r.lower().strip() for r in reviewer_filter if r and r.strip()]
    if not needles:
        return True
    hay = " ".join(
        x for x in (change.user_name, change.user_email, change.user_id) if x
    ).lower()
    return any(n in hay for n in needles)


def _slug_reviewer(name: str) -> str:
    """Filesystem-safe slug for a reviewer name."""
    out = []
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_", ".", "@"):
            out.append("-")
    s = "".join(out).strip("-")
    while "--" in s:
        s = s.replace("--", "-")
    return s[:60] or "reviewer"


def _comment_to_jsonl_record(
    c: AnchoredComment,
    thread: Thread | None,
    user_map: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Self-contained JSONL record per comment (with embedded thread, since
    JSONL records are read independently)."""
    return {
        "short_id": c.short_id,
        "thread_id": c.thread_id,
        "pathname": c.pathname,
        "line": c.line_no,
        "col": c.col,
        "offset": c.offset,
        "nearest_heading": c.nearest_heading,
        "anchored_text": c.anchored_text,
        "stale": c.stale,
        "reply_count": max(0, len(thread.messages) - 1) if thread else 0,
        "context": _serialize_context(c.context),
        "thread": _serialize_thread(thread, user_map) if thread is not None else None,
    }


def _iter_doc_ranges(ranges_payload: Any):
    if isinstance(ranges_payload, list):
        docs = ranges_payload
    elif isinstance(ranges_payload, dict):
        docs = ranges_payload.get("docs") or ranges_payload.get("ranges") or []
    else:
        docs = []
    for entry in docs:
        if not isinstance(entry, dict):
            continue
        doc_id = entry.get("id") or entry.get("_id") or entry.get("doc_id")
        if not doc_id:
            continue
        ranges = entry.get("ranges") or {}
        yield (
            str(doc_id),
            ranges.get("comments") or [],
            ranges.get("changes") or [],
        )


def run_export(
    project_url: str,
    out_dir: Path,
    *,
    project_title: str | None = None,
    base_url: str = "https://www.overleaf.com",
    browser: str = "auto",
    cookie_value: str | None = None,
    cookie_name: str | None = None,
    verbose: bool = False,
    include_raw: bool = False,
    include_open: bool = True,
    include_resolved: bool = True,
    include_changes: bool = True,
    reviewer_filter: list[str] | None = None,
    render_mode: str = "compact",
    write_jsonl: bool = True,
    per_reviewer_reports: bool = False,
    response_letter: bool = False,
    annotated_tex: bool = False,
    annotated_pdf: bool = False,
    include_source: bool = False,
    annotate_style: str = "highlight",
    stable: bool = False,
    progress: ProgressCallback | None = None,
    should_cancel: CancelCheck | None = None,
) -> ExportResult:
    """Programmatic entry point used by both the CLI and the GUI."""
    progress = progress or _noop_progress
    out_dir = Path(out_dir).expanduser()
    # Checked before anything is fetched. Choosing a folder you cannot write to
    # is an ordinary mistake, and it used to surface as a raw PermissionError
    # with an Errno in it, which the window reports as an unexpected bug.
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        probe = out_dir / ".oce-write-test"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError as e:
        raise UserFacingError(
            f"Nothing can be written to that folder.\n\n{out_dir}\n\n"
            "Pick somewhere else, for example a new folder on your Desktop. "
            f"The system said: {e.strerror or e}"
        ) from e
    log_path = out_dir / "comments.log"

    # Drop the handler from any previous export in this process before adding
    # this one. The window can run several exports, and without this each run
    # left its handler attached: the file from the first run went on receiving
    # lines from every later run, and the open handles accumulated.
    for old in [h for h in logger.handlers if getattr(h, "_oce_export_log", False)]:
        logger.removeHandler(old)
        old.close()
    handler_file = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    handler_file._oce_export_log = True  # type: ignore[attr-defined]
    handler_file.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    handler_file.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.addHandler(handler_file)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    project_id = parse_project_id(project_url)
    progress(f"Project id: {project_id}")
    logger.info("Project id: %s", project_id)

    client = OverleafClient(base_url=base_url, cookie_name=cookie_name)
    client.should_cancel = should_cancel
    if cookie_value:
        progress("Authenticating with the pasted session cookie…")
    else:
        progress(f"Authenticating via {browser} browser cookie…")
    client.connect(browser=browser, cookie_value=cookie_value)

    _stop_if_asked(should_cancel)
    progress("Fetching threads…")
    threads_raw = client.get_threads(project_id)
    progress(f"Got {len(threads_raw)} thread(s).")
    logger.info("Got %d threads.", len(threads_raw))

    resolved_ids = set(client.get_resolved_thread_ids(project_id))
    for tid in resolved_ids:
        if tid in threads_raw and isinstance(threads_raw[tid], dict):
            threads_raw[tid]["resolved"] = True

    user_map = _build_user_map(threads_raw)
    threads = _parse_threads(threads_raw)

    _stop_if_asked(should_cancel)
    progress("Fetching project file tree…")
    metadata = client.get_project_metadata(project_id)
    doc_id_to_path: dict[str, str] = {}
    if metadata.get("files"):
        for entry in client.flatten_files(metadata["files"], debug_logger=logger.info):
            doc_id_to_path[entry["doc_id"]] = entry["pathname"]
    if not doc_id_to_path:
        progress(
            "File tree empty — comments will be grouped by section in each "
            "doc instead of by filename."
        )
    project_display_name = metadata.get("name") or project_title or project_id
    progress(f"Mapped {len(doc_id_to_path)} doc(s) to paths. Project: {project_display_name}")

    _stop_if_asked(should_cancel)
    progress("Fetching project ranges (anchors + tracked changes)…")
    ranges_payload = client.get_project_ranges(project_id)
    if ranges_payload is not None:
        logger.info(
            "ranges payload type=%s len=%s",
            type(ranges_payload).__name__,
            (len(ranges_payload) if hasattr(ranges_payload, "__len__") else "?"),
        )

    anchored: list[AnchoredComment] = []
    changes: list[TrackedChange] = []
    referenced_thread_ids: set[str] = set()
    doc_texts: dict[str, DocText] = {}

    if ranges_payload:
        docs_with_anchors = list(_iter_doc_ranges(ranges_payload))
        anchor_doc_count = sum(1 for _, c, ch in docs_with_anchors if c or ch)
        progress(f"Downloading text for {anchor_doc_count} doc(s) with anchors…")
        # Fetched only if the file tree came up short, and only once. See
        # filenames.py for why the zip is the route that works for everyone.
        zip_index: dict[str, list[str]] | None = None

        for doc_id, comments_list, changes_list in docs_with_anchors:
            _stop_if_asked(should_cancel)
            if not comments_list and not changes_list:
                continue
            pathname = doc_id_to_path.get(doc_id)
            try:
                text = client.download_doc_text(project_id, doc_id)
            except Exception as e:
                logger.warning("Could not download doc %s (%s): %s",
                               doc_id, pathname or doc_id, e)
                progress(f"  skipped {pathname or doc_id}: {e}")
                continue

            if pathname is None:
                if zip_index is None:
                    progress("Filenames were not in the file tree, asking for the "
                             "project zip instead…")
                    data = client.download_project_zip(project_id)
                    zip_index = index_zip(data) if data else {}
                    logger.info("Read %d text file(s) from the project zip.",
                                len(zip_index))
                pathname = name_for(zip_index, text)
                if pathname:
                    doc_id_to_path[doc_id] = pathname
                    logger.info("Named %s from the project zip: %s", doc_id, pathname)
            if pathname is None:
                pathname = f"<unknown-{doc_id}>"
            doc = _build_doc_text(doc_id, pathname, text)
            doc_texts[doc_id] = doc

            for c in comments_list:
                op = c.get("op") or {}
                thread_id = op.get("t") or c.get("t")
                if not thread_id:
                    continue
                offset = int(op.get("p", 0))
                anchored_text = op.get("c") or ""
                resolved_offset, line, col, stale = resolve_anchor(doc, offset, anchored_text)
                heading = nearest_heading(doc.headings, line)
                context = _extract_context(doc, resolved_offset, anchored_text, line)
                anchored.append(
                    AnchoredComment(
                        thread_id=str(thread_id),
                        short_id="",  # assigned below in stable sort order
                        doc_id=doc_id,
                        pathname=pathname,
                        offset=resolved_offset,
                        anchored_text=anchored_text,
                        line_no=line,
                        col=col,
                        nearest_heading=heading,
                        stale=stale,
                        context=context,
                    )
                )
                referenced_thread_ids.add(str(thread_id))

            for ch in changes_list:
                op = ch.get("op") or {}
                meta = ch.get("metadata") or {}
                if "i" in op:
                    kind, content = "insertion", op.get("i") or ""
                elif "d" in op:
                    kind, content = "deletion", op.get("d") or ""
                else:
                    continue
                offset = int(op.get("p", 0))
                ro, line, col, _ = resolve_anchor(
                    doc, offset, content if kind == "insertion" else ""
                )
                heading = nearest_heading(doc.headings, line)
                uid = str(meta.get("user_id") or "") or None
                user = user_map.get(uid or "", {}) if uid else {}
                if kind == "insertion":
                    context = _extract_context(doc, ro, content, line)
                else:
                    context = _deletion_context(doc, ro, content, line)
                changes.append(
                    TrackedChange(
                        id=str(ch.get("id") or ch.get("_id") or ""),
                        short_id="",  # assigned below
                        doc_id=doc_id,
                        pathname=pathname,
                        kind=kind,
                        content=content,
                        offset=offset,
                        line_no=line,
                        col=col,
                        nearest_heading=heading,
                        user_id=uid,
                        user_name=user.get("name"),
                        user_email=user.get("email"),
                        timestamp_ms=_to_ms(meta.get("ts")),
                        context=context,
                    )
                )
    else:
        progress(
            "Ranges payload unavailable — Markdown will list threads without "
            "file/line anchors."
        )

    orphan_threads = [
        thread for tid, thread in threads.items() if tid not in referenced_thread_ids
    ]

    # Stable IDs assigned BEFORE filtering so they're consistent across runs.
    anchored.sort(key=lambda c: (c.pathname, c.line_no, c.col, c.offset))
    for i, c in enumerate(anchored, 1):
        c.short_id = f"C{i:03d}"
    changes.sort(key=lambda ch: (ch.pathname, ch.line_no, ch.col, ch.offset))
    for i, ch in enumerate(changes, 1):
        ch.short_id = f"T{i:03d}"

    # ---- Apply filters ----
    reviewer_filter = reviewer_filter or []
    pre_filter_anchored = list(anchored)
    pre_filter_changes = list(changes)

    def keep_comment(c: AnchoredComment) -> bool:
        t = threads.get(c.thread_id)
        if t is not None:
            if t.resolved and not include_resolved:
                return False
            if not t.resolved and not include_open:
                return False
        if reviewer_filter and not _thread_matches_reviewer(t, reviewer_filter):
            return False
        return True

    anchored = [c for c in anchored if keep_comment(c)]
    if not include_changes:
        changes = []
    else:
        changes = [ch for ch in changes if _change_matches_reviewer(ch, reviewer_filter)]

    # Orphan threads: also filter by open/resolved + reviewer
    def keep_orphan(t: Thread) -> bool:
        if t.resolved and not include_resolved:
            return False
        if not t.resolved and not include_open:
            return False
        if reviewer_filter and not _thread_matches_reviewer(t, reviewer_filter):
            return False
        return True

    orphan_threads = [t for t in orphan_threads if keep_orphan(t)]

    filtered_msg_bits = []
    if not include_open:
        filtered_msg_bits.append("open hidden")
    if not include_resolved:
        filtered_msg_bits.append("resolved hidden")
    if not include_changes:
        filtered_msg_bits.append("tracked changes hidden")
    if reviewer_filter:
        filtered_msg_bits.append(f"reviewer filter: {', '.join(reviewer_filter)}")
    if filtered_msg_bits:
        progress(
            f"Filter applied ({'; '.join(filtered_msg_bits)}): "
            f"{len(pre_filter_anchored)}→{len(anchored)} comments, "
            f"{len(pre_filter_changes)}→{len(changes)} tracked changes"
        )

    title = project_title or metadata.get("name") or project_id
    open_count = sum(
        1 for c in anchored if not (threads.get(c.thread_id) and threads[c.thread_id].resolved)
    )
    resolved_count = sum(
        1 for c in anchored if threads.get(c.thread_id) and threads[c.thread_id].resolved
    )
    # If filters hide most threads, also surface the totals over the surviving set
    thread_count_after = len({c.thread_id for c in anchored} | {t.id for t in orphan_threads})
    stale_count = sum(1 for c in anchored if c.stale)

    mode_lit = "detailed" if (render_mode or "").lower() == "detailed" else "compact"
    markdown = render_markdown(
        project_title=title,
        project_id=project_id,
        threads=threads,
        anchored=anchored,
        orphan_threads=orphan_threads,
        changes=changes,
        mode=mode_lit,
        stable=stable,
    )

    # A dated filename makes every run a new file, so git shows additions
    # instead of a diff. In stable mode there is one file that gets updated.
    # The last chance to stop before anything is written. After this the files
    # start appearing, and a half-written export folder is worse than none.
    _stop_if_asked(should_cancel)
    md_path = out_dir / ("comments.md" if stable else f"comments-{date.today().isoformat()}.md")
    md_path.write_text(markdown, encoding="utf-8")
    progress(f"Wrote {md_path.name}")

    json_payload = _build_structured_json(
        project_id=project_id,
        project_title=title,
        threads=threads,
        anchored=anchored,
        changes=changes,
        orphan_threads=orphan_threads,
        doc_id_to_path=doc_id_to_path,
        open_count=open_count,
        resolved_count=resolved_count,
        stale_count=stale_count,
        threads_raw=threads_raw,
        ranges_payload=ranges_payload,
        include_raw=include_raw,
        user_map=user_map,
        stable=stable,
    )
    json_payload["filters_applied"] = {
        "include_open": include_open,
        "include_resolved": include_resolved,
        "include_changes": include_changes,
        "reviewer_filter": reviewer_filter,
        "render_mode": mode_lit,
    }
    json_path = out_dir / "comments.json"
    json_path.write_text(json.dumps(json_payload, indent=2, default=str), encoding="utf-8")
    progress(f"Wrote {json_path.name}")

    # JSONL companion (one comment per line, self-contained)
    if write_jsonl:
        jsonl_path = out_dir / "comments.jsonl"
        with jsonl_path.open("w", encoding="utf-8") as f:
            for c in anchored:
                rec = _comment_to_jsonl_record(c, threads.get(c.thread_id), user_map)
                f.write(json.dumps(rec, default=str))
                f.write("\n")
        progress(f"Wrote {jsonl_path.name} ({len(anchored)} record(s))")

    # Per-reviewer sub-reports
    if per_reviewer_reports:
        by_reviewer_dir = out_dir / "by-reviewer"
        by_reviewer_dir.mkdir(exist_ok=True)
        reviewers: dict[str, str] = {}  # display name -> slug
        for t in threads.values():
            for m in t.messages:
                name = m.user_name or m.user_email or m.user_id
                if not name:
                    continue
                reviewers.setdefault(name, _slug_reviewer(name))
        for change in changes:
            name = change.user_name or change.user_email or change.user_id
            if name:
                reviewers.setdefault(name, _slug_reviewer(name))
        written = 0
        for reviewer_name, slug in reviewers.items():
            sub_anchored = [
                c for c in anchored
                if _thread_matches_reviewer(threads.get(c.thread_id), [reviewer_name])
            ]
            sub_changes = [
                ch for ch in changes
                if _change_matches_reviewer(ch, [reviewer_name])
            ]
            sub_orphans = [
                t for t in orphan_threads
                if _thread_matches_reviewer(t, [reviewer_name])
            ]
            if not sub_anchored and not sub_changes and not sub_orphans:
                continue
            sub_md = render_markdown(
                project_title=f"{title} — {reviewer_name}",
                project_id=project_id,
                threads=threads,
                anchored=sub_anchored,
                orphan_threads=sub_orphans,
                changes=sub_changes,
                mode=mode_lit,
                stable=stable,
            )
            (by_reviewer_dir / f"{slug}.md").write_text(sub_md, encoding="utf-8")
            written += 1
        progress(f"Wrote {written} per-reviewer report(s) into by-reviewer/")

    letter_path: Path | None = None
    if response_letter:
        letter_path = out_dir / "response-letter.md"
        letter_path.write_text(
            render_response_letter(title, project_id, threads, anchored, stable=stable),
            encoding="utf-8",
        )
        progress(f"Wrote {letter_path.name}")

    annotated_dir: Path | None = None
    if annotated_tex:
        annotated_dir = out_dir / "annotated"
        by_doc: dict[str, list[AnchoredComment]] = {}
        for c in anchored:
            by_doc.setdefault(c.doc_id, []).append(c)
        written = 0
        for doc_id, doc_comments in sorted(by_doc.items()):
            _stop_if_asked(should_cancel)
            doc = doc_texts.get(doc_id)
            if doc is None:
                continue
            annotated, n = annotate_document(
                doc.text, doc_comments, threads,
                style=annotate_style if annotate_style in ANNOTATE_STYLES else "highlight",
            )
            # Mirror the project layout so \input paths still resolve.
            rel = safe_relative(doc.pathname, doc_id)
            target = annotated_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(annotated, encoding="utf-8")
            written += 1
            progress(f"  annotated {rel} with {n} comment(s)")
        progress(
            f"Wrote {written} annotated source file(s) into annotated/ "
            f"— compile one to get a PDF carrying the comments"
        )

    annotated_pdf_path: Path | None = None
    if annotated_pdf:
        _stop_if_asked(should_cancel)
        progress("Fetching the PDF Overleaf built…")
        try:
            pdf = client.download_compiled_pdf(project_id, metadata.get("rootDocId"))
        except UserFacingError:
            raise
        except Exception as e:
            logger.warning("Could not get the compiled PDF: %s", e)
            pdf = None
        if pdf is None:
            progress(
                "Overleaf had no PDF to give. Open the project and press "
                "Recompile once, then run this again."
            )
        else:
            # The comments belong to whichever document holds most of them;
            # the PDF is one file however many sources it was built from.
            from .pdfannotate import PdfAnnotationUnavailable, annotate_pdf

            sources = {doc_id: d.text for doc_id, d in doc_texts.items()}
            if not sources:
                progress("No commented source to match against, skipping the PDF.")
            else:
                try:
                    out_bytes, placed = annotate_pdf(pdf, sources, anchored, threads)
                except PdfAnnotationUnavailable as e:
                    raise UserFacingError(str(e)) from e
                annotated_pdf_path = out_dir / "commented.pdf"
                annotated_pdf_path.write_bytes(out_bytes)
                marked = sum(1 for p in placed if p.highlighted)
                progress(
                    f"Wrote {annotated_pdf_path.name} — {marked} of {len(placed)} "
                    f"comment(s) marked on the page, all {len(placed)} listed at the end"
                )
                if marked < len(placed):
                    logger.info(
                        "Not marked: %s",
                        ", ".join(f"{p.comment.short_id} ({p.reason})"
                                  for p in placed if not p.highlighted),
                    )

    source_dir: Path | None = None
    if include_source and doc_texts:
        # Written byte for byte as it was downloaded, because `offset` and
        # `line` in comments.json index into exactly this text. An assistant
        # asked to rewrite a paragraph can then read the paragraph, rather than
        # working from the short window around the anchor.
        source_dir = out_dir / "source"
        for doc_id, doc in sorted(doc_texts.items()):
            target = source_dir / safe_relative(doc.pathname, doc_id)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(doc.text, encoding="utf-8")
        progress(
            f"Wrote {len(doc_texts)} commented file(s) into source/ — the "
            f"offsets in comments.json point into these"
        )

    agents_path = out_dir / "agents.md"
    agents_path.write_text(
        _build_agents_md(title, project_id, json_path.name, md_path.name,
                         has_source=source_dir is not None),
        encoding="utf-8")
    progress(f"Wrote {agents_path.name}")

    if stale_count:
        progress(f"{stale_count} comment anchor(s) were stale (text moved or removed).")

    return ExportResult(
        project_id=project_id,
        markdown_path=md_path,
        json_path=json_path,
        log_path=log_path,
        thread_count=thread_count_after,
        open_count=open_count,
        resolved_count=resolved_count,
        tracked_change_count=len(changes),
        stale_anchor_count=stale_count,
        jsonl_path=(out_dir / "comments.jsonl") if write_jsonl else None,
        by_reviewer_dir=(out_dir / "by-reviewer") if per_reviewer_reports else None,
        agents_path=agents_path,
        response_letter_path=letter_path,
        annotated_dir=annotated_dir,
        annotated_pdf_path=annotated_pdf_path,
        source_dir=source_dir,
    )


def _iso(ms: int | None) -> str | None:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _serialize_context(ctx: SourceContext | None) -> dict[str, Any] | None:
    if ctx is None:
        return None
    return {
        "line": ctx.line_no,
        "before": ctx.before,
        "anchor": ctx.anchor,
        "after": ctx.after,
        "truncated_before": ctx.truncated_before,
        "truncated_after": ctx.truncated_after,
    }


def _serialize_thread(
    thread: Thread, user_map: dict[str, dict[str, str]] | None = None
) -> dict[str, Any]:
    """Serialize a thread, tagging the first message as the comment itself and
    the rest as replies (Overleaf threads are flat, ordered by time)."""
    ordered = sorted(thread.messages, key=lambda x: x.timestamp_ms)
    resolver = user_map or {}
    resolved_by = resolver.get(thread.resolved_by_user_id or "", {})
    return {
        "id": thread.id,
        "resolved": thread.resolved,
        "resolved_at": _iso(thread.resolved_at_ms),
        "resolved_by": {
            "id": thread.resolved_by_user_id,
            "name": resolved_by.get("name"),
            "email": resolved_by.get("email"),
        }
        if thread.resolved_by_user_id
        else None,
        "reply_count": max(0, len(ordered) - 1),
        "messages": [
            {
                "id": m.id,
                "role": "comment" if i == 0 else "reply",
                "reply_index": None if i == 0 else i - 1,
                "user": {
                    "id": m.user_id,
                    "name": m.user_name,
                    "email": m.user_email,
                },
                "content": m.content,
                "timestamp": _iso(m.timestamp_ms),
                "edited_at": _iso(m.edited_at_ms),
            }
            for i, m in enumerate(ordered)
        ],
    }


def _build_structured_json(
    *,
    project_id: str,
    project_title: str,
    threads: dict[str, Thread],
    anchored: list[AnchoredComment],
    changes: list[TrackedChange],
    orphan_threads: list[Thread],
    doc_id_to_path: dict[str, str],
    open_count: int,
    resolved_count: int,
    stale_count: int,
    threads_raw: dict[str, Any],
    ranges_payload: Any,
    include_raw: bool = False,
    user_map: dict[str, dict[str, str]] | None = None,
    stable: bool = False,
) -> dict[str, Any]:
    """Produce a clean, AI-ingestion-friendly JSON document.

    Top-level shape:
      schema_version, project, pulled_at, summary, files (grouped),
      comments (flat with short_id), tracked_changes, orphan_threads,
      raw (the unprocessed payloads for advanced users).
    """
    by_file_comments: dict[str, list[AnchoredComment]] = {}
    for c in anchored:
        by_file_comments.setdefault(c.pathname, []).append(c)
    by_file_changes: dict[str, list[TrackedChange]] = {}
    for ch in changes:
        by_file_changes.setdefault(ch.pathname, []).append(ch)

    files: list[dict[str, Any]] = []
    for path in sorted(set(list(by_file_comments) + list(by_file_changes))):
        files.append(
            {
                "pathname": path,
                "doc_id": _doc_id_for_path(path, doc_id_to_path),
                "comment_count": len(by_file_comments.get(path, [])),
                "change_count": len(by_file_changes.get(path, [])),
                "comment_short_ids": [c.short_id for c in by_file_comments.get(path, [])],
                "change_short_ids": [ch.short_id for ch in by_file_changes.get(path, [])],
            }
        )

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": __version__,
        "project": {
            "id": project_id,
            "title": project_title,
        },
        **({} if stable else {"pulled_at": datetime.now(timezone.utc).isoformat()}),
        "summary": {
            "thread_count": len(threads),
            "open_count": open_count,
            "resolved_count": resolved_count,
            "tracked_change_count": len(changes),
            "stale_anchor_count": stale_count,
            "file_count": len(files),
            "reviewer_count": len(
                {
                    m.user_id
                    for t in threads.values()
                    for m in t.messages
                    if m.user_id
                }
            ),
        },
        # Threads are stored ONCE at the top level keyed by thread_id;
        # comments reference them via `thread_id`. This avoids duplicating
        # potentially long discussions inside every comment.
        "threads": {
            tid: _serialize_thread(threads[tid], user_map)
            for tid in sorted(threads)
        },
        "files": files,
        "comments": [
            {
                "short_id": c.short_id,
                "thread_id": c.thread_id,
                "doc_id": c.doc_id,
                "pathname": c.pathname,
                "line": c.line_no,
                "col": c.col,
                "offset": c.offset,
                "nearest_heading": c.nearest_heading,
                "anchored_text": c.anchored_text,
                "stale": c.stale,
                "reply_count": max(
                    0, len(threads[c.thread_id].messages) - 1
                ) if c.thread_id in threads else 0,
                "context": _serialize_context(c.context),
            }
            for c in anchored
        ],
        "tracked_changes": [
            {
                "short_id": ch.short_id,
                "id": ch.id,
                "doc_id": ch.doc_id,
                "pathname": ch.pathname,
                "kind": ch.kind,
                "content": ch.content,
                "line": ch.line_no,
                "col": ch.col,
                "offset": ch.offset,
                "nearest_heading": ch.nearest_heading,
                "user": {
                    "id": ch.user_id,
                    "name": ch.user_name,
                    "email": ch.user_email,
                },
                "timestamp": _iso(ch.timestamp_ms),
                "context": _serialize_context(ch.context),
            }
            for ch in changes
        ],
        "orphan_thread_ids": sorted(t.id for t in orphan_threads),
    }
    if include_raw:
        payload["raw"] = {
            "threads": threads_raw,
            "ranges": ranges_payload,
            "doc_id_to_path": doc_id_to_path,
        }
    return payload


def _doc_id_for_path(path: str, doc_id_to_path: dict[str, str]) -> str | None:
    for did, p in doc_id_to_path.items():
        if p == path:
            return did
    return None


def _build_agents_md(project_title: str, project_id: str, json_name: str, md_name: str,
                     has_source: bool = False) -> str:
    """A short instruction file for AI agents who'll ingest this batch."""
    source_note = (
        "## The source itself\n\n"
        "The full text of every commented file is in `source/`, exactly as it\n"
        "is in the project. The `offset` and `line` on each comment index into\n"
        "those files, so you can read the whole paragraph a comment is about\n"
        "rather than the short window in `context`. Edit proposals should quote\n"
        "from there.\n\n"
    ) if has_source else ""
    no_source_note = (
        "" if has_source else
        "- The full `.tex` source of the paper. You only see a short window\n"
        "  around each anchor. If you need more, ask the user to re-run the\n"
        "  export with --include-source, which writes the commented files into\n"
        "  `source/`.\n"
    )
    return f"""# Agent brief — Overleaf comments for {project_title}

You are reading an Overleaf comment export produced by
`overleaf_comments_export`. Two files in this folder are relevant:

- `{md_name}` — human-readable Markdown, with YAML front-matter and
  comments grouped by file → section → line. Every comment has a stable
  short ID like `C001` (assigned in file → line order). The Markdown is the
  canonical user-facing view.
- `{json_name}` — the same data in structured form. Use this when you need
  to enumerate, filter, or programmatically address comments.

## JSON schema (key parts)

- `schema_version` (string)
- `project` — `{{ id, title }}`
- `summary` — counts (threads, open/resolved, tracked changes, stale, files,
  reviewers)
- `threads` — `{{ "<thread_id>": {{ id, resolved, resolved_at,
  resolved_by_user_id, messages: [...] }} }}` — stored once at top level,
  not duplicated inside each comment.
- `files` — list of `{{ pathname, doc_id, comment_count, change_count,
  comment_short_ids, change_short_ids }}`
- `comments` — list of `{{ short_id, thread_id, doc_id, pathname, line, col,
  offset, nearest_heading, anchored_text, stale, context }}`. To get the
  discussion, look up `threads[thread_id]`.
- `tracked_changes` — list of `{{ short_id, id, doc_id, pathname, kind
  (insertion|deletion), content, line, col, offset, nearest_heading, user,
  timestamp, context }}`
- `orphan_thread_ids` — IDs of threads that don't anchor to live source.

`context` is a compact char-window snippet: `before`, `anchor`, `after`,
with `truncated_before`/`truncated_after` flags. `…` should be used in
rendered output where truncation is true.

## How to address comments

- Refer to comments by `short_id` (e.g., "C014"), not by `thread_id`.
- Each thread's FIRST message (`role: "comment"`) is the reviewer's actual
  ask. Later messages (`role: "reply"`, shown indented with `↳` in the
  Markdown) are follow-up discussion, often between co-authors. Answer the
  ask, taking the discussion into account; do not re-litigate sub-points the
  replies already settled.
- For each open comment, propose an edit to the .tex source. If the comment
  is a question, answer it; if it's a request, attempt the change.
- Stale comments (`stale: true`) may not point to the current location in the
  doc. Use `anchored_text` and `nearest_heading` to find the right spot.
- Tracked changes (`T001`-prefixed) are not comment threads; they are
  insertions/deletions someone made with "Track Changes" enabled. Treat them
  as suggested edits to accept, reject, or modify.

{source_note}## What you do NOT have

{no_source_note}- The ability to push edits back to Overleaf. Output any proposed edits as
  diffs or rewrites; the user will apply them.

Project ID for reference: `{project_id}`.
"""
