"use strict";

const PROJECT_PATH_RE = /\/project\/([0-9a-f]{24})(?:\/|$)/i;
const LANGUAGE_STORAGE_KEY = "overleaf-comments-export-language";
const CHOICES_STORAGE_KEY = "overleaf-comments-export-choices";
// One snapshot of the last export per paper, so the next one can say what
// changed. Kept in localStorage rather than chrome.storage because that would
// mean adding the storage permission to the manifest, and a permission change
// buys a slower review at the store for something the page can already do.
const SNAPSHOT_PREFIX = "oce-snapshot-";
// Enough for everything somebody has in review at once. Snapshots are trimmed
// to what the comparison reads, but they are still the biggest thing kept.
const MAX_SNAPSHOTS = 6;

function loadSnapshot(projectId) {
  if (typeof localStorage === "undefined") return null;
  try {
    const raw = localStorage.getItem(SNAPSHOT_PREFIX + projectId);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;               // unreadable: no diff, and no failure either
  }
}

function saveSnapshot(projectId, snapshot) {
  if (typeof localStorage === "undefined" || !snapshot) return;
  const write = () => localStorage.setItem(
    SNAPSHOT_PREFIX + projectId, JSON.stringify(snapshot));
  try {
    write();
  } catch {
    // Out of room. Drop the oldest and try once more; nothing here is
    // precious, a missing snapshot only costs the next export its diff.
    try {
      const keys = Object.keys(localStorage).filter((k) => k.startsWith(SNAPSHOT_PREFIX));
      keys.sort((a, b) => {
        const at = JSON.parse(localStorage.getItem(a) || "{}").pulled_at || "";
        const bt = JSON.parse(localStorage.getItem(b) || "{}").pulled_at || "";
        return String(at).localeCompare(String(bt));
      });
      for (const key of keys.slice(0, Math.max(1, keys.length - MAX_SNAPSHOTS + 1))) {
        localStorage.removeItem(key);
      }
      write();
    } catch {
      // Still no room. An export that has already happened must not fail
      // because of a nicety.
    }
  }
}

// The boxes people tick, and what they start as. Anyone exporting the same
// project twice wants the same files twice, so the choices are remembered.
const CHOICE_DEFAULTS = {
  "include-resolved": true,
  "include-changes": true,
  "format-md": true,
  "format-json": true,
  "format-jsonl": false,
  "format-xlsx": false,
  "format-letter": false,
};

function readStoredChoices() {
  if (typeof localStorage === "undefined") return {};
  try {
    const raw = JSON.parse(localStorage.getItem(CHOICES_STORAGE_KEY) || "{}");
    // Only keys we know about, only booleans. Anything else in there is
    // either from an older version or somebody editing storage by hand.
    return Object.fromEntries(
      Object.keys(CHOICE_DEFAULTS)
        .filter((id) => typeof raw[id] === "boolean")
        .map((id) => [id, raw[id]]));
  } catch {
    return {};
  }
}

function applyStoredChoices() {
  const stored = { ...CHOICE_DEFAULTS, ...readStoredChoices() };
  for (const [id, checked] of Object.entries(stored)) {
    const box = document.getElementById(id);
    if (box) box.checked = checked;
  }
}

function rememberChoices() {
  if (typeof localStorage === "undefined") return;
  const current = {};
  for (const id of Object.keys(CHOICE_DEFAULTS)) {
    const box = document.getElementById(id);
    if (box) current[id] = box.checked;
  }
  try {
    localStorage.setItem(CHOICES_STORAGE_KEY, JSON.stringify(current));
  } catch {
    // A full or disabled storage must not stop an export.
  }
}

