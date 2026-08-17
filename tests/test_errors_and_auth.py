from __future__ import annotations

import pytest
import requests

from overleaf_comments_export.client import (
    OverleafClient,
    UserFacingError,
    _network_hint,
    _parse_cookie_string,
)


# ---- cookie parsing (the paste-it-yourself auth path) ----

def test_parse_bare_cookie_value():
    assert _parse_cookie_string("s%3Aabc.def") == {"overleaf_session2": "s%3Aabc.def"}


def test_parse_named_cookie():
    assert _parse_cookie_string("overleaf_session2=s%3Aabc") == {
        "overleaf_session2": "s%3Aabc"
    }


def test_parse_full_document_cookie_dump():
    got = _parse_cookie_string("GCLB=xyz; overleaf_session2=s%3Aabc; other=1")
    assert got["overleaf_session2"] == "s%3Aabc"
    assert got["GCLB"] == "xyz"


def test_parse_strips_quotes_and_whitespace():
    assert _parse_cookie_string('  "s%3Aabc"  ') == {"overleaf_session2": "s%3Aabc"}


def test_parse_empty():
    assert _parse_cookie_string("") == {}
    assert _parse_cookie_string("   ") == {}


def test_connect_with_pasted_cookie_builds_session():
    client = OverleafClient()
    client.connect(browser="manual", cookie_value="overleaf_session2=s%3Aabc")
    jar = client.session.cookies
    assert jar.get("overleaf_session2", domain=".overleaf.com") == "s%3Aabc"
    # User-Agent carries the real version, not a hardcoded one
    assert "overleaf-comments-export/" in client.session.headers["User-Agent"]


def test_connect_manual_without_cookie_is_user_facing():
    client = OverleafClient()
    try:
        client.connect(browser="manual")
    except UserFacingError as e:
        assert "cookie" in str(e).lower()
    else:  # pragma: no cover
        raise AssertionError("expected UserFacingError")


def test_connect_rejects_cookie_without_session_name():
    client = OverleafClient()
    try:
        client.connect(browser="manual", cookie_value="GCLB=xyz; other=1")
    except UserFacingError as e:
        assert "overleaf_session2" in str(e)
    else:  # pragma: no cover
        raise AssertionError("expected UserFacingError")


# ---- friendly network errors (the reported DNS crash) ----

def test_dns_failure_hint_is_plain_english():
    exc = requests.exceptions.ConnectionError(
        "HTTPSConnectionPool(host='www.overleaf.com', port=443): Max retries "
        "exceeded (Caused by NameResolutionError(\"Failed to resolve "
        "'www.overleaf.com' ([Errno 8] nodename nor servname provided\"))"
    )
    hint = _network_hint(exc)
    assert "network problem on this computer" in hint
    assert "Traceback" not in hint
    assert "NameResolutionError" not in hint


def test_timeout_hint():
    assert "did not respond in time" in _network_hint(requests.exceptions.Timeout())


def test_generic_connection_hint():
    assert "Could not reach Overleaf" in _network_hint(
        requests.exceptions.ConnectionError("connection refused")
    )


def test_request_retries_then_raises_user_facing(monkeypatch):
    """A total outage must surface as UserFacingError, not a raw traceback."""
    client = OverleafClient()
    client.connect(browser="manual", cookie_value="overleaf_session2=s%3Aabc")

    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        raise requests.exceptions.ConnectionError("Failed to resolve 'www.overleaf.com'")

    monkeypatch.setattr(client.session, "request", boom)
    monkeypatch.setattr("overleaf_comments_export.client.time.sleep", lambda s: None)

    try:
        client._request("https://www.overleaf.com/project/x/threads")
    except UserFacingError as e:
        assert "network problem" in str(e)
    else:  # pragma: no cover
        raise AssertionError("expected UserFacingError")
    assert calls["n"] == 3  # retried before giving up


