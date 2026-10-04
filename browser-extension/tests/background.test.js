"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const PID = "0123456789abcdef01234567";
const PROJECT_URL = `https://www.overleaf.com/project/${PID}`;
const TAB = 7;

const settle = () => new Promise((resolve) => setImmediate(resolve));
async function until(check, ticks = 200) {
  for (let i = 0; i < ticks && !check(); i += 1) await settle();
  return check();
}

// A Chrome as Chromium behaves. The one detail that matters most: anything
// thrown inside an injected script comes back as a null result, never as a
// rejection (ProgrammaticScriptInjector::OnInjectionComplete). A real browser
// showed exactly that on 4 October 2026.
function loadBackground({ page = async () => okResult(), uiLanguage = "en-GB", downloadsGate = null } = {}) {
  const store = {};
  global.localStorage = {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
  };
  for (const k of Object.keys(require.cache)) if (/offscreen\.js$|background\.js$/.test(k)) delete require.cache[k];
  global.chrome = undefined;
  const offscreen = require("../offscreen.js");

  const world = {
    uninstallUrl: null, listener: null, popupNews: [], downloads: [], badges: {},
    offscreenOpen: false, offscreenOpened: 0, offscreenClosed: 0, injected: 0, store,
  };
  const fromPage = (message) => new Promise((resolve) => {
    let replied = false;
    const keepOpen = world.listener(message, { tab: { id: TAB } }, (answer) => { replied = true; resolve(answer); });
    if (!replied && !keepOpen) resolve(undefined);
  });
  world.page = { stopCheck: () => fromPage({ oceStopCheck: true }), progress: (p) => fromPage({ oceProgress: p }) };

  global.chrome = {
    runtime: {
      getManifest: () => ({ version: "9.9.9" }),
      setUninstallURL: (url) => { world.uninstallUrl = url; },
      onMessage: { addListener: (fn) => { world.listener = fn; } },
      getContexts: async () => (world.offscreenOpen ? [{ contextType: "OFFSCREEN_DOCUMENT" }] : []),
      sendMessage: async (message) => {
        if (message.target === "offscreen") {
          assert.ok(world.offscreenOpen, `offscreen used while closed: ${message.type}`);
          if (message.type === "blobs") return message.files.map(offscreen.blobUrl);
          if (message.type === "loadSnapshot") return offscreen.loadSnapshot(message.projectId);
          if (message.type === "saveSnapshot") return offscreen.saveSnapshot(message.projectId, message.snapshot) ?? true;
        }
        if (message.target === "popup") {
          world.popupNews.push(message);
          throw new Error("Could not establish connection. Receiving end does not exist.");
        }
        throw new Error(`unexpected message ${JSON.stringify(message)}`);
      },
    },
    i18n: { getUILanguage: () => uiLanguage },
    offscreen: {
      createDocument: async (options) => {
        assert.ok(!world.offscreenOpen, "a second offscreen document");
        assert.deepEqual([...options.reasons].sort(), ["BLOBS", "LOCAL_STORAGE"]);
        world.offscreenOpen = true; world.offscreenOpened += 1;
      },
      closeDocument: async () => {
        if (!world.offscreenOpen) throw new Error("No current offscreen document.");
        world.offscreenOpen = false; world.offscreenClosed += 1;
      },
    },
    scripting: {
      executeScript: async ({ files, func, args }) => {
        if (files) { world.injected += 1; return [{ result: null }]; }
        globalThis.__overleafCommentsExtension = { collect: (options) => page(options, world) };
        try {
          return [{ result: await func(...args) }];
        } catch {
          return [{ result: null }];              // what Chromium does with a throw
        } finally {
          delete globalThis.__overleafCommentsExtension;
        }
      },
    },
    downloads: {
      download: (options) => {
        world.downloads.push(options);
        return downloadsGate ? downloadsGate.then(() => world.downloads.length) : Promise.resolve(world.downloads.length);
      },
    },
    action: {
      setBadgeText: async ({ tabId, text }) => { world.badges[tabId] = text; },
      setBadgeBackgroundColor: async () => {},
    },
  };
  const api = require("../background.js");
  world.ask = (message) => new Promise((resolve) => {
    let replied = false;
    world.listener({ target: "background", tabId: TAB, url: PROJECT_URL, ...message }, {}, (answer) => { replied = true; resolve(answer); });
    if (!replied) resolve(undefined);
  });
  return { api, world };
}

