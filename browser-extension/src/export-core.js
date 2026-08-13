(function attachOverleafCommentsCore(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.OverleafCommentsCore = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function createCore() {
  "use strict";

  const SCHEMA_VERSION = "1.3";
  const TOOL_VERSION = "1.0.0-extension";
  const CONTEXT_BEFORE = 160;
  const CONTEXT_AFTER = 160;

  function normalizeWhitespace(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function toMilliseconds(value) {
    if (value === null || value === undefined || value === "" || typeof value === "boolean") {
      return null;
    }
    if (typeof value === "number" && Number.isFinite(value)) {
      return Math.trunc(value);
    }
    const text = String(value).trim();
    if (/^-?\d+$/.test(text)) {
      return Number.parseInt(text, 10);
    }
    const parsed = Date.parse(text);
    return Number.isNaN(parsed) ? null : parsed;
  }

  function isoTimestamp(value) {
    const milliseconds = toMilliseconds(value);
    if (!milliseconds) return null;
    try {
      return new Date(milliseconds).toISOString();
    } catch {
      return null;
    }
  }

  function displayTimestamp(value) {
    const iso = isoTimestamp(value);
    return iso ? `${iso.slice(0, 16).replace("T", " ")} UTC` : "?";
  }

  function userDetails(message) {
    const user = message?.user || {};
    const name = user.name || [user.first_name, user.last_name].filter(Boolean).join(" ") || null;
    return {
      id: String(message?.user_id || message?.userId || ""),
      name,
      email: user.email || null,
    };
  }

  function humanizeUser(user) {
    if (user?.name) return user.name;
    if (user?.email) {
      const local = user.email.split("@", 1)[0];
      const parts = local.replace(/[_-]/g, ".").split(".").filter(Boolean);
      if (parts.length >= 2 && parts.every((part) => /^[a-z]+$/i.test(part))) {
        return parts.map((part) => part[0].toUpperCase() + part.slice(1)).join(" ");
      }
      return local;
    }
    return (user?.id || "unknown").slice(0, 8);
  }

  function buildUserMap(rawThreads) {
    const users = {};
    for (const thread of Object.values(rawThreads || {})) {
      if (!thread || typeof thread !== "object") continue;
      for (const message of thread.messages || []) {
        const user = userDetails(message);
        if (!user.id) continue;
        users[user.id] ||= { id: user.id, name: null, email: null };
        if (user.name && !users[user.id].name) users[user.id].name = user.name;
        if (user.email && !users[user.id].email) users[user.id].email = user.email;
      }
    }
    return users;
  }

  function parseThreads(rawThreads, resolvedIds = []) {
    const resolved = new Set(Array.from(resolvedIds || [], String));
    const threads = {};
    for (const [threadId, rawThread] of Object.entries(rawThreads || {})) {
      if (!rawThread || typeof rawThread !== "object") continue;
      const messages = (rawThread.messages || []).map((message) => {
        const user = userDetails(message);
        return {
          id: String(message?.id || message?._id || ""),
          content: String(message?.content || ""),
          timestampMs: toMilliseconds(message?.timestamp) || 0,
          editedAtMs: toMilliseconds(message?.edited_at),
          user,
        };
      });
      threads[threadId] = {
        id: threadId,
        messages,
        resolved: Boolean(rawThread.resolved || resolved.has(threadId)),
        resolvedAtMs: toMilliseconds(rawThread.resolved_at),
        resolvedByUserId: rawThread.resolved_by_user_id
          ? String(rawThread.resolved_by_user_id)
          : null,
      };
    }
    return threads;
  }

  function flattenFiles(filesRoot) {
    const output = [];

    function walk(node, parentPath) {
      if (!node) return;
      if (Array.isArray(node)) {
        for (const child of node) walk(child, parentPath);
        return;
      }
      if (typeof node !== "object") return;

      if (node.rootFolder) {
        walk(node.rootFolder, parentPath);
      }

      for (const doc of node.docs || []) {
        const id = doc?._id || doc?.id || doc?.doc_id;
        const name = doc?.name;
        if (id && name) output.push({ docId: String(id), pathname: `${parentPath}${name}` });
      }

      for (const folder of node.folders || []) {
        const name = folder?.name || "";
        const nextPath = name && name !== "rootFolder" ? `${parentPath}${name}/` : parentPath;
        walk(folder, nextPath);
      }

      if (Array.isArray(node.children)) {
        if (node.type === "folder") {
          const name = node.name || "";
          const nextPath = name && name !== "rootFolder" ? `${parentPath}${name}/` : parentPath;
          for (const child of node.children) walk(child, nextPath);
        } else {
          for (const child of node.children) walk(child, parentPath);
        }
      }

      const kind = node.type || node.kind;
      const id = node._id || node.id || node.doc_id;
      if (id && node.name && kind === "doc") {
        output.push({ docId: String(id), pathname: `${parentPath}${node.name}` });
      }
    }

    walk(filesRoot, "");
    const seen = new Set();
    return output.filter((entry) => {
      const key = `${entry.docId}\u0000${entry.pathname}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  function documentRanges(payload) {
    const docs = Array.isArray(payload)
      ? payload
      : payload && typeof payload === "object"
        ? payload.docs || payload.ranges || []
        : [];
    const output = [];
    for (const entry of docs) {
      if (!entry || typeof entry !== "object") continue;
      const docId = entry.id || entry._id || entry.doc_id;
      if (!docId) continue;
      const ranges = entry.ranges || {};
      output.push({
        docId: String(docId),
        comments: Array.isArray(ranges.comments) ? ranges.comments : [],
        changes: Array.isArray(ranges.changes) ? ranges.changes : [],
      });
    }
    return output;
  }

  function buildLineStarts(text) {
    const starts = [0];
    for (let index = 0; index < text.length; index += 1) {
      if (text[index] === "\n") starts.push(index + 1);
    }
    return starts;
  }

  function upperBound(values, target) {
    let low = 0;
    let high = values.length;
    while (low < high) {
      const middle = Math.floor((low + high) / 2);
      if (values[middle] <= target) low = middle + 1;
      else high = middle;
    }
    return low;
  }

  function offsetToLineColumn(lineStarts, rawOffset) {
    const offset = Math.max(0, Number(rawOffset) || 0);
    const line = Math.max(1, upperBound(lineStarts, offset));
    return { line, column: offset - lineStarts[line - 1] };
  }

  function resolveAnchor(text, lineStarts, rawOffset, anchoredText, searchWindow = 200) {
    const offset = Math.max(0, Number(rawOffset) || 0);
    const anchor = String(anchoredText || "");
    if (anchor && text.slice(offset, offset + anchor.length) === anchor) {
      return { offset, ...offsetToLineColumn(lineStarts, offset), stale: false };
    }

    if (anchor) {
      const low = Math.max(0, offset - searchWindow);
      const high = Math.min(text.length, offset + searchWindow + anchor.length);
      const nearby = text.indexOf(anchor, low);
      if (nearby !== -1 && nearby <= high - anchor.length) {
        return { offset: nearby, ...offsetToLineColumn(lineStarts, nearby), stale: false };
      }
      const anywhere = text.indexOf(anchor);
      if (anywhere !== -1) {
        return { offset: anywhere, ...offsetToLineColumn(lineStarts, anywhere), stale: true };
      }
    }

    const bounded = Math.min(offset, Math.max(0, text.length - 1));
    return { offset, ...offsetToLineColumn(lineStarts, bounded), stale: true };
  }

  function findHeadings(text, lineStarts) {
    const headings = [];
    const levels = {
      part: -1,
      chapter: 0,
      section: 1,
      subsection: 2,
      subsubsection: 3,
      paragraph: 4,
    };
    const headingPattern = /^\s*\\(section|subsection|subsubsection|chapter|paragraph|part)\*?\s*(?:\[[^\]]*\])?\s*\{(.*?)\}/gm;
    for (const match of text.matchAll(headingPattern)) {
      headings.push({
        line: upperBound(lineStarts, match.index),
        level: levels[match[1]] ?? 99,
        text: match[2].trim(),
      });
    }

    const pseudoPattern = /^\s*\\(?:begin\{(abstract|titlepage)\}|(title|maketitle|tableofcontents|frontmatter|mainmatter|backmatter|appendix))(?:\s*\{([^}]*)\})?/gm;
    for (const match of text.matchAll(pseudoPattern)) {
      const environment = match[1];
      const command = match[2];
      const argument = (match[3] || "").trim();
      let label = null;
      if (environment === "abstract") label = "Abstract";
      else if (environment === "titlepage") label = "Title page";
      else if (command === "title") label = argument ? `Title: ${argument}` : "Title";
      else if (command === "maketitle") label = "Title block";
      else if (command === "tableofcontents") label = "Table of contents";
      else if (command === "frontmatter") label = "Front matter";
      else if (command === "mainmatter") label = "Main matter";
      else if (command === "backmatter") label = "Back matter";
      else if (command === "appendix") label = "Appendix";
      if (label) {
        headings.push({ line: upperBound(lineStarts, match.index), level: 1, text: label });
      }
    }

    return headings.sort((left, right) => left.line - right.line || left.level - right.level);
  }

  function nearestHeading(headings, line) {
    const enclosing = new Map();
    for (const heading of headings) {
      if (heading.line > line) break;
      enclosing.set(heading.level, heading);
      for (const level of Array.from(enclosing.keys())) {
        if (level > heading.level) enclosing.delete(level);
      }
    }
    return Array.from(enclosing.keys())
      .sort((left, right) => left - right)
      .map((level) => enclosing.get(level).text)
      .join(" > ") || null;
  }

  function extractContext(text, offset, anchoredText, line) {
    if (!text) {
      return {
        line,
        before: "",
        anchor: anchoredText || "",
        after: "",
        truncatedBefore: false,
        truncatedAfter: false,
      };
    }
    const anchor = String(anchoredText || "");
    let end = offset + anchor.length;
    let actualAnchor = anchor;
    if (!anchor || text.slice(offset, end) !== anchor) {
      if (!anchor) {
        actualAnchor = text.slice(offset, offset + Math.min(40, Math.max(0, text.length - offset)));
        end = offset + actualAnchor.length;
      }
    }
    return {
      line,
      before: normalizeWhitespace(text.slice(Math.max(0, offset - CONTEXT_BEFORE), offset)),
      anchor: normalizeWhitespace(actualAnchor),
      after: normalizeWhitespace(text.slice(end, Math.min(text.length, end + CONTEXT_AFTER))),
      truncatedBefore: offset > CONTEXT_BEFORE,
      truncatedAfter: end < text.length - CONTEXT_AFTER,
    };
  }

  function deletionContext(text, offset, deletedText, line) {
    const bounded = Math.max(0, Math.min(Number(offset) || 0, text.length));
    return {
      line,
      before: normalizeWhitespace(text.slice(Math.max(0, bounded - CONTEXT_BEFORE), bounded)),
      anchor: normalizeWhitespace(deletedText),
      after: normalizeWhitespace(text.slice(bounded, bounded + CONTEXT_AFTER)),
      truncatedBefore: bounded > CONTEXT_BEFORE,
      truncatedAfter: bounded + CONTEXT_AFTER < text.length,
    };
  }

  function serializeThread(thread, userMap) {
    const messages = [...thread.messages].sort((left, right) => left.timestampMs - right.timestampMs);
    const resolver = thread.resolvedByUserId ? userMap[thread.resolvedByUserId] : null;
    return {
      id: thread.id,
      resolved: thread.resolved,
      resolved_at: isoTimestamp(thread.resolvedAtMs),
      resolved_by: resolver || (thread.resolvedByUserId ? { id: thread.resolvedByUserId, name: null, email: null } : null),
      reply_count: Math.max(0, messages.length - 1),
      messages: messages.map((message, index) => ({
        id: message.id,
        role: index === 0 ? "comment" : "reply",
        reply_index: index === 0 ? null : index - 1,
        user: message.user,
        content: message.content,
        timestamp: isoTimestamp(message.timestampMs),
        edited_at: isoTimestamp(message.editedAtMs),
      })),
    };
  }

  function inlineContext(context, anchoredText) {
    if (!context) return anchoredText ? `> **▸${anchoredText}◂**` : "> _(anchor text unavailable)_";
    const before = context.before.length > 70 ? context.before.slice(-70).trimStart() : context.before;
    const after = context.after.length > 70 ? context.after.slice(0, 70).trimEnd() : context.after;
    const lead = context.truncatedBefore || context.before.length > 70 ? "…" : "";
    const tail = context.truncatedAfter || context.after.length > 70 ? "…" : "";
    return `> ${lead}${before}${before ? " " : ""}**▸${context.anchor || anchoredText || ""}◂**${after ? ` ${after}` : ""}${tail}`;
  }

  function emitMessages(lines, thread, indent = "") {
    const messages = [...(thread?.messages || [])].sort((left, right) => left.timestampMs - right.timestampMs);
    if (!messages.length) {
      lines.push(`${indent}- _(no messages)_`);
      return;
    }
    messages.forEach((message, index) => {
      const who = humanizeUser(message.user);
      const when = displayTimestamp(message.timestampMs);
      const edited = message.editedAtMs ? " _(edited)_" : "";
      const prefix = index === 0 ? `${indent}- ` : `${indent}  - ↳ `;
      const body = String(message.content || "").trim();
      if (body.includes("\n")) {
        lines.push(`${prefix}**${who}** · ${when}${edited}:`);
        for (const bodyLine of body.split(/\r?\n/)) lines.push(`${indent}    > ${bodyLine}`);
      } else {
        lines.push(`${prefix}**${who}** · ${when}${edited}: ${body}`);
      }
    });
  }

  const REPORT_COPY = {
    zh: {
      title: "Overleaf 评论 — {title}",
      summary: "摘要",
      threads: "**讨论：** {total}（{open} 个未解决，{resolved} 个已解决）",
      changes: "**修订记录：** {count}",
      files: "**文件：** {count}",
      reviewers: "**评论者：** {count}",
      noSection: "_(无所属章节)_",
      line: "第 {line} 行",
      resolved: "已解决",
      open: "未解决",
      reply: "{count} 条回复",
      commentedAt: "评论时间：{time}",
      trackedChanges: "修订记录",
      insertion: "插入",
      deletion: "删除",
      changedAt: "修订时间：{time}",
      orphanTitle: "无法定位锚点的讨论",
      orphanHelp: "_Overleaf 返回了这些讨论，但无法将它们定位到当前源文件文本。_",
      thread: "讨论",
      responseTitle: "评论回复信 — {title}",
      noOpen: "_没有发现带锚点的未解决评论。_",
      referringTo: "**对应原文：**",
      comment: "**评论：**",
      commentTime: "**评论时间：** {time}",
      response: "**回复：**",
      changeMade: "**所作修改：**",
      changeTodo: "_待填写 — 说明修改内容和位置。_",
    },
    en: {
      title: "Overleaf comments — {title}",
      summary: "Summary",
      threads: "**Threads:** {total} ({open} open, {resolved} resolved)",
      changes: "**Tracked changes:** {count}",
      files: "**Files:** {count}",
      reviewers: "**Reviewers:** {count}",
      noSection: "_(no enclosing section)_",
      line: "Line {line}",
      resolved: "resolved",
      open: "open",
      reply: "{count} {label}",
      commentedAt: "Commented: {time}",
      trackedChanges: "Tracked changes",
      insertion: "insertion",
      deletion: "deletion",
      changedAt: "Changed: {time}",
      orphanTitle: "Threads without resolvable anchors",
      orphanHelp: "_These discussions were returned by Overleaf but could not be mapped to live source text._",
      thread: "Thread",
      responseTitle: "Response to comments — {title}",
      noOpen: "_No open anchored comments were found._",
      referringTo: "**Referring to:**",
      comment: "**Comment:**",
      commentTime: "**Comment time:** {time}",
      response: "**Response:**",
      changeMade: "**Change made:**",
      changeTodo: "_TODO — describe what changed and where._",
    },
  };

  function reportText(payload, key, replacements = {}) {
    const language = payload.report_language === "zh" ? "zh" : "en";
    let value = REPORT_COPY[language][key] || REPORT_COPY.en[key] || key;
    for (const [name, replacement] of Object.entries(replacements)) {
      value = value.replaceAll(`{${name}}`, String(replacement));
    }
    return value;
  }

  function renderMarkdown(payload) {
    const summary = payload.summary;
    const lines = [
      "---",
      `schema_version: ${payload.schema_version}`,
      `tool_version: ${payload.tool_version}`,
      `project_id: ${payload.project.id}`,
      `project_title: ${JSON.stringify(payload.project.title)}`,
      `pulled_at: ${payload.pulled_at}`,
      `thread_count: ${summary.thread_count}`,
      `open_count: ${summary.open_count}`,
      `resolved_count: ${summary.resolved_count}`,
      `tracked_change_count: ${summary.tracked_change_count}`,
      `stale_anchor_count: ${summary.stale_anchor_count}`,
      `file_count: ${summary.file_count}`,
      `reviewer_count: ${summary.reviewer_count}`,
      "companion_json: comments.json",
      "companion_agents: agents.md",
      "---",
      "",
      `# ${reportText(payload, "title", { title: payload.project.title })}`,
      "",
      `## ${reportText(payload, "summary")}`,
      "",
      `- ${reportText(payload, "threads", { total: summary.thread_count, open: summary.open_count, resolved: summary.resolved_count })}`,
      `- ${reportText(payload, "changes", { count: summary.tracked_change_count })}`,
      `- ${reportText(payload, "files", { count: summary.file_count })}`,
      `- ${reportText(payload, "reviewers", { count: summary.reviewer_count })}`,
      "",
    ];

    const commentsByPath = new Map();
    for (const comment of payload.comments) {
      if (!commentsByPath.has(comment.pathname)) commentsByPath.set(comment.pathname, []);
      commentsByPath.get(comment.pathname).push(comment);
    }
    const changesByPath = new Map();
    for (const change of payload.tracked_changes) {
      if (!changesByPath.has(change.pathname)) changesByPath.set(change.pathname, []);
      changesByPath.get(change.pathname).push(change);
    }
    const paths = Array.from(new Set([...commentsByPath.keys(), ...changesByPath.keys()])).sort();

    for (const pathname of paths) {
      lines.push(`## ${pathname}`, "");
      let previousHeading = null;
      for (const comment of commentsByPath.get(pathname) || []) {
        const heading = comment.nearest_heading || reportText(payload, "noSection");
        if (heading !== previousHeading) {
          lines.push(`### § ${heading}`, "");
          previousHeading = heading;
        }
        const thread = payload.threads[comment.thread_id];
        const replies = thread?.reply_count || 0;
        const status = reportText(payload, thread?.resolved ? "resolved" : "open");
        const stale = comment.stale ? " · ⚠ stale" : "";
        const quote = normalizeWhitespace(comment.anchored_text);
        const replyLabel = payload.report_language === "zh"
          ? reportText(payload, "reply", { count: replies })
          : reportText(payload, "reply", { count: replies, label: replies === 1 ? "reply" : "replies" });
        lines.push(`**${reportText(payload, "line", { line: comment.line })}**`, "", inlineContext(comment.context, quote), "");
        lines.push(
          `**${comment.short_id}** _${status}${replies ? ` · ${replyLabel}` : ""}${stale}_ — “${quote}”`,
          `- ${reportText(payload, "commentedAt", { time: displayTimestamp(comment.created_at) })}`
        );
        emitMessages(lines, thread);
        lines.push("");
      }

      const changes = changesByPath.get(pathname) || [];
      if (changes.length) lines.push(`### § ${reportText(payload, "trackedChanges")}`, "");
      for (const change of changes) {
        const sign = change.kind === "insertion" ? "+" : "-";
        lines.push(
          `**${change.short_id}** _${reportText(payload, change.kind)}_ — ${reportText(payload, "line", { line: change.line })} — ${humanizeUser(change.user)} · ${displayTimestamp(change.timestamp)}`,
          `- ${reportText(payload, "changedAt", { time: displayTimestamp(change.timestamp) })}`,
          `- \`${sign} ${normalizeWhitespace(change.content)}\``,
          ""
        );
      }
    }

    if (payload.orphan_thread_ids.length) {
      lines.push(`## ${reportText(payload, "orphanTitle")}`, "", reportText(payload, "orphanHelp"), "");
      for (const threadId of payload.orphan_thread_ids) {
        const thread = payload.threads[threadId];
        lines.push(`- **${reportText(payload, "thread")} \`${threadId.slice(0, 8)}…\`** _${reportText(payload, thread.resolved ? "resolved" : "open")}_`);
        emitMessages(lines, thread, "  ");
        lines.push("");
      }
    }

    return `${lines.join("\n").trimEnd()}\n`;
  }

  function renderJsonLines(payload) {
    const records = [];
    for (const comment of payload.comments) {
      records.push({
        schema_version: payload.schema_version,
        type: "comment",
        project: payload.project,
        ...comment,
        thread: payload.threads[comment.thread_id] || null,
      });
    }
    for (const threadId of payload.orphan_thread_ids) {
      records.push({
        schema_version: payload.schema_version,
        type: "orphan_thread",
        project: payload.project,
        thread: payload.threads[threadId],
      });
    }
    return records.map((record) => JSON.stringify(record)).join("\n") + (records.length ? "\n" : "");
  }

  function renderAgentsBrief(payload, markdownName) {
    // Deliberately the same brief the Python export writes. It is the file
    // that tells an assistant how to read the other two, so the two exports
    // saying different things would defeat the point of sharing a schema
    // version.
    return `# Agent brief - Overleaf comments for ${payload.project.title}

You are reading an Overleaf comment export produced by the
overleaf-comments-export browser extension. Two files in this folder are
relevant:

- \`${markdownName}\` - human-readable Markdown, with YAML front-matter and
  comments grouped by file, then section, then line. Every comment has a
  stable short ID like \`C001\`, assigned in file then line order. The
  Markdown is the canonical user-facing view.
- \`comments.json\` - the same data in structured form. Use this when you need
  to enumerate, filter, or programmatically address comments.

## JSON schema (key parts)

- \`schema_version\` (string)
- \`project\` - \`{ id, title }\`
- \`summary\` - counts (threads, open/resolved, tracked changes, stale, files,
  reviewers)
- \`threads\` - \`{ "<thread_id>": { id, resolved, resolved_at,
  resolved_by_user_id, messages: [...] } }\` - stored once at top level, not
  duplicated inside each comment.
- \`files\` - list of \`{ pathname, doc_id, comment_count, change_count,
  comment_short_ids, change_short_ids }\`
- \`comments\` - list of \`{ short_id, thread_id, doc_id, pathname, line, col,
  offset, nearest_heading, anchored_text, stale, context }\`. To get the
  discussion, look up \`threads[thread_id]\`.
- \`tracked_changes\` - list of \`{ short_id, id, doc_id, pathname, kind
  (insertion|deletion), content, line, col, offset, nearest_heading, user,
  timestamp, context }\`
- \`orphan_thread_ids\` - IDs of threads that do not anchor to live source.

\`context\` is a compact char-window snippet: \`before\`, \`anchor\`, \`after\`,
with \`truncated_before\`/\`truncated_after\` flags.

## How to address comments

- Refer to comments by \`short_id\`, for example "C014", not by \`thread_id\`.
- Each thread's FIRST message is the reviewer's actual ask. Later messages are
  follow-up discussion, often between co-authors. Answer the ask, taking the
  discussion into account; do not re-litigate sub-points the replies already
  settled.
- For each open comment, propose an edit to the .tex source. If the comment is
  a question, answer it; if it is a request, attempt the change.
- Stale comments (\`stale: true\`) may not point to the current location in the
  doc. Use \`anchored_text\` and \`nearest_heading\` to find the right spot.
- Tracked changes (\`T001\`-prefixed) are not comment threads; they are
  insertions and deletions someone made with Track Changes enabled. Treat them
  as suggested edits to accept, reject, or modify.

## What you do NOT have

- The full \`.tex\` source of the paper. You only see a short window around each
  anchor. If you need more context, ask the user to share the relevant \`.tex\`
  file.
- The ability to push edits back to Overleaf. Output any proposed edits as
  diffs or rewrites; the user will apply them.

Project ID for reference: \`${payload.project.id}\`.
`;
  }

  function renderResponseLetter(payload) {
    const lines = [`# ${reportText(payload, "responseTitle", { title: payload.project.title })}`, ""];
    const openComments = payload.comments.filter((comment) => !payload.threads[comment.thread_id]?.resolved);
    if (!openComments.length) {
      lines.push(reportText(payload, "noOpen"), "");
      return lines.join("\n");
    }
    for (const comment of openComments) {
      const thread = payload.threads[comment.thread_id];
      const rootMessage = thread?.messages?.[0];
      lines.push(
        `## ${comment.short_id} — ${comment.pathname}:${comment.line}`,
        "",
        `${reportText(payload, "referringTo")} “${normalizeWhitespace(comment.anchored_text)}”`,
        "",
        reportText(payload, "commentTime", { time: displayTimestamp(comment.created_at) }),
        "",
        reportText(payload, "comment"),
        "",
        `> ${String(rootMessage?.content || "").replace(/\r?\n/g, "\n> ")}`,
        "",
        reportText(payload, "response"),
        "",
        "_TODO_",
        "",
        reportText(payload, "changeMade"),
        "",
        reportText(payload, "changeTodo"),
        ""
      );
    }
    return `${lines.join("\n").trimEnd()}\n`;
  }

  function assembleExport({
    projectId,
    projectTitle,
    language = "en",
    rawThreads,
    resolvedIds = [],
    rangesPayload = null,
    docTexts = {},
    docIdToPath = {},
    includeResolved = true,
    includeChanges = true,
  }) {
    const allThreads = parseThreads(rawThreads, resolvedIds);
    const userMap = buildUserMap(rawThreads);
    const anchored = [];
    const trackedChanges = [];
    const referencedThreadIds = new Set();

    for (const entry of documentRanges(rangesPayload)) {
      const text = docTexts[entry.docId];
      if (typeof text !== "string") continue;
      const pathname = docIdToPath[entry.docId] || `<unknown-${entry.docId}>`;
      const lineStarts = buildLineStarts(text);
      const headings = findHeadings(text, lineStarts);

      for (const rawComment of entry.comments) {
        const operation = rawComment?.op || {};
        const threadId = operation.t || rawComment?.t;
        if (!threadId) continue;
        const anchoredText = String(operation.c || "");
        const resolved = resolveAnchor(text, lineStarts, Number(operation.p) || 0, anchoredText);
        anchored.push({
          shortId: "",
          threadId: String(threadId),
          docId: entry.docId,
          pathname,
          offset: resolved.offset,
          anchoredText,
          line: resolved.line,
          column: resolved.column,
          nearestHeading: nearestHeading(headings, resolved.line),
          stale: resolved.stale,
          context: extractContext(text, resolved.offset, anchoredText, resolved.line),
        });
        referencedThreadIds.add(String(threadId));
      }

      if (includeChanges) {
        for (const rawChange of entry.changes) {
          const operation = rawChange?.op || {};
          const metadata = rawChange?.metadata || {};
          let kind = null;
          let content = "";
          if (Object.prototype.hasOwnProperty.call(operation, "i")) {
            kind = "insertion";
            content = String(operation.i || "");
          } else if (Object.prototype.hasOwnProperty.call(operation, "d")) {
            kind = "deletion";
            content = String(operation.d || "");
          }
          if (!kind) continue;
          const rawOffset = Number(operation.p) || 0;
          const resolved = resolveAnchor(text, lineStarts, rawOffset, kind === "insertion" ? content : "");
          const userId = metadata.user_id ? String(metadata.user_id) : "";
          trackedChanges.push({
            shortId: "",
            id: String(rawChange?.id || rawChange?._id || ""),
            docId: entry.docId,
            pathname,
            kind,
            content,
            offset: rawOffset,
            line: resolved.line,
            column: resolved.column,
            nearestHeading: nearestHeading(headings, resolved.line),
            user: userMap[userId] || { id: userId, name: null, email: null },
            timestampMs: toMilliseconds(metadata.ts),
            context: kind === "insertion"
              ? extractContext(text, resolved.offset, content, resolved.line)
              : deletionContext(text, rawOffset, content, resolved.line),
          });
        }
      }
    }

    anchored.sort((left, right) =>
      left.pathname.localeCompare(right.pathname) || left.line - right.line || left.column - right.column || left.offset - right.offset
    );
    anchored.forEach((comment, index) => { comment.shortId = `C${String(index + 1).padStart(3, "0")}`; });
    trackedChanges.sort((left, right) =>
      left.pathname.localeCompare(right.pathname) || left.line - right.line || left.column - right.column || left.offset - right.offset
    );
    trackedChanges.forEach((change, index) => { change.shortId = `T${String(index + 1).padStart(3, "0")}`; });

    const visibleComments = anchored.filter((comment) => {
      const thread = allThreads[comment.threadId];
      return includeResolved || !thread?.resolved;
    });
    const orphanThreads = Object.values(allThreads).filter((thread) =>
      !referencedThreadIds.has(thread.id) && (includeResolved || !thread.resolved)
    );
    const visibleThreadIds = new Set([
      ...visibleComments.map((comment) => comment.threadId),
      ...orphanThreads.map((thread) => thread.id),
    ]);
    const visibleThreads = {};
    for (const threadId of [...visibleThreadIds].sort()) {
      if (allThreads[threadId]) visibleThreads[threadId] = serializeThread(allThreads[threadId], userMap);
    }

    const files = [];
    const allPaths = new Set([
      ...visibleComments.map((comment) => comment.pathname),
      ...trackedChanges.map((change) => change.pathname),
    ]);
    for (const pathname of [...allPaths].sort()) {
      const docId = Object.keys(docIdToPath).find((id) => docIdToPath[id] === pathname) || null;
      files.push({
        pathname,
        doc_id: docId,
        comment_count: visibleComments.filter((comment) => comment.pathname === pathname).length,
        change_count: trackedChanges.filter((change) => change.pathname === pathname).length,
      });
    }

    const serializedComments = visibleComments.map((comment) => {
      const messages = visibleThreads[comment.threadId]?.messages || [];
      return {
        short_id: comment.shortId,
        thread_id: comment.threadId,
        doc_id: comment.docId,
        pathname: comment.pathname,
        line: comment.line,
        col: comment.column,
        offset: comment.offset,
        nearest_heading: comment.nearestHeading,
        anchored_text: comment.anchoredText,
        stale: comment.stale,
        created_at: messages[0]?.timestamp || null,
        last_activity_at: messages.at(-1)?.timestamp || null,
        reply_count: visibleThreads[comment.threadId]?.reply_count || 0,
        context: comment.context ? {
          line: comment.context.line,
          before: comment.context.before,
          anchor: comment.context.anchor,
          after: comment.context.after,
          truncated_before: comment.context.truncatedBefore,
          truncated_after: comment.context.truncatedAfter,
        } : null,
      };
    });
    const serializedChanges = trackedChanges.map((change) => ({
      short_id: change.shortId,
      id: change.id,
      doc_id: change.docId,
      pathname: change.pathname,
      kind: change.kind,
      content: change.content,
      line: change.line,
      col: change.column,
      offset: change.offset,
      nearest_heading: change.nearestHeading,
      user: change.user,
      timestamp: isoTimestamp(change.timestampMs),
      occurred_at: isoTimestamp(change.timestampMs),
      context: change.context ? {
        line: change.context.line,
        before: change.context.before,
        anchor: change.context.anchor,
        after: change.context.after,
        truncated_before: change.context.truncatedBefore,
        truncated_after: change.context.truncatedAfter,
      } : null,
    }));

    const threadValues = Object.values(visibleThreads);
    const reviewerKeys = new Set();
    for (const thread of threadValues) {
      for (const message of thread.messages) {
        const user = message.user || {};
        const key = user.id || user.email || user.name;
        if (key) reviewerKeys.add(key);
      }
    }

    const payload = {
      schema_version: SCHEMA_VERSION,
      tool_version: TOOL_VERSION,
      report_language: language === "zh" ? "zh" : "en",
      project: { id: projectId, title: projectTitle || projectId },
      pulled_at: new Date().toISOString(),
      summary: {
        thread_count: threadValues.length,
        open_count: threadValues.filter((thread) => !thread.resolved).length,
        resolved_count: threadValues.filter((thread) => thread.resolved).length,
        tracked_change_count: serializedChanges.length,
        stale_anchor_count: serializedComments.filter((comment) => comment.stale).length,
        file_count: files.length,
        reviewer_count: reviewerKeys.size,
      },
      threads: visibleThreads,
      files,
      comments: serializedComments,
      tracked_changes: serializedChanges,
      orphan_thread_ids: orphanThreads.map((thread) => thread.id).sort(),
    };

    return {
      payload,
      markdown: renderMarkdown(payload),
      jsonl: renderJsonLines(payload),
      responseLetter: renderResponseLetter(payload),
    };
  }

  return {
    SCHEMA_VERSION,
    TOOL_VERSION,
    assembleExport,
    buildLineStarts,
    documentRanges,
    findHeadings,
    flattenFiles,
    nearestHeading,
    normalizeWhitespace,
    offsetToLineColumn,
    parseThreads,
    renderJsonLines,
    renderMarkdown,
    renderAgentsBrief,
    renderResponseLetter,
    resolveAnchor,
    toMilliseconds,
  };
});