const COPY = {
  en: {
    formatXlsx: "Spreadsheet",
    repoLink: "Free and open source. Star it on GitHub ★",
    stopButton: "Stop",
    stopping: "Stopping…",
    stopped: "Stopped. Nothing was downloaded.",
    progressFiles: "Reading file {done} of {total}…",
    progressIncludes: "Reading {total} more file(s) the paper pulls in…",
    progressBuilding: "Putting the export together…",
    languageName: "English",
    title: "Export project comments",
    languageLabel: "Language",
    checkingPage: "Checking the current tab…",
    includeLegend: "Include",
    resolvedTitle: "Resolved comments",
    resolvedHelp: "Also export discussions marked as resolved",
    changesTitle: "Tracked changes",
    changesHelp: "Include insertion and deletion records",
    outputLegend: "Output files",
    responseLetter: "Response letter",
    exportButton: "Export current project",
    exporting: "Reading comments and source files…",
    privacyNote: "Data is read only from the current tab and downloaded locally. The extension never reads, stores, or uploads your login cookie.",
    invalidPage: "This tab is not an Overleaf project",
    invalidPageHelp: "Open an Overleaf project editor, then click the extension again.",
    ready: "Overleaf project detected",
    initError: "Could not inspect the current tab",
    noFormat: "Select at least one output format.",
    injectionError: "The extension page script did not load. Refresh the Overleaf page and try again.",
    invalidResult: "The export did not return a valid result.",
    complete: "Export complete: {threads} discussions ({open} open, {resolved} resolved), {changes} tracked changes. Downloaded {files} files.",
    warnings: "Warnings: {warnings}",
  },
  zh: {
    formatXlsx: "电子表格",
    repoLink: "免费开源，欢迎在 GitHub 点亮星标 ★",
    stopButton: "停止",
    stopping: "正在停止…",
    stopped: "已停止，未下载任何文件。",
    progressFiles: "正在读取第 {done} / {total} 个文件…",
    progressIncludes: "正在读取论文引用的另外 {total} 个文件…",
    progressBuilding: "正在生成导出内容…",
    languageName: "中文",
    title: "导出项目评论",
    languageLabel: "语言",
    checkingPage: "正在检查当前标签页…",
    includeLegend: "包含内容",
    resolvedTitle: "已解决评论",
    resolvedHelp: "同时导出已标记 resolved 的讨论",
    changesTitle: "修订记录",
    changesHelp: "包含插入与删除记录",
    outputLegend: "输出文件",
    responseLetter: "回复信模板",
    exportButton: "导出当前项目",
    exporting: "正在读取评论与源文件…",
    privacyNote: "数据仅在当前标签页中读取并下载到本机；扩展不会读取、保存或上传登录 Cookie。",
    invalidPage: "当前标签页不是 Overleaf 项目",
    invalidPageHelp: "请先打开项目编辑器页面，再点击扩展图标。",
    ready: "已检测到 Overleaf 项目",
    initError: "无法检查当前标签页",
    noFormat: "请至少选择一种输出格式。",
    injectionError: "扩展页面脚本没有加载成功。请刷新 Overleaf 页面后重试。",
    invalidResult: "没有收到有效的导出结果。",
    complete: "导出完成：{threads} 个讨论（{open} 个未解决、{resolved} 个已解决），{changes} 条修订记录。已下载 {files} 个文件。",
    warnings: "警告：{warnings}",
  },
};

const ui = {
  languageSelect: document.getElementById("language-select"),
  pageCard: document.getElementById("page-card"),
  pageState: document.getElementById("page-state"),
  pageDetail: document.getElementById("page-detail"),
  options: document.getElementById("options"),
  formats: document.getElementById("formats"),
  exportButton: document.getElementById("export"),
  buttonLabel: document.getElementById("button-label"),
  spinner: document.getElementById("spinner"),
  progress: document.getElementById("progress"),
  stopButton: document.getElementById("stop"),
  result: document.getElementById("result"),
};

let activeTab = null;
let busy = false;
let stopRequested = false;

// The page asks whether to stop, and reports where it has got to. Both
// arrive here while executeScript is still running, which is the only way
// the popup learns anything before the export finishes.
chrome.runtime.onMessage.addListener((message, _sender, respond) => {
  if (message?.oceStopCheck) {
    respond({ stop: stopRequested });
    return true;
  }
  if (message?.oceProgress) {
    showProgress(message.oceProgress);
  }
  return undefined;
});

function showProgress({ stage, done, total }) {
  if (!busy) return;
  if (stage === "files") ui.progress.textContent = t("progressFiles", { done, total });
  else if (stage === "includes") ui.progress.textContent = t("progressIncludes", { total });
  else ui.progress.textContent = t("progressBuilding");
}
let pageStatus = "checking";
let pageDetail = "";
const DEFAULT_LANGUAGE = "en";

