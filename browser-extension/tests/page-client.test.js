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
  assert.equal(result.outputs.length, 2);
  assert.match(result.outputs[0].content, /Clarify this\./);
  assert.ok(requests.every((entry) => entry.options.credentials === "include"));
});
