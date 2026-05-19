from __future__ import annotations

import html
import json
import logging
import re
from typing import Any, Optional
from urllib.parse import unquote, urlparse

import requests

logger = logging.getLogger(__name__)

OVERLEAF_BASE = "https://www.overleaf.com"

PROJECT_URL_RE = re.compile(r"/project/(?P<id>[0-9a-fA-F]{24})")


def parse_project_id(project_url: str) -> str:
    parsed = urlparse(project_url)
    m = PROJECT_URL_RE.search(parsed.path)
    if not m:
        raise ValueError(
            f"Could not extract a 24-char project id from URL: {project_url!r}. "
            "Expected something like https://www.overleaf.com/project/<24-hex-chars>."
        )
    return m.group("id")


class OverleafClient:
    """Thin wrapper around pyoverleaf for cookie auth + a few extra endpoints
    (threads, ranges, plain-text doc download, file tree)."""

    def __init__(self, base_url: str = OVERLEAF_BASE) -> None:
        self.base_url = base_url.rstrip("/")
        self._api = None
        self._session: Optional[requests.Session] = None

    SUPPORTED_BROWSERS = ("safari", "firefox", "auto", "chrome", "chromium", "edge", "brave")
    # Browsers that don't trigger macOS Keychain or password prompts:
    PRIVACY_FRIENDLY_BROWSERS = ("safari", "firefox")

    def connect(self, browser: str = "auto") -> None:
        """Authenticate via the user's browser cookie.

        If browser is "auto", we let pyoverleaf auto-detect.
        Otherwise we read the overleaf.com cookies for the named browser
        directly via browser-cookie3 and build our own session.
        """
        browser = (browser or "auto").lower()
        if browser not in self.SUPPORTED_BROWSERS:
            raise ValueError(
                f"Unsupported browser {browser!r}. Choose one of: "
                + ", ".join(self.SUPPORTED_BROWSERS)
            )

        if browser == "auto":
            session = self._connect_via_pyoverleaf()
        else:
            session = self._connect_via_browser_cookie3(browser)

        session.headers.setdefault(
            "User-Agent",
            "overleaf-comments-export/0.1 (Mozilla/5.0 compatible)",
        )
        session.headers.setdefault("Accept", "application/json, text/plain, */*")
        session.headers.setdefault("Referer", f"{self.base_url}/")
        self._session = session

    def _connect_via_pyoverleaf(self) -> requests.Session:
        try:
            import pyoverleaf  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "pyoverleaf is not installed. Install it with `pip install pyoverleaf`."
            ) from e

        api = pyoverleaf.Api()
        try:
            api.login_from_browser()
        except Exception as e:
            raise RuntimeError(
                "Could not read an Overleaf session cookie from any browser. "
                "Open https://www.overleaf.com in Chrome or Firefox, sign in, then "
                "re-run this tool. Or pick a specific browser in the dropdown."
            ) from e
        self._api = api
        return self._extract_session(api)

    def _connect_via_browser_cookie3(self, browser: str) -> requests.Session:
        try:
            import browser_cookie3  # type: ignore
        except ImportError as e:
            import sys
            raise RuntimeError(
                f"browser-cookie3 could not be imported by this Python "
                f"({sys.executable}). Underlying error: {e}. "
                "If this is the bundled .app, try quitting and relaunching it — "
                "the launcher will reinstall dependencies on the next start."
            ) from e

        loader = getattr(browser_cookie3, browser, None)
        if loader is None:
            raise RuntimeError(
                f"browser-cookie3 has no loader for {browser!r}. Available: "
                + ", ".join(n for n in dir(browser_cookie3) if not n.startswith("_"))
            )

        try:
            jar = loader(domain_name="overleaf.com")
        except Exception as e:
            raise RuntimeError(
                f"Could not read Overleaf cookies from {browser}. Make sure {browser} "
                "is installed and you are signed in to overleaf.com in it. On macOS, "
                "browsers like Chrome may require granting Terminal/the launcher app "
                "Full Disk Access in System Settings → Privacy & Security to read "
                "their cookie store."
            ) from e

        session_cookie = next(
            (c for c in jar if c.name in ("overleaf_session2", "overleaf.sid")),
            None,
        )
        if session_cookie is None:
            raise RuntimeError(
                f"No Overleaf session cookie found in {browser}. Sign in to "
                "https://www.overleaf.com in that browser and retry."
            )

        session = requests.Session()
        session.cookies.update(jar)

        try:
            import pyoverleaf  # type: ignore
            api = pyoverleaf.Api()
            api.login_from_browser()
            self._api = api
        except Exception as e:
            logger.warning(
                "pyoverleaf init failed (file tree may be unavailable, paths will "
                "fall back to <unknown-doc-id>): %s",
                e,
            )
            self._api = None

        return session

    @staticmethod
    def _extract_session(api: Any) -> requests.Session:
        for attr in ("_session", "session", "_client", "client"):
            candidate = getattr(api, attr, None)
            if isinstance(candidate, requests.Session):
                return candidate
        for attr in dir(api):
            try:
                candidate = getattr(api, attr)
            except Exception:
                continue
            if isinstance(candidate, requests.Session):
                return candidate
        raise RuntimeError(
            "Could not find a requests.Session on the pyoverleaf Api object. "
            "This tool may need to be updated for the installed pyoverleaf version."
        )

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            raise RuntimeError("call connect() before using the client")
        return self._session

    def _get(self, path: str, expect_json: bool = True) -> Any:
        url = f"{self.base_url}{path}"
        r = self.session.get(url, timeout=30)
        if r.status_code in (401, 403):
            raise RuntimeError(
                f"Overleaf returned {r.status_code} for {path}. Your session may have "
                "expired or you may not have access to this project. Refresh the "
                "Overleaf tab in your browser and re-run."
            )
        r.raise_for_status()
        if not expect_json:
            return r.text
        ctype = r.headers.get("Content-Type", "")
        if "application/json" not in ctype:
            raise RuntimeError(
                f"Expected JSON from {path} but got Content-Type={ctype!r}. "
                "This usually means the endpoint moved or you got redirected to login."
            )
        return r.json()

    def get_threads(self, project_id: str) -> dict[str, Any]:
        """GET /project/:id/threads -> dict keyed by thread_id."""
        data = self._get(f"/project/{project_id}/threads")
        if not isinstance(data, dict):
            raise RuntimeError(f"Unexpected /threads response shape: {type(data).__name__}")
        return data

    def get_resolved_thread_ids(self, project_id: str) -> list[str]:
        try:
            data = self._get(f"/project/{project_id}/resolved-thread-ids")
        except Exception as e:
            logger.warning("resolved-thread-ids fetch failed: %s", e)
            return []
        if isinstance(data, dict) and "resolvedThreadIds" in data:
            return list(data["resolvedThreadIds"])
        if isinstance(data, list):
            return list(data)
        return []

    def get_project_ranges(self, project_id: str) -> Optional[dict[str, Any]]:
        """GET /project/:id/ranges -> { docs: [{ id, ranges: { comments, changes } }] }.
        Returns None if the endpoint isn't accessible (e.g. 404 on older deployments)."""
        try:
            return self._get(f"/project/{project_id}/ranges")
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                logger.warning(
                    "/project/%s/ranges returned 404 — anchors and tracked changes "
                    "will be omitted from the export.",
                    project_id,
                )
                return None
            raise
        except RuntimeError as e:
            logger.warning("ranges fetch failed: %s", e)
            return None

    def download_doc_text(self, project_id: str, doc_id: str) -> str:
        """GET /Project/:id/doc/:doc_id/download -> plain text body."""
        return self._get(
            f"/Project/{project_id}/doc/{doc_id}/download", expect_json=False
        )

    def get_project_metadata(self, project_id: str) -> dict[str, Any]:
        """Best-effort fetch of project name + file tree.

        Tries (in order): pyoverleaf socket call, then an HTML scrape of the
        project editor page (parses <meta name="ol-*"> tags). The two paths
        return different shapes; we merge them.
        """
        result: dict[str, Any] = {"files": None, "name": None, "rootDocId": None, "raw_meta": {}}

        api = self._api
        if api is not None:
            for method_name in ("project_get_files", "get_project_files", "get_files"):
                method = getattr(api, method_name, None)
                if callable(method):
                    try:
                        files = method(project_id)
                        if files:
                            result["files"] = files
                            logger.info("pyoverleaf.%s returned file tree", method_name)
                        break
                    except Exception as e:
                        logger.warning("pyoverleaf.%s failed: %s", method_name, e)

        # HTML fallback — works even when the socket path fails.
        try:
            meta = self.scrape_project_html(project_id)
            result["raw_meta"] = meta
            if meta.get("ol-project"):
                proj = meta["ol-project"]
                if isinstance(proj, dict):
                    if not result["files"] and proj.get("rootFolder"):
                        result["files"] = proj["rootFolder"]
                    result["name"] = result["name"] or proj.get("name")
                    result["rootDocId"] = result["rootDocId"] or proj.get("rootDoc_id")
            for key in ("ol-projectName", "ol-project-name"):
                if meta.get(key) and not result["name"]:
                    result["name"] = meta[key]
            for key in ("ol-rootDocId", "ol-root-doc-id"):
                if meta.get(key) and not result["rootDocId"]:
                    result["rootDocId"] = meta[key]
        except Exception as e:
            logger.warning("HTML scrape of project page failed: %s", e)

        return result

    def scrape_project_html(self, project_id: str) -> dict[str, Any]:
        """GET /project/:id and parse <meta name="ol-*" content="..."> tags.

        Values are HTML-entity-decoded and JSON-parsed when possible.
        Returns a dict { 'ol-<key>': decoded_value }.
        """
        path = f"/project/{project_id}"
        url = f"{self.base_url}{path}"
        r = self.session.get(url, timeout=30, allow_redirects=False)
        if r.status_code in (301, 302, 303, 307, 308):
            loc = r.headers.get("Location", "")
            if "login" in loc.lower():
                raise RuntimeError(
                    "Overleaf redirected the project page to a login URL. "
                    "Your session cookie is missing or expired."
                )
        if r.status_code in (401, 403):
            raise RuntimeError(
                f"Overleaf returned {r.status_code} for {path}. Session likely expired."
            )
        r.raise_for_status()
        body = r.text

        # Match <meta name="ol-*" content="..." /> with attributes in either order.
        meta_re = re.compile(
            r"<meta\b[^>]*\bname\s*=\s*\"(?P<name>ol-[^\"]+)\"[^>]*\bcontent\s*=\s*\"(?P<content>[^\"]*)\"",
            re.IGNORECASE,
        )
        meta_re_alt = re.compile(
            r"<meta\b[^>]*\bcontent\s*=\s*\"(?P<content>[^\"]*)\"[^>]*\bname\s*=\s*\"(?P<name>ol-[^\"]+)\"",
            re.IGNORECASE,
        )

        found: dict[str, Any] = {}
        for regex in (meta_re, meta_re_alt):
            for m in regex.finditer(body):
                name = m.group("name")
                if name in found:
                    continue
                raw = m.group("content")
                found[name] = _decode_meta_content(raw)

        if not found:
            logger.warning(
                "Project HTML at %s contained no <meta name=\"ol-*\"> tags — "
                "the editor may not have been rendered (login wall? error page?).",
                path,
            )
        else:
            logger.info("HTML scrape found %d ol-meta attributes", len(found))
        return found

    def flatten_files(self, files_root: Any, debug_logger=None) -> list[dict[str, str]]:
        """Walk a project file tree and return a flat list of
        {doc_id, pathname} for each editable doc.

        Handles three shapes:
          1. pyoverleaf.ProjectFolder dataclass (`id`, `name`, `children` of
             ProjectFolder/ProjectFile, type=="doc"/"file"/"folder")
          2. dict with `docs` / `folders` keys (raw Overleaf rootFolder JSON)
          3. dict with `_id` / `name` / `type` (single entity)
        """
        out: list[dict[str, str]] = []

        def walk_pyo(node: Any, parent: str) -> None:
            # pyoverleaf ProjectFolder / ProjectFile
            node_type = getattr(node, "type", None)
            if node_type == "folder":
                name = getattr(node, "name", "") or ""
                new_parent = (
                    f"{parent}{name}/" if name and name != "rootFolder" else parent
                )
                for child in getattr(node, "children", []) or []:
                    walk_pyo(child, new_parent)
                return
            if node_type == "doc":
                node_id = getattr(node, "id", None)
                name = getattr(node, "name", None)
                if node_id and name:
                    out.append({"doc_id": str(node_id), "pathname": f"{parent}{name}"})
                return
            # Skip type=="file" (binary attachments — figures, etc.)
            if node_type == "file":
                return
            # Fall through to dict/list walkers
            walk_any(node, parent)

        def walk_dict(node: dict[str, Any], parent: str) -> None:
            for doc in node.get("docs", []) or []:
                doc_id = doc.get("_id") or doc.get("id")
                name = doc.get("name") or ""
                if doc_id and name:
                    out.append({"doc_id": str(doc_id), "pathname": f"{parent}{name}"})
            for folder in node.get("folders", []) or []:
                fname = folder.get("name") or ""
                new_parent = (
                    f"{parent}{fname}/" if fname and fname != "rootFolder" else parent
                )
                walk_dict(folder, new_parent)

        def walk_any(node: Any, parent: str) -> None:
            if hasattr(node, "type") and hasattr(node, "name"):
                walk_pyo(node, parent)
                return
            if isinstance(node, dict):
                if "docs" in node or "folders" in node:
                    walk_dict(node, parent)
                    return
                doc_id = node.get("_id") or node.get("id") or node.get("doc_id")
                name = node.get("name")
                kind = node.get("type") or node.get("kind")
                if doc_id and name and kind in (None, "doc", "file"):
                    out.append({"doc_id": str(doc_id), "pathname": f"{parent}{name}"})
                    return
            if isinstance(node, list):
                for item in node:
                    walk_any(item, parent)

        if hasattr(files_root, "type") and hasattr(files_root, "name"):
            walk_pyo(files_root, "")
        elif isinstance(files_root, list):
            for entry in files_root:
                walk_any(entry, "")
        else:
            walk_any(files_root, "")

        if debug_logger is not None and not out:
            try:
                preview = json.dumps(files_root, default=str)[:1200]
            except Exception:
                preview = repr(files_root)[:1200]
            debug_logger(
                "flatten_files returned 0 entries. Raw shape (truncated): %s",
                preview,
            )
        return out


def _decode_meta_content(raw: str) -> Any:
    """Best-effort decode of a <meta content="..."> value.

    Overleaf URL-encodes JSON values in meta content. We try (in order):
    HTML entity unescape, URL-decode, then JSON parse. If JSON parse fails,
    return the unescaped string.
    """
    s = html.unescape(raw)
    if "%" in s:
        try:
            s_decoded = unquote(s)
            if s_decoded != s:
                s = s_decoded
        except Exception:
            pass
    if not s:
        return s
    if s[0] in "{[" or s in ("true", "false", "null") or (s and s[0].isdigit()):
        try:
            return json.loads(s)
        except Exception:
            return s
    return s
