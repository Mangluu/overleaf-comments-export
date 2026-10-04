"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

function loadOffscreen(seed = {}) {
  const store = { ...seed };
  global.localStorage = Object.assign(Object.create(null), {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
  });
  global.chrome = undefined;
  delete require.cache[require.resolve("../offscreen.js")];
  return { api: require("../offscreen.js"), store };
}

test("a snapshot is kept per paper, and read back", () => {
  const { api, store } = loadOffscreen();
  api.saveSnapshot("p1", { pulled_at: "2026-10-04T10:00:00Z", threads: { t1: {} } });
  assert.ok(store["oce-snapshot-p1"]);
  assert.deepEqual(api.loadSnapshot("p1"), { pulled_at: "2026-10-04T10:00:00Z", threads: { t1: {} } });
});

test("a missing or unreadable snapshot is no snapshot, not a crash", () => {
  // Storage is hand-editable and outlives version changes, so anything in it
  // has to be treated as untrusted. A failed diff must never fail an export.
  const { api } = loadOffscreen({ "oce-snapshot-bad": "{not json" });
  assert.equal(api.loadSnapshot("nothing-stored-here"), null);
  assert.equal(api.loadSnapshot("bad"), null);
});

test("snapshots saved by the popup before the move are still found", () => {
  // Same extension, same localStorage, same key. Nobody loses their baseline.
  const { api } = loadOffscreen({ "oce-snapshot-p9": JSON.stringify({ pulled_at: "2026-09-01T00:00:00Z" }) });
  assert.equal(api.loadSnapshot("p9").pulled_at, "2026-09-01T00:00:00Z");
});

test("a spreadsheet comes out of its blob byte for byte", async () => {
  const { api } = loadOffscreen();
  const bytes = Buffer.from([0x50, 0x4b, 0x03, 0x04, 0x00, 0xff, 0x80]);
  const url = api.blobUrl({ base64: bytes.toString("base64"), mimeType: "application/zip" });
  const { resolveObjectURL } = require("node:buffer");
  const back = Buffer.from(await resolveObjectURL(url).arrayBuffer());
  assert.deepEqual(back, bytes);
});

test("text keeps its characters through the blob", async () => {
  const { api } = loadOffscreen();
  const content = "Résumé, 中文, \u{1F9EA}, and a quote “like this”\n";
  const url = api.blobUrl({ content, mimeType: "text/markdown;charset=utf-8" });
  const { resolveObjectURL } = require("node:buffer");
  assert.equal(await resolveObjectURL(url).text(), content);
});