def test_request_retries_transient_500_then_succeeds(monkeypatch):
    client = OverleafClient()
    client.connect(browser="manual", cookie_value="overleaf_session2=s%3Aabc")

    seq = [500, 200]
    calls = {"n": 0}

    class Resp:
        def __init__(self, code):
            self.status_code = code
            self.headers = {}

    def flaky(*a, **k):
        code = seq[calls["n"]]
        calls["n"] += 1
        return Resp(code)

    monkeypatch.setattr(client.session, "request", flaky)
    monkeypatch.setattr("overleaf_comments_export.client.time.sleep", lambda s: None)

    r = client._request("https://www.overleaf.com/x")
    assert r.status_code == 200
    assert calls["n"] == 2


def test_request_does_not_retry_404(monkeypatch):
    client = OverleafClient()
    client.connect(browser="manual", cookie_value="overleaf_session2=s%3Aabc")

    calls = {"n": 0}

    class Resp:
        status_code = 404
        headers: dict = {}

    def once(*a, **k):
        calls["n"] += 1
        return Resp()

    monkeypatch.setattr(client.session, "request", once)
    assert client._request("https://www.overleaf.com/x").status_code == 404
    assert calls["n"] == 1


# --- fetching the PDF Overleaf built ---

class _Resp:
    def __init__(self, status=200, content=b"", payload=None):
        self.status_code = status
        self.content = content
        self._payload = payload
        self.headers = {}

    @property
    def ok(self):
        return self.status_code < 400

    @property
    def text(self):
        return self.content.decode("utf-8", "replace")

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise requests.exceptions.HTTPError(f"{self.status_code}")


def _client(monkeypatch, handler):
    from overleaf_comments_export.client import OverleafClient
    c = OverleafClient()
    c.connect(browser="manual", cookie_value="overleaf_session2=s%3Aabc")
    monkeypatch.setattr(c.session, "request", handler)
    return c


def test_the_last_build_is_used_when_there_is_one(monkeypatch):
    """Reusing the existing build costs nothing and is what the user is
    already looking at. Asking for a compile uses their quota."""
    seen = []

    def handler(method, url, **kw):
        seen.append((method, url))
        if url.endswith("/output/output.pdf"):
            return _Resp(content=b"%PDF-1.7 body")
        raise AssertionError(f"should not have been called: {url}")

    c = _client(monkeypatch, handler)
    assert c.download_compiled_pdf("abc") == b"%PDF-1.7 body"
    assert not any("compile" in u for _, u in seen), "asked for a needless compile"


def test_a_compile_is_requested_when_there_is_no_build(monkeypatch):
    def handler(method, url, **kw):
        if "build/1" in url:                 # checked first: the built file's
            return _Resp(content=b"%PDF-1.7 fresh")   # URL also ends in output.pdf
        if url.endswith("/output/output.pdf"):
            return _Resp(status=404)
        if url.endswith("/project/abc"):
            return _Resp(content=b'<meta name="ol-csrfToken" content="tok123">')
        if url.endswith("/compile"):
            assert method == "POST"
            assert kw["headers"]["x-csrf-token"] == "tok123"
            return _Resp(payload={"status": "success", "outputFiles": [
                {"path": "output.pdf", "url": "/project/abc/build/1/output/output.pdf"}]})
        raise AssertionError(url)

    assert _client(monkeypatch, handler).download_compiled_pdf("abc") == b"%PDF-1.7 fresh"


def test_a_failed_compile_returns_nothing_rather_than_rubbish(monkeypatch):
    def handler(method, url, **kw):
        if url.endswith("/output/output.pdf"):
            return _Resp(status=404)
        if url.endswith("/project/abc"):
            return _Resp(content=b'<meta name="ol-csrfToken" content="tok">')
        return _Resp(payload={"status": "failure", "outputFiles": []})

    assert _client(monkeypatch, handler).download_compiled_pdf("abc") is None


