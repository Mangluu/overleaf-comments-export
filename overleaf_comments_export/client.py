from __future__ import annotations

import html
import json
import logging
import os
import re
import ssl
import time
from typing import Any, Optional
from urllib.parse import unquote, urlparse

import requests

logger = logging.getLogger(__name__)


def _ensure_ca_bundle() -> None:
    """Give Python a set of root certificates when it has none.

    `requests` carries its own, so our HTTP calls always work. Anything using
    Python's default settings does not, and on a Mac where Python was installed
    without running "Install Certificates.command" the default store is empty,
    so every one of those connections fails to verify. That is what makes the
    file tree fetch fail, which is why exported files end up named after a
    document id instead of `main.tex`.

    Only done when the store is genuinely empty. A machine behind a corporate
    proxy has its own roots loaded, and replacing them would break it.
    """
    if os.environ.get("SSL_CERT_FILE") or os.environ.get("SSL_CERT_DIR"):
        return
    try:
        if ssl.create_default_context().cert_store_stats()["x509_ca"] > 0:
            return
        import certifi
    except Exception:
        return
    os.environ["SSL_CERT_FILE"] = certifi.where()
    logger.info("No root certificates were installed; using certifi's.")

OVERLEAF_BASE = "https://www.overleaf.com"

PROJECT_URL_RE = re.compile(r"/project/(?P<id>[0-9a-fA-F]{24})")

RETRY_STATUSES = (429, 500, 502, 503, 504)

# overleaf.com uses the first. Self-hosted Community Edition and Server Pro use
# `overleaf.sid`, and older self-hosted installs still use the ShareLaTeX name.
SESSION_COOKIE_NAMES = ("overleaf_session2", "overleaf.sid", "sharelatex.sid")

# A self-hosted Overleaf names its session cookie after the instance, so a
# university running it as "ifftex" has `ifftex.sid`. There is no list of those
# to keep, and there never will be, so match the shape instead. Anyone whose
# cookie does not fit can name it with --cookie-name.
SESSION_COOKIE_SUFFIX = ".sid"

# The project zip is only fetched when filenames could not be had any other
# way, and it is read into memory to be opened. Papers carry figures, so this
# is bounded rather than trusted.
MAX_PROJECT_ZIP_BYTES = 250 * 1024 * 1024


def is_session_cookie(name: str, override: str | None = None) -> bool:
    """Whether a cookie of this name could be an Overleaf session."""
    if override:
        return name == override
    return name in SESSION_COOKIE_NAMES or name.endswith(SESSION_COOKIE_SUFFIX)


def _pick_session_cookie(names, override: str | None = None):
    """The most likely session cookie among these names.

    Exact known names win over the suffix guess, so a server that has both
    `overleaf_session2` and some other `.sid` cookie still picks the right one.
    """
    names = list(names)
    if override:
        return next((n for n in names if n == override), None)
    for known in SESSION_COOKIE_NAMES:
        if known in names:
            return known
    return next((n for n in names if n.endswith(SESSION_COOKIE_SUFFIX)), None)


def _cookie_read_failed(browser: str) -> str:
    """Why a browser's cookie store could not be read, and what to do instead.

    On a Mac every browser's cookies sit behind Full Disk Access, Safari very
    much included. The old wording blamed Chrome, which sent Safari users
    looking for a problem they did not have. Granting Full Disk Access to a
    downloaded app is also a lot to ask, so the options that need no permission
    at all come first.
    """
    import sys

    lines = [f"Could not read the Overleaf cookie from {browser}.", ""]
    if sys.platform == "darwin":
        lines += [
            "macOS keeps every browser's cookies behind Full Disk Access, so "
            "nothing can read them until you allow it. There are three ways "
            "round this, easiest first.",
            "",
            "1. Paste the cookie instead. Choose \"I will paste it myself\" and "
            "press How? for the steps. Nothing needs permission and it works "
            "on every browser.",
            "",
            "2. Use the browser extension, which reads the Overleaf tab you "
            "already have open and never touches the cookie:",
            "   https://github.com/Mangluu/overleaf-comments-export/tree/main/browser-extension",
            "",
            "3. Grant Full Disk Access to this app. Open System Settings, go to "
            "Privacy & Security, then Full Disk Access, press +, and choose "
            f"this app. Then quit it and open it again. {browser.capitalize()} "
            "must also be signed in to Overleaf.",
        ]
    else:
        lines += [
            f"Check that {browser} is installed and signed in to Overleaf.",
            "",
            "If it is, its cookie store cannot be read on this computer. That "
            "happens with Chrome 127 and newer on Windows, and with browsers "
            "installed from Snap on Linux. Choose \"I will paste it myself\" "
            "instead and press How? for the steps, or use the browser "
            "extension, which needs no cookie at all.",
        ]
    return "\n".join(lines)


