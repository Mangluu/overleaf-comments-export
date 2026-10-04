"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

test("collects the current project through same-origin Overleaf endpoints", async () => {
  const projectId = "0123456789abcdef01234567";
  const docId = "doc-main";
  const source = "\\section{Method}\nAn adaptive interface.\n";
  const anchorOffset = source.indexOf("adaptive");
  const requests = [];

  global.OverleafCommentsCore = require("../src/export-core.js");
  global.location = { pathname: `/project/${projectId}` };
  global.document = {
    title: "Demo Project - Overleaf",
    querySelector(selector) {
      if (selector === 'meta[name="ol-project"]') {
        return {
          content: JSON.stringify({
            name: "Demo Project",
            rootFolder: { docs: [{ _id: docId, name: "main.tex" }], folders: [] },
          }),
        };
      }
      return null;
    },
  };
  global.fetch = async (path, options) => {
    requests.push({ path, options });
    if (path === `/project/${projectId}/threads`) {
      return new Response(JSON.stringify({
        thread1: {
          messages: [{
            id: "message-1",
            content: "Clarify this.",
            timestamp: 1_700_000_000_000,
            user_id: "reviewer-1",
            user: { name: "Reviewer" },
          }],
        },
      }), { status: 200, headers: { "content-type": "application/json" } });
    }
    if (path === `/project/${projectId}/resolved-thread-ids`) {
      return new Response(JSON.stringify([]), { status: 200, headers: { "content-type": "application/json" } });
    }
    if (path === `/project/${projectId}/ranges`) {
      return new Response(JSON.stringify({
        docs: [{
          id: docId,
          ranges: { comments: [{ op: { t: "thread1", p: anchorOffset, c: "adaptive" } }], changes: [] },
        }],
      }), { status: 200, headers: { "content-type": "application/json" } });
    }
    if (path === `/Project/${projectId}/doc/${docId}/download`) {
      return new Response(source, { status: 200, headers: { "content-type": "text/plain" } });
    }
    return new Response("not found", { status: 404 });
  };

  delete global.__overleafCommentsExtension;
  delete require.cache[require.resolve("../src/page-client.js")];
  require("../src/page-client.js");

  const result = await global.__overleafCommentsExtension.collect({
    language: "en",
    includeResolved: true,
    includeChanges: true,
    formats: { markdown: true, json: true, jsonl: false, responseLetter: false },
  });

  assert.equal(result.ok, true);
  assert.equal(result.project.title, "Demo Project");
  assert.equal(result.summary.threadCount, 1);
  assert.match(result.generatedAt, /^\d{4}-\d{2}-\d{2}T/);
  const names = result.outputs.map((output) => output.filename);
  assert.ok(names.some((name) => /^comments-\d{4}-\d{2}-\d{2}\.md$/.test(name)));
  assert.ok(names.includes("comments.json"));
  // The Markdown front matter names agents.md, so it has to be written.
  assert.ok(names.includes("agents.md"), `agents.md missing from ${names}`);
  assert.match(result.outputs[0].content, /Clarify this\./);
  assert.ok(requests.every((entry) => entry.options.credentials === "include"));

  const markdown = result.outputs[0].content;
  for (const key of ["file_count", "reviewer_count", "companion_json", "companion_agents"]) {
    assert.match(markdown, new RegExp(`^${key}:`, "m"), `front matter is missing ${key}`);
  }
});

test("asking it to stop stops it, and nothing is downloaded", async () => {
  // Before this the popup could only be closed, which left the page fetching
  // files nobody would ever see the results of.
  global.OverleafCommentsCore = require("../src/export-core.js");
  global.location = { pathname: "/project/0123456789abcdef01234567" };
  global.document = {
    title: "Demo - Overleaf",
    querySelector: () => null,
  };
  let asked = 0;
  global.chrome = {
    runtime: {
      sendMessage: async (message) => {
        if (message?.oceStopCheck) {
          asked += 1;
          return { stop: true };        // the reader pressed Stop
        }
        return {};
      },
    },
  };
  global.fetch = async () => ({
    ok: true, status: 200,
    headers: { get: () => "application/json" },
    json: async () => ({}),
    text: async () => "",
  });

  delete require.cache[require.resolve("../src/page-client.js")];
  require("../src/page-client.js");
  const { collect } = globalThis.__overleafCommentsExtension;
  const result = await collect({ language: "en", formats: {} });

  assert.ok(asked > 0, "it never asked whether to stop");
  assert.equal(result.ok, false, "it produced a result after being told to stop");
  assert.equal(result.stopped, true, "a stop has to say it was a stop, or it reads as a failure");
});

