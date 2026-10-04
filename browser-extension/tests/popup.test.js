"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

// popup.js is a plain script that wires itself to the DOM as it loads, so the
// test gives it just enough of a document to get through. Same approach as
// page-client.test.js.
function loadPopup({ stored = null, choices = null } = {}) {
  const created = [];
  const element = () => ({
    hidden: false, disabled: false, checked: false, value: "", textContent: "",
    dataset: {}, classList: { toggle() {}, add() {}, remove() {} },
    children: [], append(...kids) { this.children.push(...kids); },
    addEventListener() {}, closest: () => null, setAttribute() {},
  });
  global.document = {
    documentElement: {},
    getElementById: () => element(),
    querySelectorAll: () => [],
    createElement: () => { const el = element(); created.push(el); return el; },
    addEventListener() {},
  };
  const store = {};
  global.localStorage = Object.assign(store, {
    getItem: (key) => (key.endsWith("choices") ? choices
      : key.startsWith("oce-snapshot-") ? (store[key] || null) : stored),
    setItem(key, value) { store[key] = value; },
    removeItem(key) { delete store[key]; },
  });
  global.chrome = {
    tabs: { query: () => {} }, scripting: {}, downloads: {},
    runtime: { onMessage: { addListener() {} }, sendMessage: async () => ({}) },
  };
  // navigator is deliberately not stubbed: popup.js must not consult it. It
  // used to, and switched itself to Chinese behind the reader's back.

  delete require.cache[require.resolve("../popup.js")];
  return { api: require("../popup.js"), created };
}

test("the interface is English unless the reader chose otherwise", () => {
  // It used to read navigator.language and switch itself to Chinese, which
  // surprised anyone whose browser was set that way but who wanted English.
  const { api } = loadPopup({ stored: null });
  assert.equal(api.DEFAULT_LANGUAGE, "en");
  assert.equal(api.resolveLanguage(null), "en");
});

test("a language the reader picked before is remembered", () => {
  const { api } = loadPopup({ stored: "zh" });
  assert.equal(api.resolveLanguage("zh"), "zh");
});

test("a stored language that no longer exists falls back to English", () => {
  const { api } = loadPopup({ stored: "kl" });
  assert.equal(api.resolveLanguage("kl"), "en");
  assert.equal(api.resolveLanguage(undefined), "en");
});

test("the dropdown is built from the copy, and English heads it", () => {
  const { api } = loadPopup();
  const choices = api.languageChoices();
  assert.deepEqual(choices.map((c) => c.code), ["en", "zh"]);
  assert.deepEqual(choices.map((c) => c.label), ["English", "中文"]);
});

test("every language names itself, or it cannot appear in the dropdown", () => {
  const { api } = loadPopup();
  for (const [code, copy] of Object.entries(api.COPY)) {
    assert.ok(copy.languageName, `${code} has no languageName`);
  }
});

test("every language defines every string, so none can fall back silently", () => {
  const { api } = loadPopup();
  const [reference, ...rest] = Object.keys(api.COPY);
  const expected = Object.keys(api.COPY[reference]).sort();
  for (const code of rest) {
    assert.deepEqual(Object.keys(api.COPY[code]).sort(), expected,
      `${code} does not have the same keys as ${reference}`);
  }
});

test("the markup is English and declares itself English", () => {
  // The document used to say lang="zh-CN" and carry Chinese fallback text, so
  // the popup flashed Chinese for everyone before the script ran.
  const html = fs.readFileSync(path.join(__dirname, "..", "popup.html"), "utf8");
  assert.match(html, /<html lang="en">/);
  assert.doesNotMatch(html, /[一-鿿]/, "Chinese text is left in the markup");
  assert.match(html, /id="language-select"/);
  assert.doesNotMatch(html, /flag-/, "the flag images are gone");
});

test("the boxes you ticked last time come back", () => {
  const { api } = loadPopup({
    choices: '{"format-jsonl":true,"format-md":false}',
  });
  const stored = api.readStoredChoices();
  assert.equal(stored["format-jsonl"], true);
  assert.equal(stored["format-md"], false);
});