def _cookie_domain_for(host: str) -> str:
    """The domain to look cookies up under.

    For overleaf.com we want the registrable domain so www. and api. both
    match. For a self-hosted host we want that host exactly.
    """
    if host.endswith("overleaf.com"):
        return "overleaf.com"
    return host


class UserFacingError(RuntimeError):
    """An error with a message written for a non-technical user.

    The GUI/CLI print these verbatim without a traceback; anything else is
    treated as an unexpected bug and shown with full detail.
    """


def _network_hint(exc: Exception) -> str:
    """Plain-English explanation for a requests connection failure."""
    text = str(exc)
    if (
        "NameResolution" in text
        or "Failed to resolve" in text
        or "nodename nor servname" in text
        or "Name or service not known" in text
        or "getaddrinfo" in text
    ):
        return (
            "Could not look up www.overleaf.com.\n\n"
            "This is a network problem on this computer, not a problem with your "
            "Overleaf project. Check that you are online, then try again. If you "
            "are on a VPN or a work/university network, try turning the VPN off "
            "or switching networks."
        )
    if isinstance(exc, requests.exceptions.SSLError):
        return (
            "The secure connection to Overleaf could not be verified.\n\n"
            "This usually means a VPN, antivirus, or corporate proxy is "
            "intercepting traffic. Try again on a different network."
        )
    if isinstance(exc, requests.exceptions.Timeout):
        return (
            "Overleaf did not respond in time.\n\n"
            "The connection may be slow or Overleaf may be busy. Wait a moment "
            "and try again."
        )
    return (
        "Could not reach Overleaf.\n\n"
        "Check that you are online and that https://www.overleaf.com opens in "
        "your browser, then try again."
    )


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

    def __init__(self, base_url: str = OVERLEAF_BASE,
                 cookie_name: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        # Set when a server names its session cookie something we cannot guess.
        self.cookie_name = cookie_name or None
        # Set by run_export. Checked between retry attempts, so a stop takes
        # effect during the waiting rather than only after it.
        self.should_cancel = None
        self._api = None
        self._session: Optional[requests.Session] = None

    SUPPORTED_BROWSERS = (
        "safari", "firefox", "auto", "chrome", "chromium", "edge", "brave", "manual",
    )
    # Browsers that don't trigger macOS Keychain or password prompts:
    PRIVACY_FRIENDLY_BROWSERS = ("safari", "firefox")

    def connect(self, browser: str = "auto", cookie_value: str | None = None) -> None:
        """Authenticate as the user.

        `cookie_value` (or browser="manual") uses a session cookie pasted by the
        user — this works identically on every OS and browser, and is the
        fallback when a browser's cookie store can't be read (Chrome 127+ on
        Windows, snap-packaged browsers on Linux, locked-down macOS).
        Otherwise cookies are read from the named browser, or auto-detected.
        """
        _ensure_ca_bundle()
        browser = (browser or "auto").lower()
        if browser not in self.SUPPORTED_BROWSERS:
            raise ValueError(
                f"Unsupported browser {browser!r}. Choose one of: "
                + ", ".join(self.SUPPORTED_BROWSERS)
            )

        if cookie_value:
            session = self._connect_via_cookie_value(cookie_value)
        elif browser == "manual":
            raise UserFacingError(
                "No session cookie was provided.\n\n"
                "Paste the value of your Overleaf 'overleaf_session2' cookie, or "
                "choose a browser to read it from automatically."
            )
        elif browser == "auto":
            session = self._connect_via_pyoverleaf()
        else:
            session = self._connect_via_browser_cookie3(browser)

        # Assign, don't setdefault: requests.Session pre-fills User-Agent with
        # "python-requests/x.y", which setdefault would leave in place.
        session.headers["User-Agent"] = (
            f"overleaf-comments-export/{_tool_version()} (Mozilla/5.0 compatible)"
        )
        session.headers.setdefault("Accept", "application/json, text/plain, */*")
        session.headers.setdefault("Referer", f"{self.base_url}/")
        self._session = session

    def _connect_via_cookie_value(self, pasted: str) -> requests.Session:
        """Build a session from a cookie the user pasted.

        Accepts a bare value, `overleaf_session2=<value>`, or a whole
        `document.cookie` dump — whatever the user actually managed to copy.
        """
        pairs = _parse_cookie_string(pasted)
        if not pairs:
            raise UserFacingError(
                "That does not look like an Overleaf session cookie.\n\n"
                "In your browser open Overleaf, press F12, go to "
                "Application → Cookies → https://www.overleaf.com, and copy the "
                "Value of the row named 'overleaf_session2'."
            )
        if not _pick_session_cookie(pairs, self.cookie_name):
            raise UserFacingError(
                "The pasted cookie does not contain an Overleaf session.\n\n"
                "Copy the Value of the cookie named 'overleaf_session2' on "
                "overleaf.com. A self-hosted Overleaf names it after itself, so "
                "it ends in '.sid', for example 'overleaf.sid' or 'ifftex.sid'. "
                "Look under Application, then Cookies, in your browser's "
                "developer tools.\n\n"
                "What you pasted contained: " + ", ".join(sorted(pairs)[:15])
            )

        session = requests.Session()
        domain = urlparse(self.base_url).hostname or "www.overleaf.com"
        # Registrable domain for overleaf.com so www. and api. both match; the
        # exact host for anything self-hosted.
        cookie_domain = ".overleaf.com" if domain.endswith("overleaf.com") else domain
        for name, value in pairs.items():
            session.cookies.set(name, value, domain=cookie_domain, path="/")
        self._api = None  # no pyoverleaf; file tree comes from the HTML scrape
        return session

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

        # Derive the domain from base_url. Hardcoding overleaf.com means a
        # self-hosted instance returns no cookies at all.
        host = urlparse(self.base_url).hostname or "overleaf.com"
        domain_name = _cookie_domain_for(host)
        try:
            jar = loader(domain_name=domain_name)
        except Exception as e:
            raise UserFacingError(
                _cookie_read_failed(browser)
            ) from e

        wanted = _pick_session_cookie((c.name for c in jar), self.cookie_name)
        session_cookie = next((c for c in jar if c.name == wanted), None) if wanted else None
        if session_cookie is None:
            found = sorted({c.name for c in jar})
            # Name what was actually there. A self-hosted server can call its
            # session anything, and without this the user has no way to find out
            # what to pass to --cookie-name.
            listing = (
                "\n\nCookies found for that address:\n  " + "\n  ".join(found[:25])
                + "\n\nIf one of those is the session, pass it with "
                  "--cookie-name, or type it into the window under the "
                  "self-hosted options."
            ) if found else ""
            raise UserFacingError(
                f"No Overleaf session was found in {browser} for {host}."
                + ("" if self.cookie_name else "\n\nLooked for "
                   + ", ".join(SESSION_COOKIE_NAMES) + f", and anything ending in "
                   f"{SESSION_COOKIE_SUFFIX}.")
                + (f"\n\nLooked for a cookie named {self.cookie_name!r}."
                   if self.cookie_name else "")
                + f"\n\nOpen {self.base_url} in {browser}, sign in, and try again."
                + listing
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

    def _request(
        self, url: str, *, attempts: int = 3, method: str = "GET", timeout: int = 30,
        **kwargs: Any,
    ) -> requests.Response:
        """One request with retry on transient failures, and plain-English errors.

        Retries connection errors, timeouts, and 429/5xx (honouring Retry-After).
        Never retries 4xx other than 429 — those won't fix themselves.
        """
        last_exc: Exception | None = None
        for attempt in range(attempts):
            if self.should_cancel is not None and self.should_cancel():
                from .export import ExportCancelled
                raise ExportCancelled()
            try:
                r = self.session.request(method, url, timeout=timeout, **kwargs)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_exc = e
                if attempt == attempts - 1:
                    raise UserFacingError(_network_hint(e)) from e
                self._sleep(2**attempt)
                continue
            if r.status_code in RETRY_STATUSES and attempt < attempts - 1:
                wait = r.headers.get("Retry-After")
                try:
                    delay = min(float(wait), 30.0) if wait else 2**attempt
                except ValueError:
                    delay = 2**attempt
                logger.warning(
                    "%s returned %s — retrying in %.0fs", url, r.status_code, delay
                )
                self._sleep(delay)
                continue
            return r
        raise UserFacingError(_network_hint(last_exc or Exception()))  # pragma: no cover

    def _sleep(self, seconds: float) -> None:
        """Wait, but in short steps so a cancel is noticed while waiting."""
        waited = 0.0
        while waited < seconds:
            if self.should_cancel is not None and self.should_cancel():
                from .export import ExportCancelled
                raise ExportCancelled()
            time.sleep(min(0.25, seconds - waited))
            waited += 0.25

    def _get(self, path: str, expect_json: bool = True) -> Any:
        url = f"{self.base_url}{path}"
        r = self._request(url)
        if r.status_code in (401, 403):
            raise UserFacingError(
                "Overleaf refused the request (not signed in).\n\n"
                "Your saved session has expired. Open https://www.overleaf.com in "
                "your browser, make sure you are signed in and can see this "
                "project, then run the export again."
            )
        if r.status_code == 404:
            raise UserFacingError(
                "Overleaf could not find that project.\n\n"
                "Check the project link is correct and that this account has "
                "access to it. Open the project in your browser and copy the "
                "address from the address bar."
            )
        r.raise_for_status()
        if not expect_json:
            return r.text
        ctype = r.headers.get("Content-Type", "")
        if "application/json" not in ctype:
            raise UserFacingError(
                "Overleaf returned a web page instead of data.\n\n"
                "This usually means you were signed out. Open Overleaf in your "
                "browser, sign in, and try again. If you are already signed in, "
                "Overleaf may have changed its internal API — please report this "
                "at https://github.com/Mangluu/overleaf-comments-export/issues"
            )
        return r.json()

    def get_threads(self, project_id: str) -> dict[str, Any]:
        """GET /project/:id/threads -> dict keyed by thread_id."""
        data = self._get(f"/project/{project_id}/threads")
        if not isinstance(data, dict):
            raise RuntimeError(f"Unexpected /threads response shape: {type(data).__name__}")
        return data

    def get_resolved_thread_ids(self, project_id: str) -> list[str]:
        """Ids of resolved threads, if this server offers that endpoint.

        A second opinion, not the source of truth: the thread list already says
        which threads are resolved. Some Overleaf versions do not have this
        route at all, so a 404 here means nothing is wrong.
        """
        try:
            data = self._get(f"/project/{project_id}/resolved-thread-ids")
        except Exception as e:
            logger.info(
                "This Overleaf has no resolved-thread-ids endpoint (%s). "
                "Resolved state is being read from the thread list instead.",
                type(e).__name__,
            )
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
        except UserFacingError:
            raise  # auth/network problems are fatal, not "no ranges"
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

    def download_project_zip(self, project_id: str) -> bytes | None:
        """The whole project as a zip, or None if it cannot be had.

        This is the "Download as zip" the editor offers, over ordinary cookie
        authenticated HTTP. It is the only route to real filenames that works
        whichever way the user signed in, which is why it is here: the socket
        call needs pyoverleaf, which needs a browser, and the project page no
        longer reliably carries the file tree.
        """
        try:
            r = self._request(f"{self.base_url}/project/{project_id}/download/zip",
                              timeout=120, stream=True)
        except UserFacingError:
            raise
        except Exception as e:
            logger.warning("Could not download the project zip: %s", e)
            return None
        if not r.ok:
            logger.warning("The project zip came back as %s.", r.status_code)
            r.close()
            return None
        # Streamed and capped. A paper carrying large figures can run to
        # hundreds of megabytes, and this is a fallback that only runs when
        # something has already gone wrong, so it must not be the thing that
        # takes the machine down.
        chunks: list[bytes] = []
        total = 0
        try:
            for chunk in r.iter_content(64 * 1024):
                total += len(chunk)
                if total > MAX_PROJECT_ZIP_BYTES:
                    logger.warning(
                        "The project zip is larger than %d MB, so filenames are "
                        "left as document ids rather than reading all of it.",
                        MAX_PROJECT_ZIP_BYTES // (1024 * 1024),
                    )
                    return None
                chunks.append(chunk)
        except Exception as e:
            logger.warning("The project zip download was interrupted: %s", e)
            return None
        finally:
            r.close()
        data = b"".join(chunks)
        if data[:2] != b"PK":
            logger.warning("The project zip is not a zip: %d bytes starting %r.",
                           len(data), data[:16])
            return None
        logger.info("Downloaded the project zip (%d KB).", len(data) // 1024)
        return data

    def download_doc_text(self, project_id: str, doc_id: str) -> str:
        """GET /Project/:id/doc/:doc_id/download -> plain text body."""
        return self._get(
            f"/Project/{project_id}/doc/{doc_id}/download", expect_json=False
        )

    def download_compiled_pdf(
        self, project_id: str, root_doc_id: str | None = None
    ) -> bytes | None:
        """The PDF Overleaf itself built, or None if it cannot be had.

        Tries the last build first, because that costs nothing and is what the
        user is looking at in their browser. Only if there is no build on the
        server does it ask for a compile, which is slow and uses their quota.
        """
        url = f"{self.base_url}/project/{project_id}/output/output.pdf"
        try:
            r = self._request(url)
            if r.ok and r.content[:4] == b"%PDF":
                logger.info("Using the PDF from the last build (%d KB).", len(r.content) // 1024)
                return r.content
            logger.info(
                "No PDF from the last build: %s returned %s, %s bytes starting %r.",
                url, r.status_code, len(r.content), r.content[:16],
            )
        except UserFacingError:
            raise
        except Exception as e:
            logger.info("No ready-made PDF (%s); asking for a compile.", type(e).__name__)

        token = self._csrf_token(project_id)
        if not token:
            logger.warning("No CSRF token on the project page, cannot ask for a compile.")
            return None
        payload: dict[str, Any] = {"check": "silent", "draft": False,
                                   "incrementalCompilesEnabled": True}
        if root_doc_id:
            payload["rootDoc_id"] = root_doc_id
        try:
            # A cold compile of a real paper takes a while, so this waits far
            # longer than an ordinary request.
            r = self._request(
                f"{self.base_url}/project/{project_id}/compile",
                method="POST", timeout=240, attempts=1, json=payload,
                headers={"x-csrf-token": token, "Accept": "application/json"},
            )
            logger.info("Compile request returned %s.", r.status_code)
            data = r.json() if r.ok else {}
        except Exception as e:
            logger.warning("Compile request failed: %s", e)
            return None

        if data.get("status") != "success":
            logger.warning("Overleaf did not compile the project: %s", data.get("status"))
            return None
        files = data.get("outputFiles") or []
        for f in files:
            if f.get("path") == "output.pdf":
                r = self._request(self._output_url(f.get("url") or "", data))
                if r.ok and r.content[:4] == b"%PDF":
                    logger.info("Compiled the project (%d KB).", len(r.content) // 1024)
                    return r.content
                logger.warning(
                    "The built PDF could not be downloaded: %s returned %s. "
                    "The compile reported: %s",
                    f.get("url"), r.status_code, ", ".join(sorted(data)),
                )
                return None
        logger.warning("The compile produced no output.pdf. It made: %s",
                       ", ".join(str(f.get("path")) for f in files) or "nothing")
        return None

    def _output_url(self, path: str, compile_response: dict[str, Any]) -> str:
        """Where a freshly built file actually lives.

        The build does not sit on the main site. It stays on the machine that
        did the compiling, and the compile reply says which one that was, so
        the address has to be assembled from both. Asking the main site for it
        gets a 404, which reads exactly like "there is no PDF" and is not.
        """
        if path.startswith("http"):
            url = path if self._same_site(path) else self.base_url + _path_of(path)
        else:
            domain = str(compile_response.get("pdfDownloadDomain") or "")
            if not domain or not self._same_site(domain):
                if domain:
                    logger.warning(
                        "The compile named %s as the download host, which is not "
                        "part of %s, so it was ignored.", domain, self.base_url)
                domain = self.base_url
            url = f"{domain.rstrip('/')}{path}"
        server = compile_response.get("clsiServerId")
        if server:
            url += ("&" if "?" in url else "?") + f"clsiserverid={server}"
        return url

    def _same_site(self, url: str) -> bool:
        """Is this the Overleaf we are signed in to, or somewhere else?

        The compile reply decides which host the built PDF is fetched from,
        and it is the only value in any response that does. Overleaf really
        does answer with a different host, since the build stays on the
        machine that made it, but that host is always part of the same site.
        Anything else is not followed.

        Compared against the site rather than the exact host, because the real
        answer is a sibling of www and not a child of it: signed in to
        www.overleaf.com, the build comes back on clsi-a1b2.overleaf.com. A
        check against the full host would reject every genuine PDF.
        """
        try:
            here = urlparse(self.base_url).hostname or ""
            there = urlparse(url if "//" in url else f"//{url}").hostname or ""
        except ValueError:
            return False
        if not there:
            return False
        here, there = here.lower().rstrip("."), there.lower().rstrip(".")
        if here.startswith("www."):
            here = here[4:]
        # The suffix always carries its dot. Without it, overleaf.com.evil.example
        # would pass for being part of overleaf.com.
        return there == here or there.endswith("." + here)

    def _csrf_token(self, project_id: str) -> str | None:
        meta = self.scrape_project_html(project_id)
        for key in ("ol-csrfToken", "ol-csrf-token"):
            if meta.get(key):
                return str(meta[key])
        return None

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
        r = self._request(url, allow_redirects=False)
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


def _path_of(url: str) -> str:
    """The path and query of a URL, for putting back on a host we trust."""
    parts = urlparse(url)
    return parts.path + (f"?{parts.query}" if parts.query else "")


def _tool_version() -> str:
    from . import __version__

    return __version__


def _parse_cookie_string(pasted: str) -> dict[str, str]:
    """Parse whatever the user pasted into {cookie_name: value}.

    Handles a bare cookie value, `name=value`, and a full `document.cookie`
    dump. Falls back to treating the whole string as the session value.
    """
    s = (pasted or "").strip().strip('"').strip("'")
    if not s:
        return {}
    out: dict[str, str] = {}
    for part in s.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _, value = part.partition("=")
        name, value = name.strip(), value.strip().strip('"')
        if name and value:
            out[name] = value
    return out or {"overleaf_session2": s}


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
