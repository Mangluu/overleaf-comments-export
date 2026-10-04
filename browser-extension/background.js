"use strict";

// Chrome opens this page when someone removes the extension, the one chance
// to ask why. The address carries the version and the browser's language, so
// the page can answer in Chinese, and nothing else. No permission is needed.
const UNINSTALL_PAGE = "https://mangluu.github.io/overleaf-comments-export/uninstalled.html";

function uninstallUrl() {
  const version = chrome.runtime.getManifest().version;
  const lang = chrome.i18n.getUILanguage().toLowerCase().startsWith("zh") ? "zh" : "en";
  return `${UNINSTALL_PAGE}?v=${encodeURIComponent(version)}&lang=${lang}`;
}

// Every time the worker starts, not only on install, so an address changed in
// a later version reaches people who installed an earlier one.
chrome.runtime.setUninstallURL(uninstallUrl());


// ---- Exports run here, not in the popup ----------------------------------
//
// A popup closes the moment it loses focus, to a click anywhere else or to
// the Save dialog Chrome opens for each file when it asks where to save every
// download. Whatever the popup was running went with it. Here an export
// outlives the popup, which only starts it, watches it, and stops it.

const INJECTED_FILES = ["src/export-core.js", "src/xlsx.js", "src/page-client.js"];
const PROJECT_PATH_RE = /\/project\/([0-9a-f]{24})(?:\/|$)/i;

// One per tab, kept only while this worker lives. That is long enough for a
// popup reopened during an export, or just after it, to show it.
const jobs = new Map();

function projectIdFromUrl(value) {
  try {
    return (new URL(value).pathname.match(PROJECT_PATH_RE) || [])[1] || "";
  } catch {
    return "";
  }
}


// ---- Names Chrome will accept ---------------------------------------------
//
// chrome.downloads refuses a download outright, with "Invalid filename", when
// any folder in its path breaks a rule in Chromium's IsSafePortablePathComponent
// (net/base/filename_util_icu.cc). The paper's title is one of those folders,
// and ordinary titles broke it: an emoji made with a zero-width joiner, a soft
// hyphen pasted from a PDF, a right-to-left mark, a leading dot, the name of a
// Windows device, or a long title cut off just after a space. Every rule here
// is one of Chromium's, and a test checks the output against all of them.

// Removed, because they are invisible and Chrome refuses every one.
const INVISIBLE = /[\p{Cf}\p{Noncharacter_Code_Point}]/gu;
// Replaced. The punctuation is Chrome's list. A tilde is legal mid-name, but
// not at either end, and on Windows not in anything shaped like an old 8.3
// short name, so it is replaced everywhere rather than reasoned about.
const NOT_IN_A_NAME = /["*/:<>?\\|~\p{Cc}]/gu;
// Matched on the part before the first dot, as Windows does.
const WINDOWS_DEVICE = /^(con|prn|aux|nul|com[1-9]|lpt[1-9]|clock\$)$/i;
const WINDOWS_RESERVED = /^(desktop\.ini|thumbs\.db|conin\$|conout\$)$/i;
const SHELL_EXTENSION = /\.(local|lnk|scf|url|\{[^}]*\})$/i;
const MAX_NAME = 90;

function safeSegment(value, fallback = "overleaf-project") {
  let name = String(value ?? "")
    .normalize("NFKC")                 // first, so a fullwidth slash becomes one
    .replace(INVISIBLE, "")
    .replace(/\s+/gu, " ")
    .replace(NOT_IN_A_NAME, "-");
  // Cut before trimming the ends, never after, or the cut can leave the
  // space that ends the name. By code points, so an emoji is never halved.
  name = Array.from(name).slice(0, MAX_NAME).join("").replace(/^[\s.]+|[\s.]+$/gu, "");
  if (!name) return fallback;
  if (WINDOWS_DEVICE.test(name.split(".")[0]) || WINDOWS_RESERVED.test(name)) name = `_${name}`;
  if (SHELL_EXTENSION.test(name)) name = `${name}_`;
  return name;
}

function exportTimestampSegment(value) {
  const date = new Date(value || Date.now());
  const valid = Number.isNaN(date.getTime()) ? new Date() : date;
  return valid.toISOString().replace(/:/g, "-").replace(/\.\d{3}Z$/, "Z");
}


// ---- The offscreen page ---------------------------------------------------
//
// A service worker has no URL.createObjectURL and no localStorage. Data URLs
// would do for small files, but Chrome caps any URL at 2 MB (url::kMaxURLChars)
// and a long thesis's comments.json passes that. The offscreen page has both,
// and its localStorage is the one the popup has always used.

let offscreenUsers = 0;
let lifecycle = Promise.resolve();

// Opening and closing in turn, so one export finishing cannot close the page
// out from under another that is just starting.
function inTurn(step) {
  lifecycle = lifecycle.then(step, step);
  return lifecycle;
}

async function withOffscreen(work) {
  offscreenUsers += 1;
  try {
    await inTurn(async () => {
      const open = await chrome.runtime.getContexts({ contextTypes: ["OFFSCREEN_DOCUMENT"] });
      if (open.length) return;
      await chrome.offscreen.createDocument({
        url: "offscreen.html",
        reasons: ["BLOBS", "LOCAL_STORAGE"],
        justification: "Turns a finished export into files to download, and keeps the last export of each paper so the next one can say what changed.",
      });
    });
    return await work();
  } finally {
    offscreenUsers -= 1;
    // Closing revokes its blob URLs, which is safe once the downloads exist:
    // Chrome creates a download only when its data has started to arrive.
    await inTurn(async () => {
      if (!offscreenUsers) await chrome.offscreen.closeDocument().catch(() => {});
    });
  }
}