test("a signed-out tab is told so, not told Overleaf refused it", async () => {
  // 401 means nobody is signed in; 403 means signed in without access to this
  // project. Reporting both as "Overleaf rejected the request" sent people
  // looking for a permissions problem that was not there.
  global.OverleafCommentsCore = require("../src/export-core.js");
  global.location = { pathname: "/project/0123456789abcdef01234567" };
  global.document = { title: "Demo - Overleaf", querySelector: () => null };
  global.chrome = { runtime: { sendMessage: async () => ({ stop: false }) } };
  global.fetch = async () => ({
    ok: false, status: 401,
    headers: { get: () => "application/json" },
    json: async () => ({}), text: async () => "",
  });

  delete global.__overleafCommentsExtension;
  delete require.cache[require.resolve("../src/page-client.js")];
  require("../src/page-client.js");
  const result = await global.__overleafCommentsExtension.collect({ language: "en", formats: {} });

  assert.equal(result.ok, false, "a signed-out tab exported anyway");
  assert.equal(result.status, 401);
  assert.match(result.error, /not signed in/i, `got: ${result.error}`);
  assert.doesNotMatch(result.error, /rejected the request/i);
});

test("collect never throws, because Chrome would lose what it threw", async () => {
  // Anything thrown inside an injected script reaches the extension as a null
  // result. Every failure has to come back as data, or the reader is told only
  // that the export "did not return a valid result".
  global.OverleafCommentsCore = require("../src/export-core.js");
  global.location = { pathname: "/project/0123456789abcdef01234567" };
  global.document = { title: "Demo - Overleaf", querySelector: () => null };
  global.chrome = { runtime: { sendMessage: async () => ({ stop: false }) } };
  delete global.__overleafCommentsExtension;
  delete require.cache[require.resolve("../src/page-client.js")];
  require("../src/page-client.js");
  const { collect } = global.__overleafCommentsExtension;

  for (const [why, fetchImpl] of [
    ["the network is down", async () => { throw new TypeError("Failed to fetch"); }],
    ["access is refused", async () => new Response("", { status: 403 })],
    ["the reply is not JSON", async () => new Response("<html>", { status: 200 })],
    ["the server errors", async () => new Response("", { status: 500 })],
  ]) {
    global.fetch = fetchImpl;
    let result;
    await assert.doesNotReject(async () => { result = await collect({ language: "en", formats: {} }); }, why);
    assert.equal(result.ok, false, why);
    assert.ok(result.error && result.error !== "undefined", `${why}: no words for the reader`);
  }
});

// ---- Against the Overleaf that exists today ------------------------------
//
// Everything above fakes an `ol-project` meta tag carrying the file tree and
// the root document. overleaf.com stopped emitting that tag. The editor
// template, services/web/app/views/project/editor/_meta.pug, emits 55 tags and
// none of them is a file tree. So in the real world every export filed its
// comments under `<unknown-6a7a…>` and warned about it, and document order
// never ran. These tests fake only what the site really serves.
//
// They also send collect() exactly what popup.js readOptions() builds. The
// test above never ticked Spreadsheet, never narrowed the export and never
// passed a previous export, which is how all four were dropped on the floor
// in 1.7.0 while every test stayed green.

const PROJECT = "0123456789abcdef01234567";

