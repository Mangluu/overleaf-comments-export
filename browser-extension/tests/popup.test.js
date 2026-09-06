"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

// popup.js is a plain script that wires itself to the DOM as it loads, so the
// test gives it just enough of a document to get through. Same approach as
// page-client.test.js.
function loadPopup({ stored = null } = {}) {
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
  global.localStorage = {
    getItem: () => stored,
    setItem() {},
  };
  global.chrome = { tabs: { query: () => {} }, scripting: {}, downloads: {} };
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
