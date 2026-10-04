"use strict";

// The background's hands. A service worker has no URL.createObjectURL, which
// turning an export into downloadable files needs, and no localStorage, where
// the popup has always kept the last export of each paper. This page has both,
// and being the same extension it shares that localStorage with the popup, so
// snapshots saved before the export moved here are still found.

// One snapshot of the last export per paper, so the next one can say what
// changed. Kept in localStorage rather than chrome.storage because that would
// mean adding the storage permission to the manifest.
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

function blobUrl({ content, base64, mimeType }) {
  const body = base64 ? Uint8Array.from(atob(base64), (ch) => ch.charCodeAt(0)) : content;
  return URL.createObjectURL(new Blob([body], { type: mimeType }));
}

globalThis.chrome?.runtime?.onMessage?.addListener((message, _sender, respond) => {
  if (message?.target !== "offscreen") return false;
  if (message.type === "blobs") respond(message.files.map(blobUrl));
  else if (message.type === "loadSnapshot") respond(loadSnapshot(message.projectId));
  else if (message.type === "saveSnapshot") respond(saveSnapshot(message.projectId, message.snapshot) ?? true);
  return false;
});

if (typeof module === "object" && module.exports) module.exports = { loadSnapshot, saveSnapshot, blobUrl };
