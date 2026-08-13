"use strict";

const PROJECT_PATH_RE = /\/project\/([0-9a-f]{24})(?:\/|$)/i;
const LANGUAGE_STORAGE_KEY = "overleaf-comments-export-language";

const COPY = {
  zh: {
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
  en: {
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
};

const ui = {
  languageInputs: Array.from(document.querySelectorAll('input[name="language"]')),
  pageCard: document.getElementById("page-card"),
  pageState: document.getElementById("page-state"),
  pageDetail: document.getElementById("page-detail"),
  options: document.getElementById("options"),
  formats: document.getElementById("formats"),
  exportButton: document.getElementById("export"),
  buttonLabel: document.getElementById("button-label"),
  spinner: document.getElementById("spinner"),
  result: document.getElementById("result"),
};

let activeTab = null;
let busy = false;
let pageStatus = "checking";
let pageDetail = "";
let language = localStorage.getItem(LANGUAGE_STORAGE_KEY)
  || (navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en");

function t(key, replacements = {}) {
  let value = COPY[language]?.[key] || COPY.en[key] || key;
  for (const [name, replacement] of Object.entries(replacements)) {
    value = value.replaceAll(`{${name}}`, String(replacement));
  }
  return value;
}

function applyLanguage() {
  document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  for (const input of ui.languageInputs) {
    input.checked = input.value === language;
    input.closest(".language-option")?.classList.toggle("selected", input.checked);
  }
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
      responseLetter: document.getElementById("format-letter").checked,
    },
  };
}

function setBusy(nextBusy) {
  busy = nextBusy;
  ui.exportButton.disabled = busy || !activeTab;
  ui.options.disabled = busy || !activeTab;
  ui.formats.disabled = busy || !activeTab;
  for (const input of ui.languageInputs) {
    input.disabled = busy;
    input.closest(".language-option")?.classList.toggle("disabled", busy);
  }
  ui.spinner.hidden = !busy;
  ui.buttonLabel.textContent = busy ? t("exporting") : t("exportButton");
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
    files: ["src/export-core.js", "src/page-client.js"],
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
  const url = URL.createObjectURL(new Blob([output.content], { type: output.mimeType }));
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

for (const input of ui.languageInputs) {
  input.addEventListener("change", () => {
    if (!input.checked) return;
    language = input.value === "zh" ? "zh" : "en";
    localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
    ui.result.hidden = true;
    applyLanguage();
  });
}

ui.exportButton.addEventListener("click", async () => {
  const options = readOptions();
  if (!Object.values(options.formats).some(Boolean)) {
    showResult(t("noFormat"), true);
    return;
  }

  setBusy(true);
  ui.result.hidden = true;

  try {
    const result = await collectFromPage(options);
    if (!result?.ok) throw new Error(result?.error || t("invalidResult"));

    const folder = `overleaf-comments/${safeSegment(result.project.title)}/${exportTimestampSegment(result.generatedAt)}`;
    for (const output of result.outputs) await downloadOutput(output, folder);

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
