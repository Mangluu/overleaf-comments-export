"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const core = require("../src/export-core.js");

test("flattens Overleaf root-folder metadata", () => {
  const files = core.flattenFiles({
    docs: [{ _id: "doc-main", name: "main.tex" }],
    folders: [{
      name: "sections",
      docs: [{ _id: "doc-method", name: "method.tex" }],
      folders: [],
    }],
  });

  assert.deepEqual(files, [
    { docId: "doc-main", pathname: "main.tex" },
    { docId: "doc-method", pathname: "sections/method.tex" },
  ]);
});

test("relocates a nearby comment anchor and reports line and section", () => {
  const text = "\\section{Introduction}\nA short adaptive interface example.\n";
  const starts = core.buildLineStarts(text);
  const expected = text.indexOf("adaptive");
  const resolved = core.resolveAnchor(text, starts, expected - 3, "adaptive");

  assert.equal(resolved.offset, expected);
  assert.equal(resolved.line, 2);
  assert.equal(resolved.stale, false);
  assert.equal(core.nearestHeading(core.findHeadings(text, starts), 2), "Introduction");
});

test("assembles comments, replies, resolved threads, changes, and output formats", () => {
  const text = "\\section{Introduction}\nA short adaptive interface example.\n";
  const anchorOffset = text.indexOf("adaptive interface");
  const insertionOffset = text.indexOf("example");
  const rawThreads = {
    threadOpen: {
      resolved: false,
      messages: [
        {
          id: "message-1",
          content: "Please define this term.",
          timestamp: 1_700_000_000_000,
          user_id: "reviewer-1",
          user: { name: "A. Reviewer", email: "reviewer@example.org" },
        },
        {
          id: "message-2",
          content: "Agreed.",
          timestamp: 1_700_000_001_000,
          user_id: "author-1",
          user: { name: "Co Author" },
        },
      ],
    },
    threadResolved: {
      resolved: true,
      messages: [{
        id: "message-3",
        content: "Fixed already.",
        timestamp: 1_700_000_002_000,
        user_id: "reviewer-1",
        user: { name: "A. Reviewer" },
      }],
    },
  };
  const rangesPayload = {
    docs: [{
      id: "doc-main",
      ranges: {
        comments: [{ op: { t: "threadOpen", p: anchorOffset, c: "adaptive interface" } }],
        changes: [{
          id: "change-1",
          op: { p: insertionOffset, i: "clear " },
          metadata: { user_id: "author-1", ts: 1_700_000_003_000 },
        }],
      },
    }],
  };

  const exported = core.assembleExport({
    projectId: "0123456789abcdef01234567",
    projectTitle: "Demo Paper",
    rawThreads,
    rangesPayload,
    docTexts: { "doc-main": text },
    docIdToPath: { "doc-main": "main.tex" },
    includeResolved: true,
    includeChanges: true,
  });

  assert.equal(exported.payload.summary.thread_count, 2);
  assert.equal(exported.payload.summary.open_count, 1);
  assert.equal(exported.payload.summary.resolved_count, 1);
  assert.equal(exported.payload.summary.tracked_change_count, 1);
  assert.equal(exported.payload.comments[0].short_id, "C001");
  assert.equal(exported.payload.comments[0].created_at, "2023-11-14T22:13:20.000Z");
  assert.equal(exported.payload.comments[0].last_activity_at, "2023-11-14T22:13:21.000Z");
  assert.equal(exported.payload.comments[0].nearest_heading, "Introduction");
  assert.equal(exported.payload.tracked_changes[0].timestamp, "2023-11-14T22:13:23.000Z");
  assert.deepEqual(exported.payload.orphan_thread_ids, ["threadResolved"]);
  assert.match(exported.markdown, /Please define this term\./);
  assert.match(exported.markdown, /Commented: 2023-11-14 22:13 UTC/);
  assert.match(exported.markdown, /Changed: 2023-11-14 22:13 UTC/);
  assert.match(exported.markdown, /Tracked changes/);
  assert.match(exported.jsonl, /"type":"comment"/);
  assert.match(exported.responseLetter, /Response:/);
});

test("can omit resolved discussions and tracked changes", () => {
  const exported = core.assembleExport({
    projectId: "0123456789abcdef01234567",
    projectTitle: "Filtered Paper",
    rawThreads: {
      resolvedOnly: {
        resolved: true,
        messages: [{ content: "Done", timestamp: 1_700_000_000_000 }],
      },
    },
    rangesPayload: { docs: [] },
    includeResolved: false,
    includeChanges: false,
  });

  assert.equal(exported.payload.summary.thread_count, 0);
  assert.equal(exported.payload.summary.tracked_change_count, 0);
  assert.deepEqual(exported.payload.orphan_thread_ids, []);
});

test("renders Chinese Markdown and response-letter headings when selected", () => {
  const source = "\\section{方法}\n自适应界面。\n";
  const exported = core.assembleExport({
    projectId: "0123456789abcdef01234567",
    projectTitle: "双语测试",
    language: "zh",
    rawThreads: {
      thread1: {
        resolved: false,
        messages: [{
          content: "请说明这里的依据。",
          timestamp: 1_700_000_000_000,
          user_id: "reviewer",
          user: { name: "审稿人" },
        }],
      },
    },
    rangesPayload: {
      docs: [{
        id: "doc-main",
        ranges: {
          comments: [{ op: { t: "thread1", p: source.indexOf("自适应"), c: "自适应界面" } }],
          changes: [],
        },
      }],
    },
    docTexts: { "doc-main": source },
    docIdToPath: { "doc-main": "main.tex" },
  });

  assert.equal(exported.payload.report_language, "zh");
  assert.match(exported.markdown, /## 摘要/);
  assert.match(exported.markdown, /第 2 行/);
  assert.match(exported.markdown, /评论时间：2023-11-14 22:13 UTC/);
  assert.match(exported.responseLetter, /评论回复信/);
  assert.match(exported.responseLetter, /\*\*评论时间：\*\*/);
  assert.match(exported.responseLetter, /\*\*回复：\*\*/);
});

test("a stale anchor offset stays inside the document", () => {
  // It computed the bounded offset, used it for line and column, and returned
  // the raw one. An offset past the end slices to nothing, so the context read
  // as though there were none, and it contradicted the line beside it.
  const text = "Short document.\n";
  const lineStarts = core.buildLineStarts(text);

  for (const raw of [10000, -5]) {
    const got = core.resolveAnchor(text, lineStarts, raw, "text that is gone");
    assert.equal(got.stale, true);
    assert.ok(got.offset >= 0 && got.offset < text.length,
      `offset ${got.offset} is outside a ${text.length} character document`);
    assert.ok(text.slice(got.offset, got.offset + 1).length > 0);
  }
});

test("a good anchor is left exactly where it is", () => {
  const text = "alpha beta gamma\n";
  const got = core.resolveAnchor(text, core.buildLineStarts(text), text.indexOf("beta"), "beta");
  assert.equal(got.stale, false);
  assert.equal(got.offset, text.indexOf("beta"));
});