def test_an_html_error_page_is_not_mistaken_for_a_pdf(monkeypatch):
    def handler(method, url, **kw):
        if url.endswith("/output/output.pdf"):
            return _Resp(content=b"<!DOCTYPE html><title>Not found</title>")
        if url.endswith("/project/abc"):
            return _Resp(content=b"<html>no token here</html>")
        raise AssertionError(url)

    assert _client(monkeypatch, handler).download_compiled_pdf("abc") is None


def test_the_build_is_fetched_from_the_machine_that_made_it(monkeypatch):
    """A build lives on the compile server, not the main site. Asking the main
    site returns 404, which looks like "no PDF" and is not."""
    asked = []

    def handler(method, url, **kw):
        asked.append(url)
        if "clsiserverid=clsi-7" in url:
            return _Resp(content=b"%PDF-1.7 built")
        if url.endswith("/output/output.pdf"):
            return _Resp(status=404, content=b"<!DOCTYPE html>")
        if url.endswith("/project/abc"):
            return _Resp(content=b'<meta name="ol-csrfToken" content="tok">')
        if url.endswith("/compile"):
            return _Resp(payload={
                "status": "success", "clsiServerId": "clsi-7",
                "pdfDownloadDomain": "https://a.overleaf.com",
                "outputFiles": [{"path": "output.pdf",
                                 "url": "/project/abc/user/u1/build/b1/output/output.pdf"}]})
        raise AssertionError(url)

    c = _client(monkeypatch, handler)
    assert c.download_compiled_pdf("abc") == b"%PDF-1.7 built"
    assert asked[-1] == (
        "https://a.overleaf.com/project/abc/user/u1/build/b1/output/output.pdf"
        "?clsiserverid=clsi-7"
    )


def test_the_build_url_works_without_the_extra_fields(monkeypatch):
    """Self-hosted Overleaf serves its own builds and sends neither field."""
    def handler(method, url, **kw):
        if "build/b1" in url:
            assert "clsiserverid" not in url
            return _Resp(content=b"%PDF-1.7 built")
        if url.endswith("/output/output.pdf"):
            return _Resp(status=404)
        if url.endswith("/project/abc"):
            return _Resp(content=b'<meta name="ol-csrfToken" content="tok">')
        return _Resp(payload={"status": "success", "outputFiles": [
            {"path": "output.pdf", "url": "/project/abc/build/b1/output/output.pdf"}]})

    assert _client(monkeypatch, handler).download_compiled_pdf("abc") == b"%PDF-1.7 built"


# --- session cookies that are not called overleaf_session2 (issue #6) ---

def test_a_self_hosted_cookie_named_after_the_instance_is_recognised():
    """ifftex.fz-juelich.de calls it ifftex.sid. There is no list of these to
    keep, so the shape is what gets matched."""
    from overleaf_comments_export.client import is_session_cookie

    for name in ("ifftex.sid", "overleaf.sid", "sharelatex.sid",
                 "overleaf_session2", "tex.sid"):
        assert is_session_cookie(name), name
    for name in ("_ga", "csrf", "sid", "session", "overleaf_session2_backup"):
        assert not is_session_cookie(name), name


def test_a_known_name_is_preferred_over_a_guess():
    from overleaf_comments_export.client import _pick_session_cookie

    assert _pick_session_cookie(["analytics.sid", "overleaf_session2"]) == "overleaf_session2"
    assert _pick_session_cookie(["_ga", "ifftex.sid"]) == "ifftex.sid"
    assert _pick_session_cookie(["_ga", "csrf"]) is None


def test_an_explicit_name_overrides_the_guessing():
    from overleaf_comments_export.client import _pick_session_cookie, is_session_cookie

    assert _pick_session_cookie(["ifftex.sid", "weird_session"], "weird_session") == "weird_session"
    assert _pick_session_cookie(["ifftex.sid"], "weird_session") is None
    assert is_session_cookie("weird_session", "weird_session")
    assert not is_session_cookie("ifftex.sid", "weird_session")


