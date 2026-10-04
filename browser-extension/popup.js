"use strict";

const PROJECT_PATH_RE = /\/project\/([0-9a-f]{24})(?:\/|$)/i;
const LANGUAGE_STORAGE_KEY = "overleaf-comments-export-language";
const CHOICES_STORAGE_KEY = "overleaf-comments-export-choices";
// The boxes people tick, and what they start as. Anyone exporting the same
// project twice wants the same files twice, so the choices are remembered.
const CHOICE_DEFAULTS = {
  "include-resolved": true,
  "include-changes": true,
  "format-md": true,
  "format-json": true,
  "format-jsonl": false,
  "format-xlsx": false,
  "scope-current": false,
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
    scopeLegend: "Narrow it down",
    currentFileTitle: "This file only",
    currentFileHelp: "Just the document open in the editor",
    reviewerTitle: "One person",
    reviewerHelp: "Only threads this person took part in",
    reviewerPlaceholder: "Leave empty for everyone",
    copyButton: "Copy the Markdown",
    copied: "Copied. Paste it into anything.",
    copyFailed: "Could not copy. The file is in your Downloads folder.",
    savedTo: "Saved to your Downloads folder, under {folder}",
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
    scopeLegend: "缩小范围",
    currentFileTitle: "仅当前文件",
    currentFileHelp: "只导出编辑器中打开的文档",
    reviewerTitle: "指定某个人",
    reviewerHelp: "只导出此人参与过的讨论",
    reviewerPlaceholder: "留空表示所有人",
    copyButton: "复制 Markdown",
    copied: "已复制，可直接粘贴。",
    copyFailed: "复制失败，文件已保存在下载文件夹中。",
    savedTo: "已保存到下载文件夹的 {folder} 中",
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
  copyButton: document.getElementById("copy"),
  result: document.getElementById("result"),
};

let activeTab = null;
let busy = false;
let stopping = false;

// Progress comes straight from the page, job news from the background. Both
// are about one tab, which has to be this one.
chrome.runtime.onMessage.addListener((message, sender) => {
  if (message?.oceProgress && sender.tab?.id === activeTab?.id) showProgress(message.oceProgress);
  if (message?.target === "popup" && message.tabId === activeTab?.id) render(message.job);
  return false;
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

function storedLanguage() {
  try {
    return localStorage.getItem(LANGUAGE_STORAGE_KEY);
  } catch {
    return null;                 // storage unavailable: English, not a crash
  }
}

let language = resolveLanguage(typeof localStorage === "undefined" ? null : storedLanguage());

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
  for (const element of document.querySelectorAll("[data-i18n-placeholder]")) {
    element.placeholder = t(element.dataset.i18nPlaceholder);
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

function readOptions() {
  return {
    language,
    includeResolved: document.getElementById("include-resolved").checked,
    includeChanges: document.getElementById("include-changes").checked,
    currentFileOnly: document.getElementById("scope-current").checked,
    reviewer: document.getElementById("scope-reviewer").value.trim(),
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
  ui.stopButton.disabled = stopping;
  ui.stopButton.textContent = stopping ? t("stopping") : t("stopButton");
}

// The Markdown of the last export, held so it can be copied without running
// the whole thing again. Pasting it into an assistant is the most common
// thing anyone does next, and downloading a file to open it and copy it is
// three steps where one will do.
let lastMarkdown = "";

function showResult(message, isError = false) {
  ui.result.hidden = false;
  ui.result.classList.toggle("error", isError);
  ui.result.textContent = message;
  ui.copyButton.hidden = isError || !lastMarkdown;
  ui.copyButton.textContent = t("copyButton");
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
  // An export may already be running here, started before the popup last
  // closed, or have just finished. Either way, show it.
  render(await send("status").catch(() => null));
}

function send(type, payload = {}) {
  return chrome.runtime.sendMessage({ target: "background", type, tabId: activeTab?.id, url: activeTab?.url, ...payload });
}

// Codes from the background, worded here, where the language is known.
// Anything else arrives already worded by the page.
function errorText(error) {
  return ["injectionError", "invalidResult"].includes(error) ? t(error) : String(error || t("invalidResult"));
}

function completeMessage(job) {
  const summary = job.summary || {};
  let message = t("complete", {
    threads: summary.threadCount,
    open: summary.openCount,
    resolved: summary.resolvedCount,
    changes: summary.trackedChangeCount,
    files: job.files,
  });
  message += ` ${t("savedTo", { folder: job.folder })}`;
  if (job.warnings?.length) {
    const separator = language === "zh" ? "；" : "; ";
    message += ` ${t("warnings", { warnings: job.warnings.join(separator) })}`;
  }
  return message;
}

function render(job) {
  if (!job) return;
  stopping = Boolean(job.stopping);
  if (job.state === "running") {
    ui.result.hidden = true;
    ui.copyButton.hidden = true;
    setBusy(true);
    if (stopping) ui.progress.textContent = t("stopping");
    else if (job.progress) showProgress(job.progress);
    return;
  }
  setBusy(false);
  // Held so it can be copied without running the export again.
  lastMarkdown = job.state === "done" ? job.markdown || "" : "";
  if (job.state === "done") showResult(completeMessage(job));
  else if (job.state === "stopped") showResult(t("stopped"));
  else showResult(errorText(job.error), true);
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

ui.copyButton.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(lastMarkdown);
    ui.copyButton.textContent = t("copied");
  } catch {
    // Clipboard access can be refused. The file is on disk either way, so
    // say where rather than leaving a button that appears to do nothing.
    ui.copyButton.textContent = t("copyFailed");
  }
});

ui.stopButton.addEventListener("click", () => {
  // The page checks between steps. A request already in flight has to come
  // back first, so the button says what it is doing rather than appearing to
  // have done nothing.
  stopping = true;
  setBusy(true);
  ui.progress.textContent = t("stopping");
  send("stop").catch(() => {});
});

ui.languageSelect.addEventListener("change", () => {
  language = resolveLanguage(ui.languageSelect.value);
  try {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  } catch {
    // Not remembered, but still switched for now.
  }
  ui.result.hidden = true;
  applyLanguage();
});

ui.exportButton.addEventListener("click", async () => {
  const options = readOptions();
  if (!Object.values(options.formats).some(Boolean)) {
    showResult(t("noFormat"), true);
    return;
  }
  // Starts it and nothing more. The background runs it, so this popup can
  // close at any moment, to a stray click or a Save dialog, and lose nothing.
  stopping = false;
  lastMarkdown = "";
  ui.copyButton.hidden = true;
  ui.result.hidden = true;
  setBusy(true);
  try {
    const reply = await send("export", { options });
    if (reply?.job) render(reply.job);      // one was already running here
  } catch (error) {
    setBusy(false);
    showResult(error?.message || String(error), true);
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
    CHOICE_DEFAULTS, readStoredChoices,
  };
}