function toOffscreen(type, payload = {}) {
  return chrome.runtime.sendMessage({ target: "offscreen", type, ...payload });
}


// ---- The export -----------------------------------------------------------

function view(job) {
  if (!job) return null;
  const { state, progress, stopping, summary, files, folder, warnings, markdown, error } = job;
  return { state, progress, stopping, summary, files, folder, warnings, markdown, error };
}

// Tells the popup, if one is open, and the badge, for whoever closed it.
function tell(tabId, job) {
  chrome.runtime.sendMessage({ target: "popup", type: "job", tabId, job: view(job) }).catch(() => {});
  const [text, color] = job.state === "running" ? ["…", "#2f7d4f"]
    : job.state === "failed" ? ["!", "#b3261e"] : ["", "#2f7d4f"];
  chrome.action.setBadgeBackgroundColor({ tabId, color }).catch(() => {});
  chrome.action.setBadgeText({ tabId, text }).catch(() => {});
}

async function runExport(tabId, url, options) {
  const job = { state: "running", stopping: false, progress: null, projectId: projectIdFromUrl(url) };
  jobs.set(tabId, job);
  tell(tabId, job);
  try {
    await withOffscreen(async () => {
      const previousSnapshot = job.projectId
        ? await toOffscreen("loadSnapshot", { projectId: job.projectId }) : null;

      // The isolated world on purpose. Everything the injected code needs from
      // the page is DOM, which the isolated world shares, and a relative fetch
      // sends the session cookie there just the same. In the main world the
      // page owns the globals, so a hostile page matching the project URL could
      // define __overleafCommentsExtension first and decide what gets written.
      await chrome.scripting.executeScript({ target: { tabId }, files: INJECTED_FILES });
      const [execution] = await chrome.scripting.executeScript({
        target: { tabId },
        func: (exportOptions) => {
          const client = globalThis.__overleafCommentsExtension;
          return client ? client.collect(exportOptions) : { ok: false, error: "injectionError" };
        },
        args: [{ ...options, previousSnapshot }],
      });
      // Chrome turns anything thrown in the page into a null result. collect
      // never throws, so a null here means it never ran.
      const result = execution?.result;
      if (!result?.ok) {
        throw Object.assign(new Error(result?.error || "invalidResult"), { stopped: Boolean(result?.stopped) });
      }

      const folder = `overleaf-comments/${safeSegment(result.project?.title)}/${exportTimestampSegment(result.generatedAt)}`;
      const urls = await toOffscreen("blobs", {
        files: result.outputs.map(({ content, base64, mimeType }) => ({ content, base64, mimeType })),
      });
      await Promise.all(result.outputs.map((output, i) => chrome.downloads.download({
        url: urls[i],
        filename: `${folder}/${safeSegment(output.filename, "comments.txt")}`,
        conflictAction: "uniquify",
        saveAs: false,
      })));
      // Only once the files are on their way, so a failed export never moves
      // the baseline the next one is compared against.
      if (job.projectId && result.snapshot) {
        await toOffscreen("saveSnapshot", { projectId: job.projectId, snapshot: result.snapshot });
      }
      Object.assign(job, {
        state: "done",
        summary: result.summary,
        files: result.outputs.length,
        folder,
        warnings: result.warnings || [],
        markdown: result.outputs.find((o) => /^comments-.*\.md$/.test(o.filename))?.content || "",
      });
    });
  } catch (error) {
    const stopped = job.stopping || Boolean(error?.stopped);
    Object.assign(job, { state: stopped ? "stopped" : "failed", error: stopped ? "" : error?.message || String(error) });
  }
  tell(tabId, job);
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  // From the page client, while it works.
  if (message?.oceStopCheck) {
    // No job means this worker restarted and the export it belonged to is
    // gone, so nobody would ever collect the result. Stop.
    respond({ stop: jobs.get(sender.tab?.id)?.stopping ?? true });
    return false;
  }
  if (message?.oceProgress) {
    const job = jobs.get(sender.tab?.id);
    if (job) job.progress = message.oceProgress;
    return false;
  }

  // From the popup.
  if (message?.target !== "background") return false;
  const { tabId } = message;
  const job = jobs.get(tabId);
  if (message.type === "status") {
    // A tab can have moved on to another paper since, and that job is over.
    const same = job && job.projectId === projectIdFromUrl(message.url);
    if (job && !same && job.state !== "running") jobs.delete(tabId);
    if (!job || job.state !== "running") chrome.action.setBadgeText({ tabId, text: "" }).catch(() => {});
    respond(same ? view(job) : null);
  } else if (message.type === "export") {
    if (job?.state === "running") {
      respond({ ok: false, job: view(job) });
    } else {
      runExport(tabId, message.url, message.options || {});
      respond({ ok: true });
    }
  } else if (message.type === "stop") {
    if (job?.state === "running") {
      job.stopping = true;
      tell(tabId, job);
    }
    respond({ ok: true });
  }
  return false;
});

if (typeof module === "object" && module.exports) {
  module.exports = { uninstallUrl, UNINSTALL_PAGE, safeSegment, projectIdFromUrl, exportTimestampSegment, jobs };
}