def test_a_pasted_self_hosted_cookie_is_accepted(monkeypatch):
    from overleaf_comments_export.client import OverleafClient

    client = OverleafClient(base_url="https://ifftex.fz-juelich.de")
    client.connect(browser="manual", cookie_value="ifftex.sid=s%3Aabc123")
    assert client.session.cookies.get("ifftex.sid") == "s%3Aabc123"


def test_the_error_names_the_cookies_it_actually_found(monkeypatch):
    """dixr could have solved this alone if the message had said what was there."""
    import types

    from overleaf_comments_export.client import OverleafClient, UserFacingError

    class Cookie:
        def __init__(self, name):
            self.name = name

    fake = types.SimpleNamespace(
        firefox=lambda domain_name=None: [Cookie("_ga"), Cookie("ifftex_login")]
    )
    monkeypatch.setitem(__import__("sys").modules, "browser_cookie3", fake)
    client = OverleafClient(base_url="https://tex.example.edu")
    with pytest.raises(UserFacingError) as excinfo:
        client.connect(browser="firefox")
    message = str(excinfo.value)
    assert "ifftex_login" in message, "the message must list what it did find"
    assert "--cookie-name" in message


def test_an_enormous_project_zip_is_refused_rather_than_read(monkeypatch):
    """It is fetched only when something has already gone wrong, so it must not
    be the thing that takes the machine down."""
    from overleaf_comments_export import client as client_mod
    from overleaf_comments_export.client import OverleafClient

    monkeypatch.setattr(client_mod, "MAX_PROJECT_ZIP_BYTES", 1024)

    class Streamed(_Resp):
        def iter_content(self, size):
            for _ in range(10):
                yield b"PK" + b"\x00" * 500

        def close(self):
            pass

    c = _client(monkeypatch, lambda method, url, **kw: Streamed())
    assert c.download_project_zip("abc") is None


def test_a_normal_project_zip_comes_back_whole(monkeypatch):
    from overleaf_comments_export.client import OverleafClient

    class Streamed(_Resp):
        def iter_content(self, size):
            yield b"PK\x03\x04"
            yield b"rest of the archive"

        def close(self):
            pass

    c = _client(monkeypatch, lambda method, url, **kw: Streamed())
    assert c.download_project_zip("abc") == b"PK\x03\x04rest of the archive"


def test_something_that_is_not_a_zip_is_not_returned(monkeypatch):
    class Streamed(_Resp):
        def iter_content(self, size):
            yield b"<!DOCTYPE html><title>Sign in</title>"

        def close(self):
            pass

    c = _client(monkeypatch, lambda method, url, **kw: Streamed())
    assert c.download_project_zip("abc") is None


def test_the_cookie_failure_offers_a_route_that_needs_no_permission(monkeypatch):
    """A downloaded Mac app has no Full Disk Access, so on macOS every browser's
    cookie store is unreadable. The message used to blame Chrome, which sent
    Safari users hunting for a problem they did not have."""
    import sys as _sys

    from overleaf_comments_export.client import _cookie_read_failed

    monkeypatch.setattr(_sys, "platform", "darwin")
    message = _cookie_read_failed("safari")
    assert "Full Disk Access" in message
    # The options that need no permission must come before the one that does.
    assert message.index("paste") < message.index("Full Disk Access", message.index("paste"))
    assert "extension" in message
    assert "Chrome" not in message, "do not blame Chrome to a Safari user"


def test_the_cookie_failure_reads_differently_off_macos(monkeypatch):
    import sys as _sys

    from overleaf_comments_export.client import _cookie_read_failed

    monkeypatch.setattr(_sys, "platform", "win32")
    message = _cookie_read_failed("chrome")
    assert "Full Disk Access" not in message, "that is a macOS thing"
    assert "Chrome 127" in message
