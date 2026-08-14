from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Iterable, Literal

from . import __version__
from .model import AnchoredComment, SourceContext, Thread, TrackedChange

SCHEMA_VERSION = "1.3"
RenderMode = Literal["compact", "detailed"]

# How aggressively to clip the captured context window when rendering.
COMPACT_CONTEXT_CHARS = 70
DETAILED_CONTEXT_CHARS = 160


def _fmt_ts(ms: int | None) -> str:
    if not ms:
        return "?"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _humanize_user(name: str | None, email: str | None, user_id: str | None) -> str:
    """Best-effort display name. If `name` is set, use it. Else if the email
    local part looks like firstname.lastname, title-case it. Else fall back to
    the email local part, then a short id."""
    if name:
        return name
    if email:
        local = email.split("@", 1)[0]
        # firstname.lastname → "Firstname Lastname"
        parts = [p for p in local.replace("_", ".").replace("-", ".").split(".") if p]
        if len(parts) >= 2 and all(p.isalpha() for p in parts):
            return " ".join(p.capitalize() for p in parts)
        return local
    return (user_id or "unknown")[:8]


def _clip_left(s: str, n: int) -> tuple[str, bool]:
    """Return rightmost n chars; True if clipped on the left."""
    if len(s) <= n:
        return s, False
    return s[-n:].lstrip(), True


def _clip_right(s: str, n: int) -> tuple[str, bool]:
    """Return leftmost n chars; True if clipped on the right."""
    if len(s) <= n:
        return s, False
    return s[:n].rstrip(), True


def _inline_context(ctx: SourceContext | None, anchored_text_raw: str) -> str:
    """Single-line blockquote: `…before  ▸anchor◂  after…`"""
    if ctx is None:
        text = (anchored_text_raw or "").strip()
        return f"> **▸{text}◂**" if text else "> _(anchor text unavailable)_"
    before, clipped_b = _clip_left(ctx.before, COMPACT_CONTEXT_CHARS)
    after, clipped_a = _clip_right(ctx.after, COMPACT_CONTEXT_CHARS)
    anchor = ctx.anchor or anchored_text_raw or ""
    lead = "…" if (ctx.truncated_before or clipped_b) else ""
    tail = "…" if (ctx.truncated_after or clipped_a) else ""
    parts = []
    if before:
        parts.append(f"{lead}{before} ")
    elif lead:
        parts.append(lead)
    parts.append(f"**▸{anchor}◂**")
    if after:
        parts.append(f" {after}{tail}")
    elif tail:
        parts.append(tail)
    return "> " + "".join(parts)


def _detailed_context(ctx: SourceContext | None, anchored_text_raw: str) -> list[str]:
    """Multi-line code fence with the anchor on its own line."""
    if ctx is None:
        text = (anchored_text_raw or "").strip()
        if not text:
            return ["> _(anchor text unavailable)_"]
        return ["```tex", f"▸ {text}", "```"]
    before, clipped_b = _clip_left(ctx.before, DETAILED_CONTEXT_CHARS)
    after, clipped_a = _clip_right(ctx.after, DETAILED_CONTEXT_CHARS)
    anchor = ctx.anchor or anchored_text_raw or ""
    lead = "…" if (ctx.truncated_before or clipped_b) else ""
    tail = "…" if (ctx.truncated_after or clipped_a) else ""
    out = ["```tex"]
    if before:
        out.append(f"{lead}{before}")
    out.append(f"▸ {anchor}")
    if after:
        out.append(f"{after}{tail}")
    out.append("```")
    return out


def _group_label(path: str) -> str:
    if path.startswith("<unknown-") and path.endswith(">"):
        return "Unmapped doc (filename not available)"
    return path


def _slug(s: str) -> str:
    return "f-" + "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-")[:80]


