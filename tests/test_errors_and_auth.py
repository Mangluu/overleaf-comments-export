from __future__ import annotations

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

    monkeypatch.setattr(client.session, "get", boom)
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

    monkeypatch.setattr(client.session, "get", flaky)
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

    monkeypatch.setattr(client.session, "get", once)
    assert client._request("https://www.overleaf.com/x").status_code == 404
    assert calls["n"] == 1
