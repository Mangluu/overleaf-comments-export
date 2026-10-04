// Real Chrome, real extension, a fake overleaf.com. Run before every upload.
//
//   cd browser-extension/e2e && npm install && npx puppeteer browsers install chrome && npm run e2e
//
// Two passes. The first gives the test build localhost access so it can drive
// the background directly. The second is the shipped manifest untouched, with
// access only from the real toolbar action, as for a person.
const fs = require("fs");
const path = require("path");
const { start } = require("./fake-overleaf");
const { launch, listDownloads, shutdown } = require("./harness");

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function waitFor(check, ms = 20000) {
  const end = Date.now() + ms;
  for (;;) { const v = await check(); if (v) return v; if (Date.now() > end) return v; await sleep(150); }
}
let failures = 0;
const check = (label, ok, detail = "") => { console.log(`${ok ? "PASS" : "FAIL"}  ${label}${detail ? `  (${detail})` : ""}`); if (!ok) failures += 1; };

async function backgroundExport() {
  const site = await start();
  const { browser, worker, extensionId, downloads } = await launch();
  try {
    const project = await browser.newPage();
    await project.goto(site.projectUrl);
    const tabId = await worker.evaluate(async (url) => (await chrome.tabs.query({})).find((t) => t.url === url).id, site.projectUrl);
    const options = { language: "en", includeResolved: true, includeChanges: true, formats: { markdown: true, json: true, xlsx: true, jsonl: false, responseLetter: false } };

    // Start an export the way the popup does, from an extension page, and
    // close that page at once, the way a popup closes on a stray click.
    async function exportAndClosePopup(extra = {}) {
      const popup = await browser.newPage();
      await popup.goto(`chrome-extension://${extensionId}/popup.html`);
      const reply = await popup.evaluate((m) => chrome.runtime.sendMessage(m),
        { target: "background", type: "export", tabId, url: site.projectUrl, options: { ...options, ...extra } });
      await popup.close();
      return reply;
    }
    const job = () => worker.evaluate((id) => { const j = jobs.get(id); return j && { state: j.state, error: j.error, folder: j.folder, files: j.files }; }, tabId);
    const finished = () => waitFor(async () => { const j = await job(); return j && j.state !== "running" ? j : null; });
    const filesIn = (folder) => listDownloads(downloads).filter((f) => f.startsWith(folder + "/"));

    // 1. The popup is gone before the export even starts working.
    const reply = await exportAndClosePopup();
    check("the background accepted the export", reply?.ok === true, JSON.stringify(reply));
    let done = await finished();
    check("export finished with the popup closed", done?.state === "done", JSON.stringify(done));
    const first = done.folder;
    await waitFor(() => filesIn(first).length === 4);
    const got = filesIn(first).map((f) => path.basename(f));
    check("every file arrived", got.length === 4, got.join(", "));
    const json = JSON.parse(fs.readFileSync(path.join(downloads, first, "comments.json"), "utf8"));
    check("comments.json is whole and filed by real names", json.comments.every((c) => !c.pathname.startsWith("<unknown")), json.comments.map((c) => c.pathname).join(", "));
    const xlsx = fs.readFileSync(path.join(downloads, first, "comments.xlsx"));
    check("the spreadsheet is a real zip", xlsx.subarray(0, 2).toString() === "PK", `${xlsx.length} bytes`);
    const open = await worker.evaluate(async () => (await chrome.runtime.getContexts({ contextTypes: ["OFFSCREEN_DOCUMENT"] })).length);
    check("the offscreen page was closed afterwards", open === 0, `${open} open`);

    // 2. The second export compares with the first, through the offscreen page's storage.
    await sleep(1100);
    await exportAndClosePopup();
    done = await finished();
    await waitFor(() => filesIn(done.folder).some((f) => f.endsWith("whats-new.md")));
    check("the second export says what changed", filesIn(done.folder).some((f) => f.endsWith("whats-new.md")), filesIn(done.folder).map((f) => path.basename(f)).join(", "));

    // 3. Past the 2 MB a data URL can carry.
    site.state.bulk = 1800;
    await sleep(1100);
    await exportAndClosePopup({ formats: { markdown: true, json: true } });
    done = await finished();
    const bigPath = path.join(downloads, done.folder, "comments.json");
    await waitFor(() => fs.existsSync(bigPath));
    await sleep(500);
    const big = fs.readFileSync(bigPath, "utf8");
    let parsed = null; try { parsed = JSON.parse(big); } catch {}
    check("a comments.json over 2 MB arrives whole", Boolean(parsed) && big.length > 2 * 1024 * 1024, `${(big.length / 1048576).toFixed(1)} MB, ${parsed ? parsed.comments.length + " comments" : "unparsable"}`);
    site.state.bulk = 0;

    // 4. Signed out: the page's own words reach the reader.
    site.state.threadsStatus = 401;
    await exportAndClosePopup();
    done = await finished();
    check("a signed-out tab is told it is signed out", done.state === "failed" && /not signed in/i.test(done.error || ""), done.error);
    site.state.threadsStatus = 200;

    // 5. Stop, mid-export.
    site.state.slowMs = 1500;
    await exportAndClosePopup();
    await sleep(400);
    const popup = await browser.newPage();
    await popup.goto(`chrome-extension://${extensionId}/popup.html`);
    await popup.evaluate((m) => chrome.runtime.sendMessage(m), { target: "background", type: "stop", tabId });
    await popup.close();
    done = await finished();
    check("Stop stops it, and says so", done.state === "stopped", JSON.stringify(done));
    site.state.slowMs = 0;

    // 6. Titles Chrome used to refuse.
    const titles = {
      "90th character is a space": "A".repeat(89) + " long academic title",
      "emoji with a zero-width joiner": "Lab notes \u{1F469}‍\u{1F52C}",
      "soft hyphen": "Inter­action",
      "leading dot": ".NET performance study",
      "leading tilde": "~Draft",
      "right-to-left mark": "מחקר‏ study",
      "Windows device name": "Aux",
    };
    for (const [label, title] of Object.entries(titles)) {
      site.state.title = title;
      await project.reload();
      await sleep(1100);
      await exportAndClosePopup({ formats: { markdown: true } });
      done = await finished();
      const ok = done.state === "done" && (await waitFor(() => filesIn(done.folder).length > 0, 5000));
      check(`a paper titled with a ${label} exports`, Boolean(ok), done.state === "done" ? done.folder.split("/")[1] : done.error);
    }
  } finally {
    await shutdown(browser);
    site.server.close();
  }
}