def render_markdown(
    project_title: str,
    project_id: str,
    threads: dict[str, Thread],
    anchored: list[AnchoredComment],
    orphan_threads: list[Thread],
    changes: list[TrackedChange],
    *,
    mode: RenderMode = "compact",
    stable: bool = False,
) -> str:
    """Render the export as Markdown.

    `stable` omits everything that changes from one run to the next, so the
    file can live in a git repository and only move when the comments do.
    """
    pulled_at_iso = (
        None if stable else datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    open_count = sum(1 for t in threads.values() if not t.resolved)
    resolved_count = sum(1 for t in threads.values() if t.resolved)
    stale_count = sum(1 for c in anchored if c.stale)
    file_count = len({c.pathname for c in anchored} | {ch.pathname for ch in changes})

    reviewer_counter: Counter[str] = Counter()
    for t in threads.values():
        for m in t.messages:
            reviewer_counter[_humanize_user(m.user_name, m.user_email, m.user_id)] += 1

    out: list[str] = []

    # ---- YAML front-matter ----
    out.append("---")
    out.append(f"schema_version: {SCHEMA_VERSION}")
    out.append(f"tool_version: {__version__}")
    out.append(f"project_id: {project_id}")
    out.append(f'project_title: "{project_title}"')
    if pulled_at_iso is not None:
        out.append(f"pulled_at: {pulled_at_iso}")
    out.append(f"thread_count: {len(threads)}")
    out.append(f"open_count: {open_count}")
    out.append(f"resolved_count: {resolved_count}")
    out.append(f"tracked_change_count: {len(changes)}")
    out.append(f"stale_anchor_count: {stale_count}")
    out.append(f"file_count: {file_count}")
    out.append(f"reviewer_count: {len(reviewer_counter)}")
    out.append("companion_json: comments.json")
    out.append("companion_agents: agents.md")
    out.append("---")
    out.append("")

    # ---- Human-friendly header ----
    out.append(f"# Overleaf comments — {project_title}")
    out.append("")
    out.append(
        "Stable IDs like `C001` are assigned in file → line order. Cite them when "
        "asking an AI to address specific comments. The full structured data is in "
        "`comments.json` next to this file."
    )
    out.append("")

    # ---- Summary ----
    out.append("## Summary")
    out.append("")
    out.append(f"- **Threads:** {len(threads)} ({open_count} open, {resolved_count} resolved)")
    out.append(f"- **Tracked changes:** {len(changes)}")
    if stale_count:
        out.append(
            f"- **Stale anchors:** {stale_count} "
            f"(quoted text moved or no longer matches the live doc — best-effort relocation applied)"
        )
    if reviewer_counter:
        top = sorted(reviewer_counter.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        out.append(
            "- **Most active reviewers:** "
            + ", ".join(f"{name} ({n})" for name, n in top)
        )
    if anchored:
        addressed = sum(1 for c in anchored
                        if (t := threads.get(c.thread_id)) is not None and t.resolved)
        out.append(
            f"- **Addressed:** {addressed} of {len(anchored)} "
            f"([the list is at the end](#still-to-address))"
        )
    out.append("")

    by_file_comments: dict[str, list[AnchoredComment]] = defaultdict(list)
    for c in anchored:
        by_file_comments[c.pathname].append(c)
    by_file_changes: dict[str, list[TrackedChange]] = defaultdict(list)
    for ch in changes:
        by_file_changes[ch.pathname].append(ch)
    all_paths = sorted(set(by_file_comments) | set(by_file_changes))

    # ---- Table of contents (skip if only one file) ----
    if len(all_paths) > 1:
        out.append("## Table of contents")
        out.append("")
        for path in all_paths:
            n_c = len(by_file_comments.get(path, []))
            n_t = len(by_file_changes.get(path, []))
            parts = []
            if n_c:
                parts.append(f"{n_c} comment{'' if n_c == 1 else 's'}")
            if n_t:
                parts.append(f"{n_t} tracked change{'' if n_t == 1 else 's'}")
            out.append(
                f"- [{_group_label(path)}](#{_slug(path)}) — {', '.join(parts)}"
            )
        out.append("")

    # ---- Per-file sections ----
    single_file = len(all_paths) == 1
    for path in all_paths:
        comments_in_file = sorted(by_file_comments.get(path, []), key=lambda c: (c.line_no, c.col, c.offset))
        changes_in_file = sorted(by_file_changes.get(path, []), key=lambda c: (c.line_no, c.col, c.offset))

        if not single_file:
            out.append(f"## {_group_label(path)}")
            out.append("")
            out.append(f'<a id="{_slug(path)}"></a>')
            out.append("")

        # Group comments by (section, line) so we emit context once.
        groups: dict[tuple[str, int], list[AnchoredComment]] = defaultdict(list)
        section_for_line: dict[int, str] = {}
        for c in comments_in_file:
            heading = c.nearest_heading or "_(no enclosing section)_"
            groups[(heading, c.line_no)].append(c)
            section_for_line[c.line_no] = heading

        last_section: str | None = None
        for (heading, line_no), group in sorted(groups.items(), key=lambda kv: (kv[1][0].line_no if False else 0, kv[0][1])):
            # Stable order: by line within section, sections by their first-line position
            pass
        # Re-do ordering: sort by (first_line_in_section, line_no)
        section_first_line = {}
        for (heading, line_no), _ in groups.items():
            section_first_line[heading] = min(line_no, section_first_line.get(heading, line_no))

        ordered_keys = sorted(
            groups.keys(),
            key=lambda k: (section_first_line[k[0]], k[1]),
        )

        for heading, line_no in ordered_keys:
            group = groups[(heading, line_no)]
            if heading != last_section:
                out.append(f"### § {heading}")
                out.append("")
                last_section = heading

            # Pick the most informative context from any comment in the group
            # (they all anchor to the same line so the surrounding chars are
            # similar; we just need one rendition).
            sample = group[0]
            out.append(f"**Line {line_no}** — {len(group)} comment{'' if len(group) == 1 else 's'}")
            out.append("")
            if mode == "detailed":
                out.extend(_detailed_context(sample.context, sample.anchored_text))
            else:
                out.append(_inline_context(sample.context, sample.anchored_text))
            out.append("")
            for c in group:
                thread = threads.get(c.thread_id)
                _emit_comment_compact(out, c, thread)

        if changes_in_file:
            out.append("### § Tracked changes")
            out.append("")
            for ch in changes_in_file:
                _emit_change(out, ch, mode=mode)

    if orphan_threads:
        out.append("## Threads without resolvable anchors")
        out.append("")
        out.append(
            "_These threads exist but we couldn't locate them in the live source._"
        )
        out.append("")
        for thread in orphan_threads:
            _emit_orphan_thread(out, thread)

    out.extend(render_checklist(threads, anchored))
    return "\n".join(out).rstrip() + "\n"


def render_response_letter(
    project_title: str,
    project_id: str,
    threads: dict[str, Thread],
    anchored: list[AnchoredComment],
    *,
    stable: bool = False,
) -> str:
    """A point-by-point reply document, pre-filled with every open comment.

    Grouped by the person who raised each point, because that is how journals
    ask for rebuttals. Each entry carries its `C###` id so it can be traced
    back to the full export.
    """
    out: list[str] = []
    pulled = None if stable else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Only points that still need answering, keyed by whoever raised them.
    by_reviewer: dict[str, list[AnchoredComment]] = defaultdict(list)
    for c in anchored:
        thread = threads.get(c.thread_id)
        if thread is None or thread.resolved or not thread.messages:
            continue
        first = min(thread.messages, key=lambda m: m.timestamp_ms)
        who = _humanize_user(first.user_name, first.user_email, first.user_id)
        by_reviewer[who].append(c)

    total = sum(len(v) for v in by_reviewer.values())

    out.append(f"# Response to reviewers — {project_title}")
    out.append("")
    out.append(
        f"_{total} point(s) to address._"
        if pulled is None
        else f"_Draft generated {pulled}. {total} point(s) to address._"
    )
    out.append("")
    out.append(
        "Fill in the **Response** and **Change made** lines under each point. "
        "The `C###` ids match `comments.json`, so you can ask an AI assistant "
        "to draft any of them by id."
    )
    out.append("")
    out.append("---")
    out.append("")

    if not total:
        out.append("No open comments. Nothing to respond to.")
        out.append("")
        return "\n".join(out).rstrip() + "\n"

    out.append("## Summary of changes")
    out.append("")
    out.append("_A short paragraph on the main revisions goes here._")
    out.append("")

    for reviewer in sorted(by_reviewer):
        items = by_reviewer[reviewer]
        out.append(f"## {reviewer} — {len(items)} point(s)")
        out.append("")
        for c in items:
            thread = threads[c.thread_id]
            ordered = sorted(thread.messages, key=lambda m: m.timestamp_ms)
            where = c.nearest_heading or "no enclosing section"
            # Don't leak "<unknown-6a21dec…>" into a document someone sends to
            # an editor; the line number alone is enough there.
            if c.pathname.startswith("<unknown-"):
                locus = f"line {c.line_no}"
            else:
                locus = f"`{c.pathname}` line {c.line_no}"
            out.append(f"### {c.short_id} — § {where} ({locus})")
            out.append("")
            quote = (c.anchored_text or "").strip().replace("\n", " ")
            if quote:
                out.append(f"**Referring to:** “{quote}”")
                out.append("")
            out.append("**Comment:**")
            out.append("")
            for line in (ordered[0].content or "").strip().splitlines() or [""]:
                out.append(f"> {line}")
            out.append("")
            if len(ordered) > 1:
                out.append("**Discussion so far:**")
                out.append("")
                for msg in ordered[1:]:
                    who = _humanize_user(msg.user_name, msg.user_email, msg.user_id)
                    body = (msg.content or "").strip().replace("\n", " ")
                    out.append(f"> ↳ {who}: {body}")
                out.append("")
            out.append("**Response:**")
            out.append("")
            out.append("_TODO_")
            out.append("")
            out.append("**Change made:**")
            out.append("")
            out.append("_TODO — what changed, and where._")
            out.append("")
            out.append("---")
            out.append("")

    return "\n".join(out).rstrip() + "\n"


def _status_badge(thread: Thread | None, stale: bool) -> str:
    bits = []
    if thread and thread.resolved:
        bits.append("resolved")
    else:
        bits.append("open")
    replies = max(0, len(thread.messages) - 1) if thread else 0
    if replies:
        bits.append(f"{replies} repl{'y' if replies == 1 else 'ies'}")
    if stale:
        bits.append("⚠ stale")
    return " · ".join(bits)


def _emit_comment_compact(out: list[str], c: AnchoredComment, thread: Thread | None) -> None:
    """One comment in compact form: header + quoted phrase + replies. No
    standalone source context (that's emitted once per (file, line) group)."""
    status = _status_badge(thread, c.stale)
    quote = (c.anchored_text or "").strip().replace("\n", " ")
    if quote:
        if len(quote) > 80:
            quote = quote[:77].rstrip() + "…"
        head = f"**{c.short_id}** _{status}_ — “{quote}”"
    else:
        head = f"**{c.short_id}** _{status}_ — _(empty anchor)_"
    if c.float_ref is not None:
        head += f" — in {c.float_ref.describe()}"
    out.append(head)
    if thread is None or not thread.messages:
        out.append("- _(no messages)_")
    else:
        # Overleaf threads are flat: the first message (oldest) is the comment
        # itself, everything after it is a reply. Replies are indented under it
        # with "↳" so the original ask is unmistakable.
        ordered = sorted(thread.messages, key=lambda m: m.timestamp_ms)
        for i, msg in enumerate(ordered):
            who = _humanize_user(msg.user_name, msg.user_email, msg.user_id)
            when = _fmt_ts(msg.timestamp_ms)
            edited = " _(edited)_" if msg.edited_at_ms else ""
            body = (msg.content or "").strip()
            bullet, indent = ("- ", "  ") if i == 0 else ("  - ↳ ", "    ")
            if "\n" in body:
                out.append(f"{bullet}**{who}** · {when}{edited}:")
                for line in body.splitlines():
                    out.append(f"{indent}> {line}")
            else:
                out.append(f"{bullet}**{who}** · {when}{edited}: {body}")
    out.append("")


def _emit_change(out: list[str], ch: TrackedChange, *, mode: RenderMode = "compact") -> None:
    sign = "+" if ch.kind == "insertion" else "-"
    who = _humanize_user(ch.user_name, ch.user_email, ch.user_id)
    when = _fmt_ts(ch.timestamp_ms)
    content = (ch.content or "").strip()
    out.append(
        f"**{ch.short_id}** _{ch.kind}_ — line {ch.line_no} — {who} · {when}"
    )

    ctx = ch.context
    if mode == "detailed" and ctx is not None:
        before, clipped_b = _clip_left(ctx.before, DETAILED_CONTEXT_CHARS)
        after, clipped_a = _clip_right(ctx.after, DETAILED_CONTEXT_CHARS)
        lead = "…" if (ctx.truncated_before or clipped_b) else ""
        tail = "…" if (ctx.truncated_after or clipped_a) else ""
        out.append("```diff")
        if before:
            out.append(f"  {lead}{before}")
        for ln in content.splitlines() or [""]:
            out.append(f"{sign} {ln}")
        if after:
            out.append(f"  {after}{tail}")
        out.append("```")
    else:
        # Compact: one-line diff with truncation
        flat = content.replace("\n", "⏎ ")
        if len(flat) > 120:
            flat = flat[:117].rstrip() + "…"
        out.append(f"- `{sign} {flat}`")
        if ctx is not None:
            before, clipped_b = _clip_left(ctx.before, COMPACT_CONTEXT_CHARS)
            after, clipped_a = _clip_right(ctx.after, COMPACT_CONTEXT_CHARS)
            lead = "…" if (ctx.truncated_before or clipped_b) else ""
            tail = "…" if (ctx.truncated_after or clipped_a) else ""
            if before or after:
                # Show the changed text in place: struck through for a
                # deletion, bracketed for an insertion.
                snippet = (ctx.anchor or content).replace("\n", " ").strip()
                if len(snippet) > COMPACT_CONTEXT_CHARS:
                    snippet = snippet[: COMPACT_CONTEXT_CHARS - 1].rstrip() + "…"
                marked = (
                    f"~~{snippet}~~" if ch.kind == "deletion" else f"**▸{snippet}◂**"
                )
                out.append(f"  > {lead}{before} {marked} {after}{tail}")
    out.append("")


def _emit_orphan_thread(out: list[str], thread: Thread) -> None:
    status = "resolved" if thread.resolved else "open"
    out.append(f"- **Thread `{thread.id[:8]}…`** _{status}_")
    if not thread.messages:
        out.append("  - _(no messages)_")
    else:
        for msg in sorted(thread.messages, key=lambda m: m.timestamp_ms):
            who = _humanize_user(msg.user_name, msg.user_email, msg.user_id)
            when = _fmt_ts(msg.timestamp_ms)
            body = (msg.content or "").strip().replace("\n", " ")
            out.append(f"  - {who} · {when}: {body}")
    out.append("")


def render_checklist(
    threads: dict[str, Thread], anchored: list[AnchoredComment]
) -> list[str]:
    """A tick list of every comment, so you can see what is left.

    Deliberately stateless. A tick means Overleaf says the thread is resolved,
    nothing more. Keeping progress in a side file would mean merging it on
    every run, which is the easiest way to introduce bugs nobody can reproduce.
    Tick the boxes yourself as you work; a fresh export starts from Overleaf
    again.
    """
    if not anchored:
        return []
    done = sum(1 for c in anchored
               if (t := threads.get(c.thread_id)) is not None and t.resolved)
    out = ["## Still to address", "",
           f"{done} of {len(anchored)} done, going by what is resolved in Overleaf.",
           ""]
    for c in anchored:
        thread = threads.get(c.thread_id)
        box = "x" if thread is not None and thread.resolved else " "
        quote, clipped = _clip_right(" ".join((c.anchored_text or "").split()), 48)
        quote = (quote + "…") if clipped else (quote or "(empty anchor)")
        if c.float_ref is not None:
            where = c.float_ref.describe()
        else:
            # The deepest heading only, and bounded. A full path with a paper
            # title in it makes every line unreadable, and this is a list you
            # scan rather than read.
            heading = (c.nearest_heading or c.pathname).split(" > ")[-1]
            where, clipped = _clip_right(heading, 40)
            where = (where + "…") if clipped else where
        who = ""
        if thread is not None and thread.messages:
            first = min(thread.messages, key=lambda m: m.timestamp_ms)
            who = " — " + _humanize_user(first.user_name, first.user_email, first.user_id)
        out.append(f"- [{box}] **{c.short_id}** “{quote}” — {where}{who}")
    out.append("")
    return out
