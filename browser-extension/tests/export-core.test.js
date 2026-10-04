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
  assert.equal(exported.payload.comments[0].created_at, "2023-11-14T22:13:20+00:00");
  assert.equal(exported.payload.comments[0].last_activity_at, "2023-11-14T22:13:21+00:00");
  assert.equal(exported.payload.comments[0].nearest_heading, "Introduction");
  assert.equal(exported.payload.tracked_changes[0].timestamp, "2023-11-14T22:13:23+00:00");
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

test("the include chain is readable from outside, for fetching the rest", () => {
  // The page needs this to fetch files that carry no comments. A figure in
  // one of those still decides what number the next figure gets.
  assert.deepEqual(core.findIncludes("\\input{a}\n\\include{b/c}\n"), ["a", "b/c"]);
  assert.deepEqual(core.findIncludes("% \\input{draft}\n\\input{real}"), ["real"]);
  assert.equal(core.resolveInclude("intro", { "sections/intro.tex": "x" }),
               "sections/intro.tex");
  assert.equal(core.resolveInclude("nope", { "a.tex": "x" }), null);
});


test("timestamps are written the way Python writes them", () => {
  // Both exports claim the same schema, so the same instant has to be the
  // same string, not two spellings of it. Python is the one to match: the
  // project supports 3.10, whose fromisoformat cannot read the Z form, and
  // since.py parses these back.
  const threads = {
    t1: { messages: [{ id: "m1", content: "x", timestamp: 1700000000000,
                       user_id: "u1", user: { name: "R" } }] },
  };
  const out = core.assembleExport({
    projectId: "0123456789abcdef01234567", projectTitle: "P",
    rawThreads: threads, resolvedIds: [], rangesPayload: [],
    docTexts: {}, docIdToPath: {},
  });
  const stamp = out.payload.threads.t1.messages[0].timestamp;
  assert.match(stamp, /\+00:00$/, `got ${stamp}`);
  assert.doesNotMatch(stamp, /Z$/);
});

test("the reviewer filter keeps threads that person took part in", () => {
  // A reply is theirs too, so a thread somebody else started but they
  // answered still counts. Matches what --reviewer does in the Python tool.
  const threads = {
    t1: { messages: [
      { id: "m1", content: "started by one", user: { name: "Bakhtawar Khan" } },
      { id: "m2", content: "answered by another", user: { name: "ans.ahmad" } },
    ] },
    t2: { messages: [{ id: "m3", content: "only one", user: { name: "ans.ahmad" } }] },
  };
  const run = (reviewer) => core.assembleExport({
    projectId: "0123456789abcdef01234567", projectTitle: "P",
    rawThreads: threads, resolvedIds: [], rangesPayload: [],
    docTexts: {}, docIdToPath: {}, reviewer,
  }).payload.summary.thread_count;

  assert.equal(run(""), 2);
  assert.equal(run("Bakhtawar"), 1, "the thread they replied in was dropped");
  assert.equal(run("ans.ahmad"), 2, "they took part in both");
  assert.equal(run("nobody at all"), 0);
});

test("the reviewer filter ignores case and matches an email", () => {
  const threads = {
    t1: { messages: [{ id: "m1", content: "x",
                       user: { name: "Someone", email: "SOMEONE@example.com" } }] },
  };
  const run = (reviewer) => core.assembleExport({
    projectId: "0123456789abcdef01234567", projectTitle: "P",
    rawThreads: threads, resolvedIds: [], rangesPayload: [],
    docTexts: {}, docIdToPath: {}, reviewer,
  }).payload.summary.thread_count;

  assert.equal(run("someone@example.com"), 1);
  assert.equal(run("SOMEONE"), 1);
});

// ---- Naming files and finding the root on today's Overleaf ---------------

test("the file name is read from the download's Content-Disposition", () => {
  const core = require("../src/export-core.js");
  assert.equal(core.fileNameFromDisposition('attachment; filename="main.tex"'), "main.tex");
  assert.equal(core.fileNameFromDisposition("attachment; filename=main.tex"), "main.tex");
  // The encoded form wins when both are sent, because it is the exact name.
  assert.equal(core.fileNameFromDisposition(
    "attachment; filename=\"r?sum?.tex\"; filename*=UTF-8''r%C3%A9sum%C3%A9.tex"), "résumé.tex");
  assert.equal(core.fileNameFromDisposition('attachment; filename="say \\"hi\\".tex"'), 'say "hi".tex');
  assert.equal(core.fileNameFromDisposition(""), null);
  assert.equal(core.fileNameFromDisposition(null), null);
});

