(function attachOverleafPageClient(root) {
  "use strict";

  // No "already injected" guard. There used to be one, keyed on a version
  // string nobody remembered to bump, so after an update a tab could keep
  // answering with the old collect(). Defining it again costs nothing.

  const core = root.OverleafCommentsCore;
  if (!core) throw new Error("OverleafCommentsCore was not loaded before page-client.js.");

  const TEXT = {
    zh: {
      notSignedIn: "当前标签页尚未登录 Overleaf。请登录并重新加载项目后再试。",
      network: "无法连接 Overleaf：{detail}",
      forbidden: "Overleaf 拒绝了请求。请确认当前标签页已经登录且有权访问这个项目。",
      http: "Overleaf 接口 {path} 返回 HTTP {status}。",
      invalidJson: "Overleaf 接口 {path} 没有返回有效 JSON。",
      noProject: "当前页面没有有效的 Overleaf project ID。",
      invalidThreads: "Overleaf 的评论接口返回了无法识别的数据结构。",
      resolvedWarning: "无法读取独立的 resolved 列表，已使用 thread 自带状态",
      rangesWarning: "无法读取评论锚点，评论仍会导出但可能没有文件名和行号",
      filesWarning: "部分文件无法确定文件名，将使用文档 ID 命名",
      sourceWarning: "无法下载源文件 {file}，相关评论将作为未定位讨论导出",
      noOpenDoc: "无法确定当前打开的是哪个文件。请在左侧文件列表中点击该文件，或取消勾选“仅当前文件”。",
    },
    en: {
      notSignedIn: "This tab is not signed in to Overleaf. Sign in, reload the project, then try again.",
      network: "Could not connect to Overleaf: {detail}",
      forbidden: "Overleaf rejected the request. Make sure this tab is signed in and the account can access the project.",
      http: "The Overleaf endpoint {path} returned HTTP {status}.",
      invalidJson: "The Overleaf endpoint {path} did not return valid JSON.",
      noProject: "No valid Overleaf project ID was found on this page.",
      invalidThreads: "The Overleaf comments endpoint returned an unrecognized data structure.",
      resolvedWarning: "The separate resolved list was unavailable; thread-level status was used instead",
      rangesWarning: "Comment anchors were unavailable; comments were exported without reliable filenames or line numbers",
      filesWarning: "Some files could not be named, so they use document IDs instead",
      sourceWarning: "Could not download {file}; its comments were exported as unlocated discussions",
      noOpenDoc: "Could not tell which file is open. Click it in the file list on the left, or untick This file only.",
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


  // ---- Talking to the extension while the work happens --------------------
  //
  // executeScript hands back one result at the end, so an export on a thesis
  // was a silent wait with no way out. These two send messages: one to say
  // where we are, which the popup shows if it is open, and one to ask the
  // background whether to stop.
  //
  // The background owns the export, so a popup that has closed changes
  // nothing. Only a rejected stop check means nobody is waiting, for example
  // after the extension was updated mid-export, and that is treated as a stop.

  function canMessage() {
    return typeof chrome === "object" && chrome?.runtime
      && typeof chrome.runtime.sendMessage === "function";
  }

  async function report(stage, done, total) {
    if (!canMessage()) return;
    try {
      await chrome.runtime.sendMessage({ oceProgress: { stage, done, total } });
    } catch {
      // Nobody listening for progress is fine. The stop check decides.
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
      return true;                 // nobody is waiting for this any more
    }
  }

  class ExportStopped extends Error {
    constructor() {
      super("stopped");
      this.name = "ExportStopped";
    }
  }

  async function throwIfStopped() {
    if (await stopRequested()) throw new ExportStopped();
  }

  function signedIn() {
    // Overleaf puts the current user in the page for its own use. Reading it
    // is how we can say "you are not signed in" up front, instead of letting
    // the first request come back 401 and reporting that Overleaf "rejected"
    // it, which sounds like a permissions problem with the project.
    const user = readMeta("ol-user", "ol-currentUser", "ol-current-user");
    if (user && typeof user === "object") {
      return Boolean(user.id || user._id || user.email);
    }
    // No tag is not proof of anything. Overleaf renames these, and guessing
    // from the DOM would turn a working export into a false refusal, so
    // anything other than an explicit user means carry on and let the
    // response decide.
    return true;
  }

  // "This file only" means the document open in the editor. Older pages put
  // its id in the address or in a meta tag. Today's file list marks the open
  // item aria-selected, and the element carrying data-file-id is the first
  // thing inside that item, ahead of any folder contents. See
  // file-tree-doc.tsx and file-tree-item-inner.tsx in overleaf/overleaf.
  function openDocFromPage() {
    const legacy = (location.pathname.match(/\/doc\/([0-9a-f]{24})/i) || [])[1]
      || readMeta("ol-openDocId");
    if (legacy) return String(legacy);
    const open = [];
    for (const item of document.querySelectorAll?.('li[role="treeitem"][aria-selected="true"]') || []) {
      const entity = item.querySelector?.("[data-file-id]");
      if (entity?.getAttribute("data-file-type") === "doc") open.push(entity.getAttribute("data-file-id"));
    }
    return open.length === 1 ? open[0] : null;
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

    if (response.status === 401) {
      throw new RequestError(tx("notSignedIn"), 401);
    }
    if (response.status === 403) {
      throw new RequestError(tx("forbidden"), response.status);
    }
    if (!response.ok) {
      throw new RequestError(tx("http", { path, status: response.status }), response.status);
    }

    // A document download names its file in this header, and on today's
    // Overleaf that is the only place the name is to be had.
    if (responseType === "doc") {
      return {
        text: await response.text(),
        name: core.fileNameFromDisposition(response.headers.get("content-disposition")),
      };
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

  function outputFiles(exported, formats, previousSnapshot) {
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
    // What changed since the last export of this paper. The previous
    // snapshot is passed in by the popup, which is what keeps it.
    if (previousSnapshot) {
      const since = core.compareExports(previousSnapshot, exported.payload);
      files.push({
        filename: "whats-new.md",
        mimeType: "text/markdown;charset=utf-8",
        content: core.renderSinceMarkdown(since, exported.payload.project.title),
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

  // Chrome does not pass on anything thrown inside an injected script.
  // ProgrammaticScriptInjector::OnInjectionComplete in Chromium finishes with
  // an empty error whatever happened, so executeScript resolves with a null
  // result. Every message below, "not signed in" among them, used to arrive
  // as that null, and the reader saw "did not return a valid result" instead.
  // So collect never throws. It hands any failure back as data.
  async function collect(userOptions = {}) {
    try {
      return await collectOrThrow(userOptions);
    } catch (error) {
      return {
        ok: false,
        error: error?.message || String(error),
        status: error?.status ?? null,
        stopped: error instanceof ExportStopped,
      };
    }
  }

  async function collectOrThrow(userOptions) {
    currentLanguage = userOptions.language === "zh" ? "zh" : "en";
    // Everything the popup sends, normalised. In 1.7.0 this was rebuilt from
    // a list older than four of the popup's options, so Spreadsheet, This file
    // only, One person and the comparison with the last export all reached
    // this point and were dropped without a word.
    const options = {
      language: currentLanguage,
      includeResolved: userOptions.includeResolved !== false,
      includeChanges: userOptions.includeChanges !== false,
      currentFileOnly: Boolean(userOptions.currentFileOnly),
      reviewer: String(userOptions.reviewer || "").trim(),
      previousSnapshot: userOptions.previousSnapshot || null,
      formats: {
        markdown: userOptions.formats?.markdown !== false,
        json: userOptions.formats?.json !== false,
        jsonl: Boolean(userOptions.formats?.jsonl),
        xlsx: Boolean(userOptions.formats?.xlsx),
        responseLetter: Boolean(userOptions.formats?.responseLetter),
      },
    };

    const projectId = projectIdFromPage();
    if (!projectId) {
      return { ok: false, error: tx("noProject") };
    }

    const warnings = [];
    // Said before the first request rather than after it fails, when the
    // page itself already knows the answer.
    if (!signedIn()) throw new RequestError(tx("notSignedIn"), 401);

    const metadata = readProjectMetadata(projectId);
    let rootDocId = metadata.rootDocId;

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

    // Only older pages carry the tree. On today's Overleaf this stays empty
    // and the names are worked out further down instead.
    const docIdToPath = {};
    for (const entry of core.flattenFiles(metadata.filesRoot)) {
      docIdToPath[entry.docId] = entry.pathname;
    }

    const rangeEntries = core.documentRanges(rangesPayload);
    // "This file only" narrows to the document open in the editor. On a
    // thesis it is the difference between one chapter and the whole book.
    const openDocId = options.currentFileOnly ? openDocFromPage() : null;
    if (options.currentFileOnly && !openDocId) {
      // Exporting the whole paper instead is the silent failure this replaces.
      return { ok: false, error: tx("noOpenDoc") };
    }
    const docIds = [...new Set(
      rangeEntries
        .filter((entry) => !openDocId || entry.docId === openDocId)
        .filter((entry) => entry.comments.length || (options.includeChanges && entry.changes.length))
        .map((entry) => entry.docId)
    )];
    // The root as well, even with no comments in it, because it names the
    // order the rest are read in.
    if (rootDocId && !docIds.includes(rootDocId)) docIds.push(rootDocId);

    const docTexts = {};
    const docNames = {};
    let read = 0;
    let toRead = docIds.length;
    // warn is off for files read only to put the paper in order. They have no
    // comments to lose, so a failure there costs the numbering, which
    // assembleExport already withholds rather than guesses.
    async function readDocs(ids, { warn = true } = {}) {
      await throwIfStopped();
      await report("files", read, toRead);
      await mapWithConcurrency(ids, 4, async (docId) => {
        try {
          const doc = await request(`/Project/${projectId}/doc/${encodeURIComponent(docId)}/download`, "doc");
          docTexts[docId] = doc.text;
          if (doc.name) docNames[docId] = doc.name;
        } catch {
          if (warn) warnings.push(tx("sourceWarning", { file: docIdToPath[docId] || docId }));
        }
        read += 1;
        await report("files", read, toRead);
      });
    }
    await readDocs(docIds);

    if (!Object.keys(docIdToPath).length) {
      // Today's Overleaf. Each download named its own file, and this lists
      // every path in the project, which supplies the folders.
      let docPaths = [];
      try {
        const listing = await request(`/project/${projectId}/entities`);
        docPaths = (listing?.entities || [])
          .filter((entity) => entity?.type === "doc" && typeof entity.path === "string")
          .map((entity) => entity.path.replace(/^\/+/, ""));
      } catch (error) {
        if (error.status === 401 || error.status === 403) throw error;
        // Names without their folders are still far better than ids.
      }
      // A paper in several files is only put in order, and its figures only
      // numbered, if every part is read, the parts with no comments included.
      // They are small text files, and nothing else says which one is the root.
      if (!rootDocId && docPaths.filter((path) => /\.tex$/i.test(path)).length > 1) {
        const rest = [...new Set(rangeEntries.map((entry) => entry.docId))]
          .filter((docId) => !(docId in docTexts));
        toRead += rest.length;
        await readDocs(rest, { warn: false });
      }
      Object.assign(docIdToPath, core.placeDocs(docNames, docPaths));
      if (!rootDocId) {
        const textsByPath = {};
        for (const [docId, text] of Object.entries(docTexts)) {
          if (docIdToPath[docId]) textsByPath[docIdToPath[docId]] = text;
        }
        const rootPath = core.pickRootPath(textsByPath);
        rootDocId = Object.keys(docIdToPath).find((docId) => docIdToPath[docId] === rootPath) || null;
      }
    }
    if (Object.keys(docTexts).some((docId) => !docIdToPath[docId])) {
      warnings.push(tx("filesWarning"));
    }

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

    // Narrowed to one file, a thread anchored in another file is simply not
    // part of this export. Left in, assembleExport never sees its anchor and
    // files it under threads that "could not be mapped to live source text",
    // which is false. A thread anchored nowhere at all stays, since it could
    // just as well belong here.
    let threadsInScope = rawThreads;
    if (openDocId) {
      const elsewhere = new Set();
      for (const entry of rangeEntries) {
        if (entry.docId === openDocId) continue;
        for (const comment of entry.comments) {
          const threadId = comment?.op?.t || comment?.t;
          if (threadId) elsewhere.add(String(threadId));
        }
      }
      threadsInScope = Object.fromEntries(
        Object.entries(rawThreads).filter(([threadId]) => !elsewhere.has(threadId)));
    }

    const exported = core.assembleExport({
      projectId,
      projectTitle: metadata.title,
      language: options.language,
      rawThreads: threadsInScope,
      resolvedIds,
      rangesPayload: openDocId
        ? rangeEntries.filter((e) => e.docId === openDocId)
          .map((e) => ({ id: e.docId, ranges: { comments: e.comments, changes: e.changes } }))
        : rangesPayload,
      docTexts,
      docIdToPath,
      rootDocId,
      includeResolved: options.includeResolved,
      reviewer: options.reviewer || "",
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
      // Handed back so the popup can store it for next time.
      snapshot: core.sinceSnapshot(exported.payload),
      outputs: outputFiles(exported, options.formats, options.previousSnapshot),
    };
  }

  root.__overleafCommentsExtension = {
    version: core.TOOL_VERSION,
    collect,
  };
})(globalThis);
