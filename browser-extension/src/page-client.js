(function attachOverleafPageClient(root) {
  "use strict";

  const VERSION = "1.4.0";
  if (root.__overleafCommentsExtension?.version === VERSION) return;

  const core = root.OverleafCommentsCore;
  if (!core) throw new Error("OverleafCommentsCore was not loaded before page-client.js.");

  const TEXT = {
    zh: {
      network: "无法连接 Overleaf：{detail}",
      forbidden: "Overleaf 拒绝了请求。请确认当前标签页已经登录且有权访问这个项目。",
      http: "Overleaf 接口 {path} 返回 HTTP {status}。",
      invalidJson: "Overleaf 接口 {path} 没有返回有效 JSON。",
      noProject: "当前页面没有有效的 Overleaf project ID。",
      invalidThreads: "Overleaf 的评论接口返回了无法识别的数据结构。",
      resolvedWarning: "无法读取独立的 resolved 列表，已使用 thread 自带状态",
      rangesWarning: "无法读取评论锚点，评论仍会导出但可能没有文件名和行号",
      filesWarning: "当前页面没有暴露完整文件树，部分文件将使用文档 ID 命名",
      sourceWarning: "无法下载源文件 {file}，相关评论将作为未定位讨论导出",
    },
    en: {
      network: "Could not connect to Overleaf: {detail}",
      forbidden: "Overleaf rejected the request. Make sure this tab is signed in and the account can access the project.",
      http: "The Overleaf endpoint {path} returned HTTP {status}.",
      invalidJson: "The Overleaf endpoint {path} did not return valid JSON.",
      noProject: "No valid Overleaf project ID was found on this page.",
      invalidThreads: "The Overleaf comments endpoint returned an unrecognized data structure.",
      resolvedWarning: "The separate resolved list was unavailable; thread-level status was used instead",
      rangesWarning: "Comment anchors were unavailable; comments were exported without reliable filenames or line numbers",
      filesWarning: "The page did not expose the complete file tree; some files use document IDs as names",
      sourceWarning: "Could not download {file}; its comments were exported as unlocated discussions",
    },
  };
  let currentLanguage = "en";

  function tx(key, replacements = {}) {
    let value = TEXT[currentLanguage]?.[key] || TEXT.en[key] || key;
    for (const [name, replacement] of Object.entries(replacements)) {
      value = value.replaceAll(`{${name}}`, String(replacement));
    }
    return value;
  }

  class RequestError extends Error {
    constructor(message, status = null) {
      super(message);
      this.name = "RequestError";
      this.status = status;
    }
  }

  function projectIdFromPage() {
    const match = location.pathname.match(/\/project\/([0-9a-f]{24})(?:\/|$)/i);
    if (match) return match[1];
    for (const name of ["ol-project_id", "ol-projectId", "ol-project-id"]) {
      const value = document.querySelector(`meta[name="${name}"]`)?.content;
      if (value && /^[0-9a-f]{24}$/i.test(value)) return value;
    }
    return null;
  }

  function decodeMetaValue(rawValue) {
    if (rawValue === null || rawValue === undefined) return null;
    let value = String(rawValue).trim();
    for (let attempt = 0; attempt < 2 && value.includes("%"); attempt += 1) {
      try {
        const decoded = decodeURIComponent(value);
        if (decoded === value) break;
        value = decoded;
      } catch {
        break;
      }
    }
    if (!value) return "";
    if (/^[{[]/.test(value) || /^(true|false|null|-?\d)/.test(value)) {
      try {
        return JSON.parse(value);
      } catch {
        return value;
      }
    }
    return value;
  }

  function readMeta(...names) {
    for (const name of names) {
      const element = document.querySelector(`meta[name="${name}"]`);
      if (element) return decodeMetaValue(element.content);
    }
    return null;
  }


  // ---- Talking to the popup while the work happens ------------------------
  //
  // executeScript hands back one result at the end, so an export on a thesis
  // was a silent wait with no way out. These two send messages the popup
  // listens for: one to say where we are, one to ask whether to stop.
  //
  // If the popup has gone, sendMessage rejects. That is treated as a stop:
  // the popup is what writes the files, so work continued after it closes is
  // work nobody will ever see.

  function canMessage() {
    return typeof chrome === "object" && chrome?.runtime
      && typeof chrome.runtime.sendMessage === "function";
  }

  async function report(stage, done, total) {
    if (!canMessage()) return;
    try {
      await chrome.runtime.sendMessage({ oceProgress: { stage, done, total } });
    } catch {
      // The popup closed. Nothing to report to, and the next stop check
      // will end the export.
    }
  }

  async function stopRequested() {
    // No channel at all is not the same as a popup that has gone. Only an
    // actual rejection means nobody is listening; if messaging is simply
    // unavailable, carrying on is right.
    if (!canMessage()) return false;
    try {
      const answer = await chrome.runtime.sendMessage({ oceStopCheck: true });
      return Boolean(answer && answer.stop);
    } catch {
      return true;                 // popup gone: nobody is waiting for this
    }
  }

  class ExportStopped extends Error {}

  async function throwIfStopped() {
    if (await stopRequested()) throw new ExportStopped("stopped");
  }

  function readProjectMetadata(projectId) {
    const project = readMeta("ol-project");
    const titleFromMeta = readMeta("ol-projectName", "ol-project-name", "ol-project_name");
    let title = typeof titleFromMeta === "string" ? titleFromMeta : null;
    let filesRoot = null;
    let rootDocId = null;

    if (project && typeof project === "object") {
      title ||= project.name || project.projectName || null;
      filesRoot = project.rootFolder || project.root_folder || project.files || null;
      rootDocId = project.rootDocId || project.rootDoc_id || project.root_doc_id || null;
    }

    if (!title) {
      title = document.title
        .replace(/\s*[-–—|]\s*Overleaf.*$/i, "")
        .replace(/^Overleaf\s*[-–—|]\s*/i, "")
        .trim();
    }

    return {
      title: title || projectId,
      filesRoot,
      rootDocId,
    };
  }

  async function request(path, responseType = "json") {
    let response;
    try {
      response = await fetch(path, {
        method: "GET",
        credentials: "include",
        headers: {
          Accept: responseType === "json" ? "application/json, text/plain, */*" : "text/plain, */*",
        },
      });
    } catch (error) {
      throw new RequestError(tx("network", { detail: error?.message || String(error) }));
    }

    if (response.status === 401 || response.status === 403) {
      throw new RequestError(tx("forbidden"), response.status);
    }
    if (!response.ok) {
      throw new RequestError(tx("http", { path, status: response.status }), response.status);
    }

    if (responseType === "text") return response.text();
    try {
      return await response.json();
    } catch {
      throw new RequestError(tx("invalidJson", { path }), response.status);
    }
  }

  async function mapWithConcurrency(items, limit, worker) {
    const results = new Array(items.length);
    let nextIndex = 0;

    async function runWorker() {
      while (nextIndex < items.length) {
        const index = nextIndex;
        nextIndex += 1;
        results[index] = await worker(items[index], index);
      }
    }

    const workers = Array.from({ length: Math.min(limit, items.length) }, () => runWorker());
    await Promise.all(workers);
    return results;
  }

  function resolvedIdsFromPayload(payload) {
    if (Array.isArray(payload)) return payload.map(String);
    if (payload && Array.isArray(payload.resolvedThreadIds)) {
      return payload.resolvedThreadIds.map(String);
    }
    return [];
  }

  function outputFiles(exported, formats) {
    const date = new Date().toISOString().slice(0, 10);
    const markdownName = `comments-${date}.md`;
    const files = [];
    if (formats.markdown) {
      files.push({
        filename: markdownName,
        mimeType: "text/markdown;charset=utf-8",
        content: exported.markdown,
      });
    }
    if (formats.json) {
      files.push({
        filename: "comments.json",
        mimeType: "application/json;charset=utf-8",
        content: `${JSON.stringify(exported.payload, null, 2)}\n`,
      });
    }
    if (formats.xlsx && typeof OverleafCommentsXlsx !== "undefined") {
      const bytes = OverleafCommentsXlsx.build(core.buildSheetRows(exported.payload));
      let binary = "";
      for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
      files.push({
        filename: "comments.xlsx",
        mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        // executeScript can only hand back things that survive JSON, so the
        // bytes travel as base64 and become a blob again in the popup.
        base64: btoa(binary),
      });
    }
    if (formats.jsonl) {
      files.push({
        filename: "comments.jsonl",
        // Not application/x-ndjson: Chrome derives the extension from the
        // MIME type and renamed this to comments.ndjson, while the Markdown
        // front matter and agents.md both say comments.jsonl. octet-stream
        // maps to no extension, so the name we ask for is the name we get.
        mimeType: "application/octet-stream",
        content: exported.jsonl,
      });
    }
    // Always written, like the Python export does, because the Markdown front
    // matter names it and because it is what makes the folder legible to an
    // assistant.
    files.push({
      filename: "agents.md",
      mimeType: "text/markdown;charset=utf-8",
      content: core.renderAgentsBrief(exported.payload, markdownName),
    });
    if (formats.responseLetter) {
      files.push({
        filename: "response-letter.md",
        mimeType: "text/markdown;charset=utf-8",
        content: exported.responseLetter,
      });
    }
    return files;
  }

  async function collect(userOptions = {}) {
    currentLanguage = userOptions.language === "zh" ? "zh" : "en";
    const options = {
      language: currentLanguage,
      includeResolved: userOptions.includeResolved !== false,
      includeChanges: userOptions.includeChanges !== false,
      formats: {
        markdown: userOptions.formats?.markdown !== false,
        json: userOptions.formats?.json !== false,
        jsonl: Boolean(userOptions.formats?.jsonl),
        responseLetter: Boolean(userOptions.formats?.responseLetter),
      },
    };

    const projectId = projectIdFromPage();
    if (!projectId) {
      return { ok: false, error: tx("noProject") };
    }

    const warnings = [];
    const metadata = readProjectMetadata(projectId);

    const rawThreadsPayload = await request(`/project/${projectId}/threads`);
    const rawThreads = rawThreadsPayload?.threads && typeof rawThreadsPayload.threads === "object"
      ? rawThreadsPayload.threads
      : rawThreadsPayload;
    if (!rawThreads || Array.isArray(rawThreads) || typeof rawThreads !== "object") {
      throw new RequestError(tx("invalidThreads"));
    }

    let resolvedIds = [];
    try {
      resolvedIds = resolvedIdsFromPayload(await request(`/project/${projectId}/resolved-thread-ids`));
    } catch (error) {
      if (error.status !== 404) warnings.push(tx("resolvedWarning"));
    }

    let rangesPayload = null;
    try {
      rangesPayload = await request(`/project/${projectId}/ranges`);
    } catch (error) {
      if (error.status === 401 || error.status === 403) throw error;
      warnings.push(tx("rangesWarning"));
    }

    const docIdToPath = {};
    for (const entry of core.flattenFiles(metadata.filesRoot)) {
      docIdToPath[entry.docId] = entry.pathname;
    }
    if (!Object.keys(docIdToPath).length) {
      warnings.push(tx("filesWarning"));
    }

    const rangeEntries = core.documentRanges(rangesPayload);
    const docIds = [...new Set(
      rangeEntries
        .filter((entry) => entry.comments.length || (options.includeChanges && entry.changes.length))
        .map((entry) => entry.docId)
    )];
    // The root as well, even with no comments in it, because it names the
    // order the rest are read in.
    if (metadata.rootDocId && !docIds.includes(metadata.rootDocId)) {
      docIds.push(metadata.rootDocId);
    }
    const docTexts = {};
    let fetched = 0;
    await throwIfStopped();
    await report("files", 0, docIds.length);
    await mapWithConcurrency(docIds, 4, async (docId) => {
      try {
        docTexts[docId] = await request(`/Project/${projectId}/doc/${encodeURIComponent(docId)}/download`, "text");
      } catch (error) {
        const label = docIdToPath[docId] || docId;
        warnings.push(tx("sourceWarning", { file: label }));
      }
      fetched += 1;
      await report("files", fetched, docIds.length);
    });

    // Files with no comments in them still hold figures, and a figure decides
    // what number the next one gets. Follow the includes from the root and
    // fetch whatever is named but not yet read.
    const pathToDocId = {};
    for (const [id, path] of Object.entries(docIdToPath)) pathToDocId[path] = id;
    for (let pass = 0; pass < 8; pass += 1) {
      await throwIfStopped();
      const known = {};
      for (const [id, text] of Object.entries(docTexts)) {
        if (docIdToPath[id]) known[docIdToPath[id]] = text;
      }
      const wanted = [];
      for (const text of Object.values(known)) {
        for (const ref of core.findIncludes(text)) {
          const target = core.resolveInclude(ref, pathToDocId);
          const id = target ? pathToDocId[target] : null;
          if (id && !(id in docTexts) && !wanted.includes(id)) wanted.push(id);
        }
      }
      if (!wanted.length) break;
      await report("includes", 0, wanted.length);
      let got = 0;
      await mapWithConcurrency(wanted, 4, async (docId) => {
        try {
          docTexts[docId] = await request(`/Project/${projectId}/doc/${encodeURIComponent(docId)}/download`, "text");
        } catch {
          // Unreadable: assembleExport then claims no figure numbers rather
          // than numbers built on a gap.
        }
        got += 1;
        await report("includes", got, wanted.length);
      });
    }

    await throwIfStopped();
    await report("building", 0, 0);

    const exported = core.assembleExport({
      projectId,
      projectTitle: metadata.title,
      language: options.language,
      rawThreads,
      resolvedIds,
      rangesPayload,
      docTexts,
      docIdToPath,
      rootDocId: metadata.rootDocId,
      includeResolved: options.includeResolved,
      includeChanges: options.includeChanges,
    });

    const summary = exported.payload.summary;
    return {
      ok: true,
      project: exported.payload.project,
      generatedAt: exported.payload.pulled_at,
      summary: {
        threadCount: summary.thread_count,
        openCount: summary.open_count,
        resolvedCount: summary.resolved_count,
        trackedChangeCount: summary.tracked_change_count,
        staleAnchorCount: summary.stale_anchor_count,
      },
      warnings: [...new Set(warnings)],
      outputs: outputFiles(exported, options.formats),
    };
  }

  root.__overleafCommentsExtension = {
    version: VERSION,
    collect,
  };
})(globalThis);
