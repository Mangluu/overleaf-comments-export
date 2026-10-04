// Launch Chrome for Testing with a copy of the extension that may also run on
// localhost, which is the only change from the shipped build.
const fs = require("fs");
const os = require("os");
const path = require("path");
const puppeteer = require("puppeteer");

const EXT_SRC = path.join(__dirname, "..");

async function launch({ hostPermissions = true } = {}) {
  const work = fs.mkdtempSync(path.join(os.tmpdir(), "oce-e2e-"));
  const ext = path.join(work, "ext");
  fs.cpSync(EXT_SRC, ext, { recursive: true, filter: (p) => !/node_modules|tests|e2e|preview/.test(p) });
  const manifest = JSON.parse(fs.readFileSync(path.join(ext, "manifest.json"), "utf8"));
  // Only for tests that skip the toolbar. Without it the build is exactly the
  // shipped one, and access comes from activeTab, as it does for a person.
  if (hostPermissions) manifest.host_permissions = ["http://localhost/*", "http://127.0.0.1/*"];
  fs.writeFileSync(path.join(ext, "manifest.json"), JSON.stringify(manifest, null, 2));

  const downloads = path.join(work, "downloads");
  const profile = path.join(work, "profile");
  fs.mkdirSync(path.join(profile, "Default"), { recursive: true });
  fs.mkdirSync(downloads);
  fs.writeFileSync(path.join(profile, "Default", "Preferences"), JSON.stringify({
    download: { default_directory: downloads, prompt_for_download: false, directory_upgrade: true },
  }));

  const browser = await puppeteer.launch({
    // Chrome for Testing. Branded Chrome ignores --load-extension since 137.
    executablePath: process.env.CHROME || puppeteer.executablePath(),
    headless: true,
    pipe: true,
    userDataDir: profile,
    enableExtensions: [ext],
    args: ["--no-first-run", "--no-default-browser-check"],
  });
  const target = await browser.waitForTarget((t) => t.type() === "service_worker" && t.url().startsWith("chrome-extension://"), { timeout: 15000 });
  const worker = await target.worker();
  const extensionId = new URL(target.url()).host;
  return { browser, worker, extensionId, downloads, work };
}

// Files that finished downloading, by path relative to the download folder.
function listDownloads(dir) {
  const out = [];
  const walk = (d) => { for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, e.name);
    if (e.isDirectory()) walk(p); else if (!/\.crdownload$/.test(e.name)) out.push(path.relative(dir, p));
  } };
  walk(dir);
  return out.sort();
}

// Chrome can sit on close with an extension service worker alive. Give it a
// moment, then end it.
async function shutdown(browser) {
  await Promise.race([browser.close(), new Promise((r) => setTimeout(r, 3000))]);
  try { browser.process()?.kill("SIGKILL"); } catch {}
}

module.exports = { launch, listDownloads, shutdown };