function todaysOverleaf({ docs, threads, openDocId = null, entities = "ok", leftOver = null }) {
  const requests = [];
  global.OverleafCommentsCore = require("../src/export-core.js");
  global.OverleafCommentsXlsx = require("../src/xlsx.js");
  global.location = { pathname: `/project/${PROJECT}` };
  // The file list marks the open document with aria-selected, and the
  // element carrying data-file-id is the first thing inside that item.
  const selectedItems = openDocId
    ? [{ querySelector: () => ({ getAttribute: (n) => ({ "data-file-id": openDocId, "data-file-type": "doc" })[n] }) }]
    : [];
  global.document = {
    title: "Touch Paper - Overleaf",
    querySelector(selector) {
      if (selector === 'meta[name="ol-projectName"]') return { content: "Touch Paper" };
      if (selector === 'meta[name="ol-user"]') return { content: JSON.stringify({ id: "u1", email: "me@uni.edu" }) };
      return null;
    },
    querySelectorAll: (selector) => (/aria-selected="true"/.test(selector) ? selectedItems : []),
  };
  delete global.chrome;
  global.fetch = async (url) => {
    requests.push(url);
    const json = (body) => new Response(JSON.stringify(body), {
      status: 200, headers: { "content-type": "application/json" } });
    if (url === `/project/${PROJECT}/threads`) return json(threads);
    if (url === `/project/${PROJECT}/resolved-thread-ids`) return json([]);
    // A list, one entry per document in the project whether or not it has
    // anything in it, which is what docstore's getAllRanges returns.
    if (url === `/project/${PROJECT}/ranges`) {
      return json(docs.map((doc) => ({
        _id: doc.id,
        ranges: {
          comments: (doc.comments || []).map(({ thread, on }) => ({ op: { t: thread, p: doc.text.indexOf(on), c: on } })),
          changes: [],
        },
      })));
    }
    if (url === `/project/${PROJECT}/entities`) {
      if (entities !== "ok") return new Response("", { status: 500 });
      return json({ project_id: PROJECT, entities: docs.map((doc) => ({ path: `/${doc.path}`, type: "doc" })) });
    }
    const download = url.match(/^\/Project\/[0-9a-f]{24}\/doc\/([^/]+)\/download$/);
    const doc = download && docs.find((d) => d.id === decodeURIComponent(download[1]));
    if (doc) {
      // DocumentUpdaterController.getDoc names the file in this header.
      return new Response(doc.text, { status: 200, headers: {
        "content-disposition": `attachment; filename="${doc.path.split("/").pop()}"` } });
    }
    return new Response("not found", { status: 404 });
  };
  // Whatever an earlier injection left behind in this tab's isolated world.
  if (leftOver) global.__overleafCommentsExtension = leftOver;
  else delete global.__overleafCommentsExtension;
  delete require.cache[require.resolve("../src/page-client.js")];
  require("../src/page-client.js");
  return { collect: global.__overleafCommentsExtension.collect, requests };
}

const person = (first, email) => ({ first_name: first, last_name: "", email });
const thread = (id, first, email, text) => ({
  messages: [{ id: `${id}-m`, content: text, timestamp: 1_700_000_000_000, user_id: first, user: person(first, email) }],
});

// A two-file paper, a comment in each. The root has the first figure and
// pulls in a section holding the second, and a bibliography sits alongside.
const MAIN = "6a7a28412a1b2c3d4e5f6071";
const METHOD = "6a7a28412a1b2c3d4e5f6082";
const REFS = "6a7a28412a1b2c3d4e5f6093";
const twoFilePaper = () => [
  {
    id: MAIN, path: "main.tex",
    text: "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nTouch input is fast.\n"
      + "\\begin{figure}\\caption{First}\\label{fig:a}\\end{figure}\n\\input{sections/method}\n\\end{document}\n",
    comments: [{ thread: "t1", on: "Touch input" }],
  },
  {
    id: METHOD, path: "sections/method.tex",
    text: "\\section{Method}\n\\begin{figure}\nWe ran twelve people.\n\\caption{Second}\\label{fig:b}\n\\end{figure}\n",
    comments: [{ thread: "t2", on: "twelve" }],
  },
  { id: REFS, path: "refs.bib", text: "@article{a, title={A}}\n" },
];
const twoThreads = () => ({
  t1: thread("t1", "Ana", "ana@uni.edu", "Cite something here."),
  t2: thread("t2", "Ben", "ben@uni.edu", "How many participants?"),
});

// Byte for byte what popup.js readOptions() builds, before the click handler
// adds a previous export.
const fromPopup = (overrides = {}) => ({
  language: "en", includeResolved: true, includeChanges: true,
  currentFileOnly: false, reviewer: "",
  formats: { markdown: true, json: true, jsonl: false, xlsx: false, responseLetter: false },
  ...overrides,
});