test("a first run uses the defaults", () => {
  const { api } = loadPopup();
  assert.deepEqual(api.readStoredChoices(), {});
  assert.equal(api.CHOICE_DEFAULTS["format-md"], true);
  assert.equal(api.CHOICE_DEFAULTS["format-json"], true);
});

test("rubbish in storage is ignored rather than believed", () => {
  // Storage is editable by hand and survives version changes, so anything
  // that is not a boolean under a key we know about is dropped.
  for (const raw of ["not json at all", "[]", '{"format-md":"yes"}',
                     '{"made-up-key":true}']) {
    const { api } = loadPopup({ choices: raw });
    const stored = api.readStoredChoices();
    for (const [key, value] of Object.entries(stored)) {
      assert.ok(key in api.CHOICE_DEFAULTS, `kept an unknown key: ${key}`);
      assert.equal(typeof value, "boolean");
    }
  }
});

test("every remembered box exists in the markup", () => {
  // A default for a checkbox that is not there would never be applied and
  // never be noticed.
  const { api } = loadPopup();
  const html = fs.readFileSync(path.join(__dirname, "..", "popup.html"), "utf8");
  for (const id of Object.keys(api.CHOICE_DEFAULTS)) {
    assert.match(html, new RegExp(`id="${id}"`), `${id} is not in popup.html`);
  }
});

test("every new string exists in both languages", () => {
  // The progress and stop copy is the newest, and a missing key shows up as
  // an English sentence in the middle of a Chinese interface.
  const { api } = loadPopup();
  for (const key of ["stopButton", "stopping", "stopped", "progressFiles",
                     "progressIncludes", "progressBuilding"]) {
    for (const [code, copy] of Object.entries(api.COPY)) {
      assert.ok(copy[key], `${code} is missing ${key}`);
    }
  }
});

test("the progress copy has somewhere to put the numbers", () => {
  const { api } = loadPopup();
  for (const [code, copy] of Object.entries(api.COPY)) {
    assert.match(copy.progressFiles, /\{done\}/, `${code} progressFiles has no {done}`);
    assert.match(copy.progressFiles, /\{total\}/, `${code} progressFiles has no {total}`);
    assert.match(copy.progressIncludes, /\{total\}/, `${code} progressIncludes has no {total}`);
  }
});

test("the markup has the progress line and the stop button", () => {
  const html = fs.readFileSync(path.join(__dirname, "..", "popup.html"), "utf8");
  assert.match(html, /id="progress"/);
  assert.match(html, /id="stop"/);
  // Both start hidden: neither means anything before an export runs.
  assert.match(html, /id="progress"[^>]*hidden/);
  assert.match(html, /id="stop"[^>]*hidden/);
});

test("the result says where the files went", () => {
  // The first question after clicking Export, and the popup used to leave it
  // unanswered. There is no API to open the folder, so saying its name is
  // the most it can do.
  const { api } = loadPopup();
  for (const [code, copy] of Object.entries(api.COPY)) {
    assert.ok(copy.savedTo, `${code} has no savedTo`);
    assert.match(copy.savedTo, /\{folder\}/, `${code} savedTo has no {folder}`);
  }
});

// ---- The popup starts exports and shows them, nothing more ----------------

// Enough of a document and a Chrome to press the real buttons. Elements are
// kept by id so a test can reach the one the popup wired up.
async function drivePopup({ status = null, exportReply = { ok: true } } = {}) {
  const PID = "0123456789abcdef01234567";
  const byId = {};
  const element = () => ({
    hidden: false, disabled: false, checked: false, value: "", textContent: "",
    dataset: {}, classList: { toggle() {}, add() {}, remove() {} },
    listeners: {}, append() {},
    addEventListener(type, fn) { this.listeners[type] = fn; },
  });
  global.document = {
    documentElement: {},
    getElementById: (id) => (byId[id] ||= element()),
    querySelectorAll: () => [],
    createElement: () => element(),
  };
  const stored = {};
  global.localStorage = {
    getItem: (k) => (k in stored ? stored[k] : null),
    setItem: (k, v) => { stored[k] = String(v); },
    removeItem: (k) => { delete stored[k]; },
  };
  const sent = [];
  let onMessage = null;
  global.chrome = {
    runtime: {
      onMessage: { addListener: (fn) => { onMessage = fn; } },
      sendMessage: async (message) => {
        sent.push(message);
        if (message.type === "status") return status;
        if (message.type === "export") return exportReply;
        return { ok: true };
      },
    },
    tabs: { query: async () => [{ id: 7, url: `https://www.overleaf.com/project/${PID}`, title: "Paper" }] },
    // The popup must not need these any more. Touching them fails the test.
    get scripting() { throw new Error("the popup reached for chrome.scripting"); },
    get downloads() { throw new Error("the popup reached for chrome.downloads"); },
  };
  delete require.cache[require.resolve("../popup.js")];
  const api = require("../popup.js");
  for (let i = 0; i < 5; i += 1) await new Promise((r) => setImmediate(r));
  const news = (job, tabId = 7) => onMessage({ target: "popup", type: "job", tabId, job }, {});
  const progress = (p, tabId = 7) => onMessage({ oceProgress: p }, { tab: { id: tabId } });
  return { api, byId, sent, news, progress };
}

