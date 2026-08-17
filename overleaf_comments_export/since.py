"""Say what changed since the last export.

Reviews arrive in waves. Between two exports of the same paper a handful of
threads are new, a few picked up replies, a few were resolved, and everything
else is exactly what you already read last week. Finding those few by reading
the whole file again is the work this saves.

It all runs off `comments.json`, which every export writes, so comparing needs
no repository and no history beyond the previous export sitting in the folder.

Identity is the thread id, never the short id. Short ids are assigned in file
then line order, so inserting one comment near the top renumbers everything
below it. A diff keyed on short ids would report the whole paper as new.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

SINCE_FILENAME = "whats-new.md"

# Papers title themselves at length, and nearest_heading picks that up. Printed
# in full it is longer than most of the comments and repeats on every line.
HEADING_CHARS = 55


def load_previous(path: str | Path) -> dict[str, Any] | None:
    """Read a previous export. Accepts a comments.json or the folder holding one.

    Returns None when there is nothing readable there, which is the normal case
    for a first export into an empty folder.
    """
    p = Path(path)
    if p.is_dir():
        p = p / "comments.json"
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


@dataclass
class Since:
    """What the comparison found. Empty lists everywhere means nothing changed."""

    comparable: bool = True
    reason: str = ""  # why not, when comparable is False
    previous_pulled_at: str | None = None
    filters_differ: bool = False

    new_comments: list[dict[str, Any]] = field(default_factory=list)
    new_replies: list[dict[str, Any]] = field(default_factory=list)
    edited: list[dict[str, Any]] = field(default_factory=list)
    resolved: list[dict[str, Any]] = field(default_factory=list)
    reopened: list[dict[str, Any]] = field(default_factory=list)
    gone: list[dict[str, Any]] = field(default_factory=list)
    new_changes: list[dict[str, Any]] = field(default_factory=list)

    @property
    def anything(self) -> bool:
        return bool(self.new_comments or self.new_replies or self.edited
                    or self.resolved or self.reopened or self.gone
                    or self.new_changes)

    def summary(self) -> str:
        """One line for the progress log."""
        if not self.comparable:
            return self.reason
        bits = [
            (len(self.new_comments), "new comment"),
            (len(self.new_replies), "thread with new replies"),
            (len(self.edited), "edited comment"),
            (len(self.resolved), "newly resolved"),
            (len(self.reopened), "reopened"),
            (len(self.gone), "gone"),
            (len(self.new_changes), "new tracked change"),
        ]
        said = [f"{n} {word}{'' if n == 1 else 's'}" for n, word in bits if n]
        if not said:
            return "Nothing has changed since the previous export."
        return "Since the previous export: " + ", ".join(said) + "."


def _threads(payload: dict[str, Any]) -> dict[str, Any]:
    t = payload.get("threads")
    return t if isinstance(t, dict) else {}


def _anchor_by_thread(payload: dict[str, Any]) -> dict[str, Any]:
    """Where each thread sits in the paper, when it sits anywhere."""
    out: dict[str, Any] = {}
    for c in payload.get("comments") or []:
        if isinstance(c, dict) and c.get("thread_id"):
            out.setdefault(c["thread_id"], c)
    return out


def _messages(thread: Any) -> list[dict[str, Any]]:
    if not isinstance(thread, dict):
        return []
    return [m for m in (thread.get("messages") or []) if isinstance(m, dict)]


def _first_message(thread: Any) -> dict[str, Any]:
    msgs = _messages(thread)
    return msgs[0] if msgs else {}


def _who(message: dict[str, Any]) -> str:
    user = message.get("user") or {}
    return (user.get("name") or user.get("email")
            or (user.get("id") or "someone")[:8])


def _when(iso: str | None) -> str:
    """The same shape of date the Markdown export prints, from an ISO string."""
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError):
        return str(iso)


def _where(anchor: dict[str, Any] | None) -> str:
    """A place a person can navigate to, said the way the Markdown says it."""
    if not anchor:
        return "not anchored to any text"
    bits = [anchor.get("pathname") or "?"]
    if anchor.get("line"):
        bits.append(f"line {anchor['line']}")
    fl = anchor.get("enclosing_float")
    if isinstance(fl, dict) and fl.get("kind"):
        name = fl["kind"].capitalize()
        bits.append(f"{name} {fl['number']}" if fl.get("number")
                    else f"an unnumbered {fl['kind']}")
    elif anchor.get("nearest_heading"):
        head = " ".join(str(anchor["nearest_heading"]).split())
        if len(head) > HEADING_CHARS:
            head = head[:HEADING_CHARS].rstrip() + "…"
        bits.append(f"§ {head}")
    return ", ".join(bits)


def compare(old: dict[str, Any], new: dict[str, Any]) -> Since:
    """Diff two comments.json payloads, old against new."""
    old_project = (old.get("project") or {}).get("id")
    new_project = (new.get("project") or {}).get("id")
    if old_project and new_project and old_project != new_project:
        return Since(
            comparable=False,
            reason=(f"The previous export in this folder is a different paper "
                    f"({old_project}), so there is nothing to compare."),
        )

    out = Since(previous_pulled_at=old.get("pulled_at"))
    # Filters decide what reaches the file at all. A thread hidden by
    # --no-resolved this time has not gone anywhere, and saying so would be a
    # lie, so when the filters differ the disappearances are not reported.
    out.filters_differ = (old.get("filters_applied") or {}) != (new.get("filters_applied") or {})

    old_threads, new_threads = _threads(old), _threads(new)
    old_anchors, new_anchors = _anchor_by_thread(old), _anchor_by_thread(new)

    for tid, thread in new_threads.items():
        anchor = new_anchors.get(tid)
        first = _first_message(thread)
        before = old_threads.get(tid)

        if before is None:
            out.new_comments.append({
                "thread_id": tid,
                "short_id": (anchor or {}).get("short_id"),
                "where": _where(anchor),
                "who": _who(first),
                "when": first.get("timestamp"),
                "text": first.get("content") or "",
                "anchored_text": (anchor or {}).get("anchored_text") or "",
                "reply_count": thread.get("reply_count") or 0,
            })
            continue

        seen = {m.get("id") for m in _messages(before)}
        fresh = [m for m in _messages(thread) if m.get("id") not in seen]
        if fresh:
            out.new_replies.append({
                "thread_id": tid,
                "short_id": (anchor or {}).get("short_id"),
                "where": _where(anchor),
                "opened_by": _who(first),
                "opening_text": first.get("content") or "",
                "replies": [{"who": _who(m), "when": m.get("timestamp"),
                             "text": m.get("content") or ""} for m in fresh],
            })

        # An edited comment changes what you have to answer without ever
        # showing up as new, which is the quietest way to miss something.
        was = {m.get("id"): m.get("content") for m in _messages(before)}
        for m in _messages(thread):
            if m.get("id") in was and was[m["id"]] != m.get("content"):
                out.edited.append({
                    "thread_id": tid,
                    "short_id": (anchor or {}).get("short_id"),
                    "where": _where(anchor),
                    "who": _who(m),
                    "was": was[m["id"]] or "",
                    "now": m.get("content") or "",
                })

        if bool(thread.get("resolved")) and not bool(before.get("resolved")):
            out.resolved.append({
                "thread_id": tid,
                "short_id": (anchor or {}).get("short_id"),
                "where": _where(anchor),
                "by": ((thread.get("resolved_by") or {}).get("name")
                       or (thread.get("resolved_by") or {}).get("email") or ""),
                "text": first.get("content") or "",
            })
        elif bool(before.get("resolved")) and not bool(thread.get("resolved")):
            out.reopened.append({
                "thread_id": tid,
                "short_id": (anchor or {}).get("short_id"),
                "where": _where(anchor),
                "text": first.get("content") or "",
            })

    if not out.filters_differ:
        for tid, thread in old_threads.items():
            if tid in new_threads:
                continue
            anchor = old_anchors.get(tid)
            first = _first_message(thread)
            out.gone.append({
                "thread_id": tid,
                "where": _where(anchor),
                "who": _who(first),
                "text": first.get("content") or "",
            })

    seen_changes = {ch.get("id") for ch in (old.get("tracked_changes") or [])
                    if isinstance(ch, dict)}
    for ch in new.get("tracked_changes") or []:
        if isinstance(ch, dict) and ch.get("id") not in seen_changes:
            out.new_changes.append({
                "short_id": ch.get("short_id"),
                "kind": ch.get("kind"),
                "content": ch.get("content") or "",
                "where": _where(ch),
                "who": (ch.get("user") or {}).get("name")
                       or (ch.get("user") or {}).get("email") or "",
            })

    return out


def _quote(text: str, limit: int = 400) -> str:
    """The comment itself, as a blockquote, clipped if someone wrote an essay."""
    text = (text or "").strip()
    if not text:
        return "> _(empty)_"
    if len(text) > limit:
        text = text[:limit].rstrip() + " …"
    return "\n".join(f"> {line}" if line.strip() else ">"
                     for line in text.splitlines())


def _head(items: list, one: str, many: str) -> str:
    return f"## {len(items)} {one if len(items) == 1 else many}"


def render_since(since: Since, *, project_title: str, previous_path: str,
                 stable: bool = False) -> str:
    """The whole file, in the order you would want to read it."""
    out: list[str] = [f"# What is new — {project_title}", ""]

    if not since.comparable:
        out += [since.reason, ""]
        return "\n".join(out)

    # A path when it is somewhere else, plain words when it is the same folder,
    # where printing an absolute path says nothing the reader does not know.
    shown = f"`{previous_path}`" if previous_path.endswith(".json") else previous_path
    where_from = f"Compared with {shown}"
    if since.previous_pulled_at and not stable:
        where_from += f", pulled {_when(since.previous_pulled_at)}"
    out += [where_from + ".", "", since.summary(), ""]

    # Said up here rather than at the end, because when it is the only thing
    # worth saying the file would otherwise stop at "nothing has changed",
    # which is exactly the case where that is misleading.
    caveat = ("Deletions are not listed. This export used different filters "
              "from the previous one, so a comment missing from it may only "
              "be filtered out rather than gone.")

    if not since.anything:
        out += ["Every comment in the export is one you have already seen.", ""]
        if since.filters_differ:
            out += [caveat, ""]
        return "\n".join(out)

    out += ["Short ids like `C012` are the ones in `comments.md` from this run. "
            "They shift when comments are added above them, so an id here will "
            "not match the same comment in an older export.", ""]

    if since.new_comments:
        out += [_head(since.new_comments, "new comment", "new comments"), ""]
        for c in since.new_comments:
            title = f"### {c['short_id']} — {c['where']}" if c["short_id"] else f"### {c['where']}"
            out.append(title)
            byline = c["who"] + (f", {_when(c['when'])}" if c["when"] and not stable else "")
            out += ["", byline, ""]
            if c["anchored_text"]:
                out += [f"On: **{c['anchored_text'].strip()}**", ""]
            out += [_quote(c["text"]), ""]
            if c["reply_count"]:
                n = c["reply_count"]
                out += [f"It already has {n} repl{'y' if n == 1 else 'ies'}, "
                        f"which are in `comments.md`.", ""]

    if since.new_replies:
        out += [_head(since.new_replies, "thread with new replies",
                      "threads with new replies"), ""]
        for t in since.new_replies:
            title = f"### {t['short_id']} — {t['where']}" if t["short_id"] else f"### {t['where']}"
            out += [title, "", f"{t['opened_by']} originally wrote:", "",
                    _quote(t["opening_text"], 200), ""]
            for r in t["replies"]:
                byline = r["who"] + (f", {_when(r['when'])}" if r["when"] and not stable else "")
                out += [f"**{byline}**", "", _quote(r["text"]), ""]

    if since.edited:
        out += [_head(since.edited, "comment was edited", "comments were edited"), ""]
        for e in since.edited:
            title = f"### {e['short_id']} — {e['where']}" if e["short_id"] else f"### {e['where']}"
            out += [title, "", f"{e['who']} changed it.", "", "It said:", "",
                    _quote(e["was"], 200), "", "It now says:", "",
                    _quote(e["now"], 200), ""]

    if since.resolved:
        out += [_head(since.resolved, "comment was marked resolved",
                      "comments were marked resolved"), ""]
        for r in since.resolved:
            sid = f"`{r['short_id']}` " if r["short_id"] else ""
            by = f", resolved by {r['by']}" if r["by"] else ""
            out.append(f"- {sid}{r['where']}{by} — {_one_line(r['text'])}")
        out.append("")

    if since.reopened:
        out += [_head(since.reopened, "comment was reopened",
                      "comments were reopened"), ""]
        for r in since.reopened:
            sid = f"`{r['short_id']}` " if r["short_id"] else ""
            out.append(f"- {sid}{r['where']} — {_one_line(r['text'])}")
        out.append("")

    if since.gone:
        out += [_head(since.gone, "comment is gone", "comments are gone"), "",
                "These were in the previous export and are not in this one. "
                "Usually that means somebody deleted the thread, or deleted the "
                "text it was attached to.", ""]
        for g in since.gone:
            out.append(f"- {g['where']}, from {g['who']} — {_one_line(g['text'])}")
        out.append("")

    if since.new_changes:
        out += [_head(since.new_changes, "new tracked change",
                      "new tracked changes"), ""]
        for ch in since.new_changes:
            sid = f"`{ch['short_id']}` " if ch["short_id"] else ""
            who = f", {ch['who']}" if ch["who"] else ""
            out.append(f"- {sid}{ch['kind']}{who}, {ch['where']} — "
                       f"{_one_line(ch['content'], 120)}")
        out.append("")

    if since.filters_differ:
        out += [caveat, ""]

    return "\n".join(out)


def _one_line(text: str, limit: int = 160) -> str:
    text = " ".join((text or "").split())
    if not text:
        return "_(empty)_"
    return text if len(text) <= limit else text[:limit].rstrip() + " …"


def short_ids(since: Since) -> dict[str, list[str]]:
    """The compact form for comments.json, so an assistant can filter on it."""
    def ids(rows):
        return [r["short_id"] for r in rows if r.get("short_id")]
    return {
        "new_comments": ids(since.new_comments),
        "new_replies": ids(since.new_replies),
        "edited": ids(since.edited),
        "resolved": ids(since.resolved),
        "reopened": ids(since.reopened),
        "new_tracked_changes": ids(since.new_changes),
        "gone_thread_ids": [r["thread_id"] for r in since.gone],
    }