function resolveLanguage(stored) {
  return Object.prototype.hasOwnProperty.call(COPY, stored) ? stored : DEFAULT_LANGUAGE;
}

function languageChoices() {
  return Object.entries(COPY).map(([code, copy]) => ({ code, label: copy.languageName || code }));
}

let language = resolveLanguage(
  typeof localStorage === "undefined" ? null : localStorage.getItem(LANGUAGE_STORAGE_KEY));

function t(key, replacements = {}) {
  let value = COPY[language]?.[key] || COPY.en[key] || key;
  for (const [name, replacement] of Object.entries(replacements)) {
    value = value.replaceAll(`{${name}}`, String(replacement));
  }
  return value;
}

function applyLanguage() {
  document.documentElement.lang = language === "zh" ? "zh-CN" : language;
  if (ui.languageSelect) ui.languageSelect.value = language;
  for (const element of document.querySelectorAll("[data-i18n]")) {
    element.textContent = t(element.dataset.i18n);
  }
  renderPageState();
  setBusy(busy);
}

function renderPageState() {
  const stateKey = {
    checking: "checkingPage",
    invalid: "invalidPage",
    ready: "ready",
    error: "initError",
  }[pageStatus];
  ui.pageState.textContent = t(stateKey || "checkingPage");
  ui.pageDetail.textContent = pageStatus === "invalid" ? t("invalidPageHelp") : pageDetail;
}

function isSupportedProjectUrl(value) {
  try {
    const url = new URL(value);
    return (url.protocol === "https:" || url.protocol === "http:") && PROJECT_PATH_RE.test(url.pathname);
  } catch {
    return false;
  }
}

function safeSegment(value, fallback = "overleaf-project") {
  const cleaned = String(value || "")
    .normalize("NFKC")
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, "-")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/[. ]+$/g, "")
    .slice(0, 90);
  return cleaned || fallback;
}

function exportTimestampSegment(value) {
  const date = new Date(value || Date.now());
  const valid = Number.isNaN(date.getTime()) ? new Date() : date;
  return valid.toISOString().replace(/:/g, "-").replace(/\.\d{3}Z$/, "Z");
}

function readOptions() {
  return {
    language,
    includeResolved: document.getElementById("include-resolved").checked,
    includeChanges: document.getElementById("include-changes").checked,
    formats: {
      markdown: document.getElementById("format-md").checked,
      json: document.getElementById("format-json").checked,
      jsonl: document.getElementById("format-jsonl").checked,
      xlsx: document.getElementById("format-xlsx").checked,
      responseLetter: document.getElementById("format-letter").checked,
    },
  };
}

function setBusy(nextBusy) {
  busy = nextBusy;
  ui.exportButton.disabled = busy || !activeTab;
  ui.options.disabled = busy || !activeTab;
  ui.formats.disabled = busy || !activeTab;
  if (ui.languageSelect) ui.languageSelect.disabled = busy;
  ui.spinner.hidden = !busy;
  ui.progress.hidden = !busy;
  if (!busy) ui.progress.textContent = "";
  ui.buttonLabel.textContent = busy ? t("exporting") : t("exportButton");
  ui.stopButton.hidden = !busy;
  ui.stopButton.disabled = stopRequested;
  ui.stopButton.textContent = stopRequested ? t("stopping") : t("stopButton");
}

function showResult(message, isError = false) {
  ui.result.hidden = false;
  ui.result.classList.toggle("error", isError);
  ui.result.textContent = message;
}

async function initialize() {
  if (!globalThis.chrome?.tabs?.query) {
    pageStatus = "invalid";
    renderPageState();
    return;
  }
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !isSupportedProjectUrl(tab.url)) {
    pageStatus = "invalid";
    ui.pageCard.classList.add("error");
    renderPageState();
    return;
  }

  activeTab = tab;
  pageStatus = "ready";
  pageDetail = tab.title || tab.url;
  ui.pageCard.classList.add("ready");
  renderPageState();
  setBusy(false);
}