function okResult(extra = {}) {
  return {
    ok: true, project: { title: "Does It Matter How You Touch?" }, generatedAt: "2026-10-04T10:00:00Z",
    summary: { threadCount: 2, openCount: 2, resolvedCount: 0, trackedChangeCount: 0 },
    warnings: [], snapshot: { pulled_at: "2026-10-04T10:00:00Z", threads: {} },
    outputs: [
      { filename: "comments-2026-10-04.md", mimeType: "text/markdown;charset=utf-8", content: "# Comments" },
      { filename: "comments.json", mimeType: "application/json;charset=utf-8", content: "{}" },
      { filename: "comments.xlsx", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", base64: Buffer.from("PK\u0003\u0004").toString("base64") },
      { filename: "agents.md", mimeType: "text/markdown;charset=utf-8", content: "brief" },
    ],
    ...extra,
  };
}

// ---- The uninstall page ---------------------------------------------------

test("removing the extension opens the feedback page, carrying only version and language", () => {
  const url = new URL(loadBackground().world.uninstallUrl);
  assert.equal(`${url.origin}${url.pathname}`, "https://mangluu.github.io/overleaf-comments-export/uninstalled.html");
  assert.deepEqual([...url.searchParams.keys()].sort(), ["lang", "v"]);
  assert.equal(url.searchParams.get("v"), "9.9.9");
  assert.equal(url.searchParams.get("lang"), "en");
});

test("a Chinese browser gets the page in Chinese", () => {
  assert.equal(new URL(loadBackground({ uiLanguage: "zh-CN" }).world.uninstallUrl).searchParams.get("lang"), "zh");
  assert.equal(new URL(loadBackground({ uiLanguage: "zh-TW" }).world.uninstallUrl).searchParams.get("lang"), "zh");
});

test("the permissions are the ones the listing explains, and no host access", () => {
  // offscreen is the only addition. It shows no warning at install or update,
  // and it is how a service worker gets blob URLs and the popup's storage.
  const manifest = require("../manifest.json");
  assert.equal(manifest.background?.service_worker, "background.js");
  assert.deepEqual([...manifest.permissions].sort(), ["activeTab", "downloads", "offscreen", "scripting"]);
  assert.equal(manifest.host_permissions, undefined);
  assert.ok(Number(manifest.minimum_chrome_version) >= 116, "getContexts needs Chrome 116");
});

test("every page and script the extension loads is packed into the store zip", () => {
  // build-zip.sh lists what it packs by hand. A file the extension loads but
  // the zip leaves out passes every other test and breaks on install.
  const root = path.join(__dirname, "..");
  const manifest = require("../manifest.json");
  const script = fs.readFileSync(path.join(root, "..", "chrome-store", "build-zip.sh"), "utf8");
  const packed = script.slice(script.indexOf("zip -r"), script.indexOf("-x ")).split(/\s+/);
  const background = fs.readFileSync(path.join(root, "background.js"), "utf8");
  const pages = [manifest.action.default_popup, ...background.matchAll(/url: "([^"]+\.html)"/g)].map((p) => (Array.isArray(p) ? p[1] : p));
  const loaded = [
    manifest.background.service_worker,
    ...Object.values(manifest.icons),
    ...pages,
    ...pages.flatMap((page) => [...fs.readFileSync(path.join(root, page), "utf8").matchAll(/<script src="([^"]+)"/g)].map((m) => m[1])),
    ...JSON.parse(background.match(/INJECTED_FILES = (\[[^\]]+\])/)[1]),
  ];
  assert.ok(pages.includes("offscreen.html"), "the offscreen page was not found in background.js");
  for (const file of loaded) {
    assert.ok(packed.includes(file) || packed.includes(file.split("/")[0]),
      `${file} is loaded by the extension but build-zip.sh does not pack it`);
  }
});

// ---- The export runs here, whatever happens to the popup -------------------

test("an export finishes with no popup open at all", async () => {
  // The whole point. Every broadcast to the popup fails, as it does once the
  // popup has closed, and the files are written anyway.
  const { world } = loadBackground();
  assert.deepEqual(await world.ask({ type: "export", options: { language: "en" } }), { ok: true });
  assert.ok(await until(() => world.downloads.length === 4), `only ${world.downloads.length} of 4 files`);
  await until(() => world.popupNews.at(-1)?.job.state === "done");
  assert.equal(world.popupNews.at(-1).job.state, "done");
  assert.deepEqual(world.downloads.map((d) => d.filename.split("/").pop()),
    ["comments-2026-10-04.md", "comments.json", "comments.xlsx", "agents.md"]);
  assert.ok(world.downloads.every((d) => d.filename.startsWith("overleaf-comments/Does It Matter How You Touch-/2026-10-04T10-00-00Z/")));
  assert.ok(world.downloads.every((d) => d.saveAs === false && d.url.startsWith("blob:")));
  assert.ok(world.store[`oce-snapshot-${PID}`], "the snapshot was not kept");
  assert.equal(world.offscreenOpen, false, "the offscreen page was left open");
});

test("every file is requested before any of them has settled", async () => {
  // Chrome opens a Save dialog per file when it asks where to save each one.
  // They should all be queued before the first is answered.
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const { world } = loadBackground({ downloadsGate: gate });
  await world.ask({ type: "export", options: {} });
  await until(() => world.downloads.length > 0);
  await settle();
  assert.equal(world.downloads.length, 4);
  assert.equal(world.store[`oce-snapshot-${PID}`], undefined, "the baseline moved before the files were on their way");
  release();
  await until(() => world.popupNews.at(-1)?.job.state === "done");
  assert.ok(world.store[`oce-snapshot-${PID}`]);
});

test("the next export is handed the last one, to say what changed", async () => {
  let seen;
  const { world } = loadBackground({ page: async (options) => { seen = options.previousSnapshot; return okResult(); } });
  await world.ask({ type: "export", options: {} });
  await until(() => world.popupNews.at(-1)?.job.state === "done");
  assert.equal(seen, null, "a first export has nothing to compare with");
  await world.ask({ type: "export", options: {} });
  await until(() => world.popupNews.filter((n) => n.job.state === "done").length === 2);
  assert.deepEqual(seen, okResult().snapshot);
});

test("a failure in the page reaches the reader in its own words", async () => {
  const { world } = loadBackground({
    page: async () => ({ ok: false, error: "This tab is not signed in to Overleaf. Sign in, reload the project, then try again.", status: 401 }),
  });
  await world.ask({ type: "export", options: {} });
  await until(() => world.popupNews.at(-1)?.job.state === "failed");
  assert.match(world.popupNews.at(-1).job.error, /not signed in/);
  assert.equal(world.downloads.length, 0);
  assert.equal(world.badges[TAB], "!", "nothing says it failed once the popup is closed");
  assert.equal(world.store[`oce-snapshot-${PID}`], undefined);
});

test("a page script that throws is reported, not left hanging", async () => {
  // Chromium turns the throw into a null result. That has a code the popup
  // words, not a blank.
  const { world } = loadBackground({ page: async () => { throw new Error("boom"); } });
  await world.ask({ type: "export", options: {} });
  await until(() => world.popupNews.at(-1)?.job.state === "failed");
  assert.equal(world.popupNews.at(-1).job.error, "invalidResult");
});

test("Stop is answered by the background, and the export says it stopped", async () => {
  let asked;
  const { world } = loadBackground({
    page: async (_options, w) => {
      await until(() => asked);                   // wait for the reader to press Stop
      const answer = await w.page.stopCheck();
      return answer.stop ? { ok: false, error: "stopped", stopped: true } : okResult();
    },
  });
  await world.ask({ type: "export", options: {} });
  assert.deepEqual(await world.page.stopCheck(), { stop: false });
  await world.ask({ type: "stop" });
  asked = true;
  await until(() => world.popupNews.at(-1)?.job.state === "stopped");
  assert.equal(world.popupNews.at(-1).job.state, "stopped");
  assert.equal(world.downloads.length, 0);
});

test("a stop check from a tab with no export says stop", async () => {
  // This worker restarted and the export it belonged to is gone.
  const { world } = loadBackground();
  assert.deepEqual(await world.page.stopCheck(), { stop: true });
});

test("a second export of the same tab is not started on top of the first", async () => {
  let finish;
  const { world } = loadBackground({ page: () => new Promise((resolve) => { finish = () => resolve(okResult()); }) });
  assert.deepEqual(await world.ask({ type: "export", options: {} }), { ok: true });
  await until(() => finish);
  const again = await world.ask({ type: "export", options: {} });
  assert.equal(again.ok, false);
  assert.equal(again.job.state, "running");
  finish();
  await until(() => world.popupNews.at(-1)?.job.state === "done");
  assert.equal(world.offscreenOpened, 1);
});

test("a popup reopened mid-export sees its progress", async () => {
  let finish;
  const { world } = loadBackground({
    page: async (_o, w) => {
      await w.page.progress({ stage: "files", done: 3, total: 9 });
      return new Promise((resolve) => { finish = () => resolve(okResult()); });
    },
  });
  await world.ask({ type: "export", options: {} });
  await until(() => finish);
  const status = await world.ask({ type: "status" });
  assert.equal(status.state, "running");
  assert.deepEqual(status.progress, { stage: "files", done: 3, total: 9 });
  finish();
  await until(() => world.popupNews.at(-1)?.job.state === "done");
});

test("a tab that has moved on to another paper shows nothing from the last one", async () => {
  const { world } = loadBackground();
  await world.ask({ type: "export", options: {} });
  await until(() => world.popupNews.at(-1)?.job.state === "done");
  assert.equal((await world.ask({ type: "status" })).state, "done");
  assert.equal(await world.ask({ type: "status", url: "https://www.overleaf.com/project/fedcba9876543210fedcba98" }), null);
});

test("two papers exporting at once share one offscreen page, closed after both", async () => {
  const finishers = [];
  const { world } = loadBackground({ page: () => new Promise((resolve) => finishers.push(() => resolve(okResult()))) });
  await world.ask({ type: "export", options: {} });
  await world.ask({ type: "export", tabId: 8, url: PROJECT_URL.replace(PID, "fedcba9876543210fedcba98"), options: {} });
  await until(() => finishers.length === 2);
  assert.equal(world.offscreenOpened, 1);
  finishers[0]();
  await until(() => world.popupNews.filter((n) => n.job.state === "done").length === 1);
  await settle();
  assert.equal(world.offscreenOpen, true, "closed while the other export still needed it");
  finishers[1]();
  await until(() => world.popupNews.filter((n) => n.job.state === "done").length === 2);
  await until(() => !world.offscreenOpen);
  assert.equal(world.offscreenOpen, false, "left open after both had finished");
  assert.equal(world.offscreenOpened, 1);
});

// ---- Names Chrome will accept ----------------------------------------------

// Chromium's own rule, transcribed separately from the code under test, from
// IsSafePortablePathComponent in net/base/filename_util_icu.cc and the
// helpers it calls. Windows-only checks are included, since Windows is where
// most of the installs are.
function chromeAccepts(name) {
  if (!name) return false;
  if (/["*/:<>?\\|\p{Cc}\p{Cf}\p{Noncharacter_Code_Point}]/u.test(name)) return false;   // IsFilenameLegal
  const ends = /^[\s.~]|[\s.~]$/u;                                                         // illegal at either end
  if (ends.test(name)) return false;
  if (/^[^\s"\\/[\]:+|<>=;?,*]{1,12}$/u.test(name) && name.includes("~")) {                // VFAT short name
    const dot = name.indexOf(".");
    if (dot === -1 ? name.length <= 8 : dot === name.lastIndexOf(".") && dot > 0 && dot <= 8 && dot + 4 >= name.length) return false;
  }
  const ext = name.includes(".") ? name.slice(name.lastIndexOf(".") + 1).toLowerCase() : "";
  if (["local", "lnk", "scf", "url"].includes(ext) || /^\{.*\}$/.test(ext)) return false;  // IsShellIntegratedExtension
  const trimmed = name.toLowerCase().replace(/[ .]+$/, "");                                 // IsReservedNameOnWindows
  const stem = trimmed.split(".")[0];
  if (/^(con|prn|aux|nul|com[1-9]|lpt[1-9]|clock\$)$/.test(stem)) return false;
  if (["desktop.ini", "thumbs.db", "conin$", "conout$"].includes(trimmed)) return false;
  return true;
}

const TITLES = [
  "Does It Matter How You Touch?",
  "A".repeat(89) + " long academic title",                // cut lands on a space
  "Lab notes \u{1F469}‍\u{1F52C}",                     // emoji built with a zero-width joiner
  "Inter­action",                                       // soft hyphen from a PDF
  ".NET performance study", "...", "~Draft", "Draft~", "Draft~2",
  "מחקר‏ study",                    // right-to-left mark
  "Aux", "aux.study", "COM1", "desktop.ini", "Notes.url", "x.{clsid}",
  "Ｆｕｌｌｗｉｄｔｈ／ｓｌａｓｈ", "tab\there", "new\nline", "\u0085next",
  "  spaced  out  ", "﻿bom", "﷐nonchar", "trailing.", "emoji \u{1F9EA}".repeat(20),
  "", "   ", null, undefined, "%20percent",
];

test("every title becomes a folder name Chrome accepts", () => {
  const { api } = loadBackground();
  for (const title of TITLES) {
    const name = api.safeSegment(title);
    assert.ok(chromeAccepts(name), `${JSON.stringify(title)} became ${JSON.stringify(name)}, which Chrome refuses`);
    assert.ok(Array.from(name).length <= 92, `${JSON.stringify(name)} is too long`);
  }
});

test("random titles never produce a name Chrome refuses", () => {
  const { api } = loadBackground();
  const pool = [..."aA. ~-_\t\n%:/\\*?\"<>|", "­", "​", "‍", "‎", "﻿", "　", " ",
    "\u{1F469}", "א", "é", "Ä", "\u0000", "\u001F", "﷐", "\u{1FFFE}"];
  let seed = 1;
  const next = () => { seed = (seed * 48271) % 2147483647; return seed; };
  for (let i = 0; i < 3000; i += 1) {
    const title = Array.from({ length: 1 + (next() % 120) }, () => pool[next() % pool.length]).join("");
    const name = api.safeSegment(title);
    assert.ok(chromeAccepts(name), `${JSON.stringify(title)} became ${JSON.stringify(name)}`);
  }
});

test("an ordinary title is left alone, apart from what Chrome forbids", () => {
  const { api } = loadBackground();
  assert.equal(api.safeSegment("Does It Matter How You Touch?"), "Does It Matter How You Touch-");
  assert.equal(api.safeSegment("Lab notes \u{1F469}‍\u{1F52C}"), "Lab notes \u{1F469}\u{1F52C}");
  assert.equal(api.safeSegment("Aux"), "_Aux");
  assert.equal(api.safeSegment(""), "overleaf-project");
});
