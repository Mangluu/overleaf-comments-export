from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Iterable, Literal

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
) -> str:
    pulled_at_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

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
    out.append(f"project_id: {project_id}")
    out.append(f'project_title: "{project_title}"')
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
        top = reviewer_counter.most_common(5)
        out.append(
            "- **Most active reviewers:** "
            + ", ".join(f"{name} ({n})" for name, n in top)
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

    return "\n".join(out).rstrip() + "\n"


def _status_badge(thread: Thread | None, stale: bool) -> str:
    bits = []
    if thread and thread.resolved:
        bits.append("resolved")
    else:
        bits.append("open")
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
    out.append(head)
    if thread is None or not thread.messages:
        out.append("- _(no messages)_")
    else:
        for msg in sorted(thread.messages, key=lambda m: m.timestamp_ms):
            who = _humanize_user(msg.user_name, msg.user_email, msg.user_id)
            when = _fmt_ts(msg.timestamp_ms)
            edited = " _(edited)_" if msg.edited_at_ms else ""
            body = (msg.content or "").strip()
            # If body is single-line, render inline; multi-line gets a
            # blockquote so it stays readable.
            if "\n" in body:
                out.append(f"- **{who}** · {when}{edited}:")
                for line in body.splitlines():
                    out.append(f"  > {line}")
            else:
                out.append(f"- **{who}** · {when}{edited}: {body}")
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
                out.append(f"  > {lead}{before} **▸here◂** {after}{tail}")
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