test("Export hands the export to the background and nothing else", async () => {
  // Nothing of the export lives here any more, so this popup can close at any
  // moment, to a stray click or a Save dialog, and lose nothing.
  const { byId, sent } = await drivePopup();
  await byId.export.listeners.click();
  const request = sent.find((m) => m.type === "export");
  assert.ok(request, "no export was asked for");
  assert.equal(request.target, "background");
  assert.equal(request.tabId, 7);
  assert.match(request.url, /\/project\/[0-9a-f]{24}$/);
  assert.equal(request.options.formats.markdown, true);
  assert.equal(byId.export.disabled, true, "the button can be pressed twice");
});

test("a popup opened during an export shows it running, with Stop", async () => {
  const { byId } = await drivePopup({ status: { state: "running", progress: { stage: "files", done: 2, total: 5 } } });
  assert.equal(byId.export.disabled, true);
  assert.equal(byId.stop.hidden, false);
  assert.match(byId.progress.textContent, /2 of 5/);
});

test("Stop asks the background to stop", async () => {
  const { byId, sent } = await drivePopup({ status: { state: "running" } });
  byId.stop.listeners.click();
  assert.ok(sent.some((m) => m.type === "stop" && m.tabId === 7));
  assert.match(byId.stop.textContent, /Stopping/);
});

test("a finished export is shown, and its Markdown can be copied", async () => {
  const { byId, news } = await drivePopup();
  news({ state: "done", summary: { threadCount: 3, openCount: 2, resolvedCount: 1, trackedChangeCount: 0 },
    files: 4, folder: "overleaf-comments/Paper/2026-10-04T10-00-00Z", warnings: [], markdown: "# Comments" });
  assert.match(byId.result.textContent, /3 discussions/);
  assert.match(byId.result.textContent, /overleaf-comments\/Paper/);
  assert.equal(byId.copy.hidden, false);
  assert.equal(byId.export.disabled, false);
});

test("a stopped export says it stopped, not that it failed", async () => {
  // It used to say "The export did not return a valid result."
  const { api, byId, news } = await drivePopup();
  news({ state: "stopped" });
  assert.equal(byId.result.textContent, api.COPY.en.stopped);
});

test("a failed export is worded, whether the page or the background said it", async () => {
  const { api, byId, news } = await drivePopup();
  news({ state: "failed", error: "This tab is not signed in to Overleaf. Sign in, reload the project, then try again." });
  assert.match(byId.result.textContent, /not signed in/);
  news({ state: "failed", error: "invalidResult" });
  assert.equal(byId.result.textContent, api.COPY.en.invalidResult);
  assert.equal(byId.copy.hidden, true);
});

test("news and progress about another tab are ignored", async () => {
  // Two papers can export at once, and every popup hears about both.
  const { byId, news, progress } = await drivePopup({ status: { state: "running" } });
  progress({ stage: "files", done: 1, total: 9 }, 8);
  assert.doesNotMatch(byId.progress.textContent, /1 of 9/);
  news({ state: "done", summary: {}, files: 1, folder: "x", markdown: "" }, 8);
  assert.equal(byId.export.disabled, true, "tab 8 finishing ended this tab's export on screen");
  progress({ stage: "files", done: 4, total: 9 }, 7);
  assert.match(byId.progress.textContent, /4 of 9/);
});