async function shippedBuild() {
  const site = await start();
  const { browser, worker, extensionId, downloads } = await launch({ hostPermissions: false });
  const pageErrors = [];
  try {
    const manifest = await worker.evaluate(() => chrome.runtime.getManifest());
    check("the build under test has no host permissions", !manifest.host_permissions, JSON.stringify(manifest.permissions));
    const extension = (await browser.extensions()).get(extensionId);
    const project = await browser.newPage();
    await project.goto(site.projectUrl);
    await project.bringToFront();
    const tabId = await worker.evaluate(async () => (await chrome.tabs.query({ active: true, lastFocusedWindow: true }))[0]?.id);

    // The action click grants activeTab, as it does for a person. Headless has
    // no toolbar to draw the popup in, so the real popup page is opened in a
    // tab and told which tab is active. Everything else is real.
    await extension.triggerAction(project);
    const projectTab = { id: tabId, url: site.projectUrl, title: await project.title() };
    async function openPopup() {
      const popup = await browser.newPage();
      await popup.evaluateOnNewDocument((tab) => {
        chrome.tabs.query = async () => [tab];
      }, projectTab);
      popup.on("pageerror", (e) => pageErrors.push(e.message));
      popup.on("console", (m) => { if (m.type() === "error") pageErrors.push(m.text()); });
      await popup.goto(`chrome-extension://${extensionId}/popup.html`);
      return popup;
    }
    const job = () => worker.evaluate((id) => { const j = jobs.get(id); return j && { state: j.state, error: j.error, folder: j.folder }; }, tabId);

    // 1. Click the icon, press Export, and close the popup at once.
    let popup = await openPopup();
    const ready = await waitFor(() => popup.$eval("#page-state", (e) => e.textContent).catch(() => ""), 10000);
    check("the popup recognises the Overleaf project", /project detected/i.test(ready), ready);
    await popup.waitForFunction(() => !document.getElementById("export").disabled, { timeout: 10000 });
    await popup.evaluate(() => document.getElementById("export").click());
    await popup.close();
    const done = await waitFor(async () => { const j = await job(); return j && j.state !== "running" ? j : null; });
    check("activeTab carries the export after the popup has closed", done?.state === "done", JSON.stringify(done));
    if (done?.folder) {
      await waitFor(() => listDownloads(downloads).filter((f) => f.startsWith(done.folder)).length >= 3);
      const files = listDownloads(downloads).filter((f) => f.startsWith(done.folder)).map((f) => path.basename(f));
      check("the files arrived", files.length >= 3, files.join(", "));
    }

    // 2. A slow export: reopen the popup mid-way, see it running, press Stop.
    site.state.slowMs = 2500;
    popup = await openPopup();
    await popup.waitForFunction(() => !document.getElementById("export").disabled, { timeout: 10000 });
    await popup.evaluate(() => document.getElementById("export").click());
    await popup.close();
    await sleep(500);
    popup = await openPopup();
    const running = await waitFor(() => popup.evaluate(() => !document.getElementById("stop").hidden && document.getElementById("export").disabled).catch(() => false), 5000);
    check("a reopened popup shows the export still running, with Stop", Boolean(running));
    await popup.evaluate(() => document.getElementById("stop").click());
    const stopped = await waitFor(() => popup.evaluate(() => document.getElementById("result").textContent).catch(() => ""), 15000);
    check("Stop, pressed in the real popup, ends it and says so", /stopped/i.test(stopped), stopped);
    await popup.close();
    site.state.slowMs = 0;

    // 3. The real popup, signed out.
    site.state.threadsStatus = 401;
    popup = await openPopup();
    await popup.waitForFunction(() => !document.getElementById("export").disabled, { timeout: 10000 });
    await popup.evaluate(() => document.getElementById("export").click());
    // Wait for the new result to be shown, not the last export's, still in the DOM.
    const failed = await waitFor(() => popup.evaluate(() => {
      const r = document.getElementById("result");
      return !r.hidden && /signed in/i.test(r.textContent) ? r.textContent : "";
    }).catch(() => ""), 15000) || await popup.evaluate(() => document.getElementById("result").textContent);
    check("the real popup says the reader is signed out", /not signed in/i.test(failed), failed);
    await popup.close();
    site.state.threadsStatus = 200;

    check("no errors in the popup", pageErrors.length === 0, pageErrors.join(" | "));
  } finally {
    await shutdown(browser);
    site.server.close();
  }
}

(async () => {
  console.log("-- the background export --");
  await backgroundExport();
  console.log("-- the shipped build, through the toolbar action --");
  await shippedBuild();
  console.log(failures ? `\n${failures} FAILED` : "\nall passed");
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error("RUN FAILED", e); process.exit(1); });