test("a name is given its folder when only one path ends in it", () => {
  const core = require("../src/export-core.js");
  const placed = core.placeDocs(
    { a: "main.tex", b: "method.tex", c: "intro.tex", d: "intro.tex" },
    ["main.tex", "sections/method.tex", "sections/intro.tex", "appendix/intro.tex"],
  );
  assert.equal(placed.a, "main.tex");
  assert.equal(placed.b, "sections/method.tex");
  // Two files called intro.tex. Which id is which folder cannot be known from
  // here, so they are kept apart by id rather than merged or guessed.
  assert.notEqual(placed.c, placed.d);
  assert.match(placed.c, /^intro\.tex /);
  assert.match(placed.d, /^intro\.tex /);
});

test("with no list of paths, the bare name is kept", () => {
  const core = require("../src/export-core.js");
  assert.deepEqual(core.placeDocs({ a: "method.tex" }, []), { a: "method.tex" });
});

test("the root is the one complete document", () => {
  const core = require("../src/export-core.js");
  const doc = (cls, body = "") => `\\documentclass{${cls}}\n\\begin{document}\n${body}\\end{document}\n`;
  assert.equal(core.pickRootPath({
    "paper.tex": doc("article", "\\input{sec}\n"),
    "sec.tex": "\\section{A}\n",
  }), "paper.tex");

  // A figure built with standalone, and a chapter built with subfiles, both
  // look like complete documents and neither is the root.
  assert.equal(core.pickRootPath({
    "paper.tex": doc("acmart"),
    "figures/plot.tex": doc("standalone"),
    "chapters/one.tex": "\\documentclass[../paper.tex]{subfiles}\n\\begin{document}\nx\n\\end{document}\n",
  }), "paper.tex");

  // A commented-out class line is not a class line.
  assert.equal(core.pickRootPath({
    "notes.tex": "% \\documentclass{article}\n\\begin{document}\n",
    "real.tex": doc("article"),
  }), "real.tex");
});

test("with several complete documents, main.tex wins, then the one that pulls in most", () => {
  const core = require("../src/export-core.js");
  const doc = (body = "") => `\\documentclass{article}\n\\begin{document}\n${body}\\end{document}\n`;
  assert.equal(core.pickRootPath({ "main.tex": doc(), "letter.tex": doc() }), "main.tex");
  assert.equal(core.pickRootPath({
    "paper.tex": doc("\\input{a}\n\\input{b}\n"),
    "rebuttal.tex": doc(),
  }), "paper.tex");
  // A tie is left unresolved. No order is better than the wrong one.
  assert.equal(core.pickRootPath({ "x.tex": doc(), "y.tex": doc() }), null);
});

test("the version the export reports is the version in the manifest", () => {
  // Both version strings had drifted to 1.6.0 while 1.7.0 shipped.
  const core = require("../src/export-core.js");
  const manifest = require("../manifest.json");
  assert.equal(core.TOOL_VERSION, `${manifest.version}-extension`);
});

test("a comment on a position, with no anchored text, is not stale", () => {
  // Overleaf sends those with no text. On a real paper this flagged 120 of
  // 134 comments "⚠ stale" when not one of them had moved.
  const core = require("../src/export-core.js");
  const text = "\\section{A}\nTouch input is fast.\n";
  const starts = core.buildLineStarts(text);
  assert.equal(core.resolveAnchor(text, starts, 14, "").stale, false);
  assert.equal(core.resolveAnchor(text, starts, 14, null).stale, false);
  // Past the end is kept inside the text, and still not called stale.
  const far = core.resolveAnchor(text, starts, 9999, "");
  assert.equal(far.stale, false);
  assert.ok(far.offset < text.length);
  // Real anchors keep their meaning.
  assert.equal(core.resolveAnchor(text, starts, text.indexOf("fast"), "fast").stale, false);
  assert.equal(core.resolveAnchor(text, starts, 0, "gone for good").stale, true);
});

test("a spreadsheet holds only characters XML allows, and no cell Excel would refuse", () => {
  // A stray U+FFFE or U+FFFF left the sheet unreadable to Excel, and a cell
  // over 32,767 characters makes Excel offer a repair instead of opening it.
  const xlsx = require("../src/xlsx.js");
  const hostile = "bell\u0007 vtab\u000B noncharacter￾￿ and ]]> <&>";
  const bytes = xlsx.build({ comments: [["Comment"], [hostile], ["x".repeat(40000)]], replies: [["A"]], changes: [["A"]] });
  const text = Buffer.from(bytes).toString("latin1");
  const start = text.indexOf("<worksheet");
  const sheet = Buffer.from(text.slice(start, text.indexOf("</worksheet>", start) + 12), "latin1").toString("utf8");
  assert.doesNotMatch(sheet, /[^\t\n\r -퟿-�\u{10000}-\u{10FFFF}]/u, "a character XML forbids is still in the sheet");
  assert.match(sheet, /bell vtab noncharacter and \]\]&gt; &lt;&amp;&gt;/);
  const longest = Math.max(...[...sheet.matchAll(/<t xml:space="preserve">([^<]*)<\/t>/g)].map((m) => Array.from(m[1]).length));
  assert.equal(longest, 32767);
});
