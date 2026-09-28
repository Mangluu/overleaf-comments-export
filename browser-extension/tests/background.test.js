"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

function loadBackground(uiLanguage) {
  let registered = null;
  global.chrome = {
    runtime: {
      getManifest: () => ({ version: "9.9.9" }),
      setUninstallURL: (url) => { registered = url; },
    },
    i18n: { getUILanguage: () => uiLanguage },
  };
  delete require.cache[require.resolve("../background.js")];
  require("../background.js");
  return registered;
}

test("removing the extension opens the feedback page, carrying only version and language", () => {
  const url = new URL(loadBackground("en-GB"));
  assert.equal(`${url.origin}${url.pathname}`,
    "https://mangluu.github.io/overleaf-comments-export/uninstalled.html");
  assert.deepEqual([...url.searchParams.keys()].sort(), ["lang", "v"]);
  assert.equal(url.searchParams.get("v"), "9.9.9");
  assert.equal(url.searchParams.get("lang"), "en");
});

test("a Chinese browser gets the page in Chinese", () => {
  assert.equal(new URL(loadBackground("zh-CN")).searchParams.get("lang"), "zh");
  assert.equal(new URL(loadBackground("zh-TW")).searchParams.get("lang"), "zh");
});

test("the feedback page asks for no new permission", () => {
  // setUninstallURL needs none. A new permission would also mean a slower
  // review and a new warning when people update.
  const manifest = require("../manifest.json");
  assert.equal(manifest.background?.service_worker, "background.js");
  assert.deepEqual([...manifest.permissions].sort(), ["activeTab", "downloads", "scripting"]);
  assert.equal(manifest.host_permissions, undefined);
});

test("every file the manifest names is packed into the store zip", () => {
  // build-zip.sh lists what it packs by hand. A file the manifest points at
  // but the zip leaves out passes every other test and breaks on install.
  const manifest = require("../manifest.json");
  const script = fs.readFileSync(path.join(__dirname, "..", "..", "chrome-store", "build-zip.sh"), "utf8");
  const packed = script.slice(script.indexOf("zip -r"), script.indexOf("-x ")).split(/\s+/);
  const named = [
    manifest.background?.service_worker,
    manifest.action?.default_popup,
    ...Object.values(manifest.icons || {}),
  ].filter(Boolean);
  for (const file of named) {
    const top = file.split("/")[0];
    assert.ok(packed.includes(file) || packed.includes(top),
      `${file} is named in the manifest but build-zip.sh does not pack it`);
  }
});