test("on today's Overleaf, comments are filed under their real file names", async () => {
  const { collect } = todaysOverleaf({ docs: twoFilePaper(), threads: twoThreads() });
  const result = await collect(fromPopup());
  const markdown = result.outputs.find((o) => /^comments-.*\.md$/.test(o.filename)).content;

  assert.doesNotMatch(markdown, /<unknown-/, "a file is still named by its document id");
  assert.match(markdown, /^## main\.tex$/m);
  assert.match(markdown, /^## sections\/method\.tex$/m);
  assert.deepEqual(result.warnings, [], `warned anyway: ${result.warnings}`);
});

test("a paper in several files is numbered in document order", async () => {
  // Figure "Second" is the second figure in the paper. Counted file by file
  // it is the first, which sends the reader to the wrong figure.
  // The root carries no comment here, so nothing but the new reading of the
  // whole paper can bring it in.
  const docs = twoFilePaper().map((doc) => (doc.id === MAIN ? { ...doc, comments: [] } : doc));
  const { collect, requests } = todaysOverleaf({ docs, threads: { t2: twoThreads().t2 } });
  const result = await collect(fromPopup());
  const payload = JSON.parse(result.outputs.find((o) => o.filename === "comments.json").content);
  const inMethod = payload.comments.find((c) => c.thread_id === "t2");

  assert.ok(requests.some((url) => url.includes(`/doc/${MAIN}/download`)), "the root was never read");

  assert.equal(inMethod.enclosing_float?.number, 2, JSON.stringify(inMethod.enclosing_float));
  assert.equal(inMethod.enclosing_float?.caption, "Second");
});

test("a spreadsheet is written when Spreadsheet is ticked", async () => {
  const { collect } = todaysOverleaf({ docs: twoFilePaper(), threads: twoThreads() });
  const result = await collect(fromPopup({
    formats: { markdown: true, json: false, jsonl: false, xlsx: true, responseLetter: false },
  }));
  const sheet = result.outputs.find((o) => o.filename === "comments.xlsx");

  assert.ok(sheet, `no spreadsheet among ${result.outputs.map((o) => o.filename)}`);
  assert.equal(Buffer.from(sheet.base64, "base64").subarray(0, 2).toString(), "PK", "not a zip");
});

test("One person keeps only the threads that person took part in", async () => {
  const { collect } = todaysOverleaf({ docs: twoFilePaper(), threads: twoThreads() });
  const result = await collect(fromPopup({ reviewer: "ana" }));
  const markdown = result.outputs[0].content;

  assert.match(markdown, /Cite something here\./);
  assert.doesNotMatch(markdown, /How many participants\?/, "Ben's thread came through the filter");
  assert.equal(result.summary.threadCount, 1);
});

test("This file only keeps the file open in the editor", async () => {
  const { collect } = todaysOverleaf({ docs: twoFilePaper(), threads: twoThreads(), openDocId: METHOD });
  const result = await collect(fromPopup({ currentFileOnly: true }));
  const markdown = result.outputs[0].content;

  assert.match(markdown, /How many participants\?/);
  assert.doesNotMatch(markdown, /Cite something here\./, "a comment from another file came through");
});

test("This file only says so when it cannot tell which file is open", async () => {
  // Quietly exporting the whole paper instead is exactly the bug this replaces.
  const { collect } = todaysOverleaf({ docs: twoFilePaper(), threads: twoThreads(), openDocId: null });
  const result = await collect(fromPopup({ currentFileOnly: true }));

  assert.equal(result.ok, false);
  assert.match(result.error, /which file is open/i);
});

test("a second export says what changed since the first", async () => {
  // The popup stores result.snapshot and hands it back next time.
  const { collect } = todaysOverleaf({ docs: twoFilePaper(), threads: twoThreads() });
  const first = await collect(fromPopup());
  const second = await collect(fromPopup({ previousSnapshot: first.snapshot }));

  assert.ok(second.outputs.some((o) => o.filename === "whats-new.md"),
    `no whats-new.md among ${second.outputs.map((o) => o.filename)}`);
});

test("names still come through when the list of paths is unavailable", async () => {
  // The download names the file even without its folder. A bare name is
  // still far more use than a document id.
  const { collect } = todaysOverleaf({ docs: twoFilePaper(), threads: twoThreads(), entities: "broken" });
  const result = await collect(fromPopup());
  const markdown = result.outputs[0].content;

  assert.doesNotMatch(markdown, /<unknown-/);
  assert.match(markdown, /^## method\.tex$/m);
});

test("code injected by an older version never answers for a newer one", async () => {
  // A version guard used to skip redefining the client when the version
  // string matched, and the string had not been bumped since 1.6.0. So after
  // an update, a tab could keep running the old collect().
  const { collect } = todaysOverleaf({
    docs: twoFilePaper(), threads: twoThreads(),
    leftOver: { version: "1.6.0", collect: () => "stale" },
  });
  const result = await collect(fromPopup());
  assert.notEqual(result, "stale");
  assert.equal(result.ok, true);
});
