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

if (typeof module === "object" && module.exports) module.exports = { uninstallUrl, UNINSTALL_PAGE };