async function collectFromPage(options) {
  // The isolated world on purpose. Everything the injected code needs from
  // the page is DOM, which the isolated world shares, and a relative fetch
  // sends the session cookie there just the same. In the main world the page
  // owns the globals, so a hostile page matching the project URL pattern
  // could define __overleafCommentsExtension before us, make the real client
  // return early, and have whatever it liked written to the user's Downloads.
  await chrome.scripting.executeScript({
    target: { tabId: activeTab.id },
    files: ["src/export-core.js", "src/xlsx.js", "src/page-client.js"],
  });

  const [execution] = await chrome.scripting.executeScript({
    target: { tabId: activeTab.id },
    func: async (exportOptions, injectionError) => {
      if (!globalThis.__overleafCommentsExtension) throw new Error(injectionError);
      return globalThis.__overleafCommentsExtension.collect(exportOptions);
    },
    args: [options, t("injectionError")],
  });

  return execution?.result;
}

async function downloadOutput(output, folder) {
  const body = output.base64
    ? Uint8Array.from(atob(output.base64), (ch) => ch.charCodeAt(0))
    : output.content;
  const url = URL.createObjectURL(new Blob([body], { type: output.mimeType }));
  try {
    await chrome.downloads.download({
      url,
      filename: `${folder}/${safeSegment(output.filename, "comments.txt")}`,
      conflictAction: "uniquify",
      saveAs: false,
    });
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  }
}

// Built from COPY, so a new language appears here by adding it there.
for (const { code, label } of languageChoices()) {
  const option = document.createElement("option");
  option.value = code;
  option.textContent = label;
  ui.languageSelect.append(option);
}

applyStoredChoices();
for (const id of Object.keys(CHOICE_DEFAULTS)) {
  document.getElementById(id)?.addEventListener("change", rememberChoices);
}

ui.stopButton.addEventListener("click", () => {
  // The page checks this between steps. A request already in flight has to
  // come back first, so the button says what it is doing rather than
  // appearing to have done nothing.
  stopRequested = true;
  setBusy(true);
  ui.progress.textContent = t("stopping");
});

ui.languageSelect.addEventListener("change", () => {
  language = resolveLanguage(ui.languageSelect.value);
  localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  ui.result.hidden = true;
  applyLanguage();
});

ui.exportButton.addEventListener("click", async () => {
  const options = readOptions();
  if (!Object.values(options.formats).some(Boolean)) {
    showResult(t("noFormat"), true);
    return;
  }

  stopRequested = false;
  setBusy(true);
  ui.result.hidden = true;

  try {
    const projectId = activeTab?.projectId || "";
    if (projectId) options.previousSnapshot = loadSnapshot(projectId);
    const result = await collectFromPage(options);
    if (!result?.ok) throw new Error(result?.error || t("invalidResult"));

    const folder = `overleaf-comments/${safeSegment(result.project.title)}/${exportTimestampSegment(result.generatedAt)}`;
    for (const output of result.outputs) await downloadOutput(output, folder);

    // Kept only after the files are safely written, so a failed export never
    // moves the baseline the next diff is measured against.
    if (projectId && result.snapshot) saveSnapshot(projectId, result.snapshot);

    const summary = result.summary;
    let message = t("complete", {
      threads: summary.threadCount,
      open: summary.openCount,
      resolved: summary.resolvedCount,
      changes: summary.trackedChangeCount,
      files: result.outputs.length,
    });
    if (result.warnings?.length) {
      const separator = language === "zh" ? "；" : "; ";
      message += ` ${t("warnings", { warnings: result.warnings.join(separator) })}`;
    }
    showResult(message);
  } catch (error) {
    showResult(error?.message || String(error), true);
  } finally {
    setBusy(false);
  }
});

applyLanguage();
initialize().catch((error) => {
  pageStatus = "error";
  pageDetail = error?.message || String(error);
  ui.pageCard.classList.add("error");
  renderPageState();
});

// Exported for the tests. Harmless in the browser, where module is undefined.
if (typeof module === "object" && module.exports) {
  module.exports = {
    COPY, DEFAULT_LANGUAGE, resolveLanguage, languageChoices,
    CHOICE_DEFAULTS, readStoredChoices, loadSnapshot, saveSnapshot,
  };
}
