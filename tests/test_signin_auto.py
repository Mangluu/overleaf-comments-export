"""Signing in with --browser auto, the command line's default.

It used to hand the job to pyoverleaf's login_from_browser, which calls
browser_cookie3.load(). That reads every browser browser_cookie3 knows, and
gives up on all of them when any one raises anything but its own error type.
On Linux its Arc reader raises TypeError, so a user signed in on Firefox got a
traceback asking them to report a bug (issue #15). And pyoverleaf keeps no
session to hand back, so auto failed even when the read worked.
"""

from __future__ import annotations

import http.cookiejar
import sqlite3
import sys
import time
import types

import pytest
import requests

from overleaf_comments_export.client import OverleafClient, UserFacingError

SESSION = "overleaf_session2"


def _jar(*names, domain=".overleaf.com"):
    jar = http.cookiejar.CookieJar()
    for name in names:
        jar.set_cookie(requests.cookies.create_cookie(name, "s%3Aabc", domain=domain))
    return jar


class BrowserCookieError(Exception):
    """Stands in for browser_cookie3's own error type."""


def _fake_cookie_library(monkeypatch, behaviour):
    """A browser_cookie3 whose browsers do what `behaviour` says.

    Each value is a jar to return, or an exception to raise. load() raises the
    TypeError the real one raises on Linux, so anything still calling it fails.
    """
    calls = []

    def loader(name):
        def read(domain_name=""):
            calls.append((name, domain_name))
            outcome = behaviour.get(name, BrowserCookieError(f"Failed to find {name} cookie file"))
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
        return read

    module = types.ModuleType("browser_cookie3")
    for name in OverleafClient.AUTO_BROWSERS:
        setattr(module, name, loader(name))
    module.BrowserCookieError = BrowserCookieError

    def load(domain_name=""):
        raise TypeError("expected str, bytes or os.PathLike object, not NoneType")

    module.load = load
    monkeypatch.setitem(sys.modules, "browser_cookie3", module)
    return calls


@pytest.fixture(autouse=True)
def live_sessions(monkeypatch):
    """Every session counts as live unless a test says otherwise, so no test
    here asks a real server. A test can set the answer per browser."""
    answers = {}

    def is_live(self, jar):
        names = {c.name for c in jar}
        return answers.get(next(iter(sorted(names)), ""), True)

    monkeypatch.setattr(OverleafClient, "_session_is_live", is_live)
    return answers


@pytest.fixture()
def pyoverleaf(monkeypatch):
    """A pyoverleaf that records what it is given, and refuses to scan browsers."""
    made = []

    class Api:
        def __init__(self, host="www.overleaf.com", **kwargs):
            self.host = host
            self.cookies = None
            made.append(self)

        def login_from_cookies(self, cookies):
            self.cookies = cookies

        def login_from_browser(self):
            raise AssertionError("pyoverleaf was told to read every browser again")

    monkeypatch.setitem(sys.modules, "pyoverleaf", types.SimpleNamespace(Api=Api))
    return made


def test_auto_skips_a_browser_that_crashes_and_uses_the_next_signed_in(monkeypatch, pyoverleaf):
    """The reported case: one reader crashing must not end the search."""
    calls = _fake_cookie_library(monkeypatch, {
        "safari": TypeError("expected str, bytes or os.PathLike object, not NoneType"),
        "chrome": _jar(SESSION, "gke_route"),
        "edge": AssertionError("read after a session was already found"),
    })
    client = OverleafClient()
    client.connect(browser="auto")

    assert client.browser_used == "chrome"
    assert [name for name, _ in calls] == ["firefox", "safari", "chrome"], \
        "it kept reading browsers after finding a session, and each can mean a Keychain prompt"
    assert SESSION in {c.name for c in client.session.cookies}
    # pyoverleaf was handed the same cookies rather than left to find its own.
    assert pyoverleaf and {c.name for c in pyoverleaf[0].cookies} == {SESSION, "gke_route"}


def test_auto_with_nobody_signed_in_says_what_it_tried_without_calling_it_a_bug(monkeypatch, pyoverleaf):
    _fake_cookie_library(monkeypatch, {
        "firefox": _jar("some_other_cookie"),
        "safari": PermissionError("[Errno 1] Operation not permitted"),
        "chrome": TypeError("expected str, bytes or os.PathLike object, not NoneType"),
    })
    with pytest.raises(UserFacingError) as caught:
        OverleafClient().connect(browser="auto")
    message = str(caught.value)

    assert "firefox: not signed in to www.overleaf.com" in message
    assert "safari: no permission to read its cookies" in message
    assert "chrome: could not read its cookies (TypeError" in message
    assert "edge: not installed" in message
    for way_out in ("--browser firefox", "--cookie", "OVERLEAF_SESSION"):
        assert way_out in message


def test_a_named_browser_reads_that_browser_only(monkeypatch, pyoverleaf):
    """It used to read the named browser, then have pyoverleaf read every
    browser again for the file tree: more Keychain prompts on a Mac, and on
    Linux the same crash, swallowed."""
    calls = _fake_cookie_library(monkeypatch, {"firefox": _jar(SESSION)})
    client = OverleafClient()
    client.connect(browser="firefox")

    assert [name for name, _ in calls] == ["firefox"]
    assert client.browser_used == "firefox"
    assert pyoverleaf[0].cookies is not None


def test_auto_reads_the_cookies_of_the_server_in_use(monkeypatch, pyoverleaf):
    """pyoverleaf's scan only ever looked for overleaf.com cookies."""
    calls = _fake_cookie_library(monkeypatch, {"firefox": _jar("overleaf.sid", domain="latex.example.edu")})
    client = OverleafClient(base_url="https://latex.example.edu")
    client.connect(browser="auto")

    assert calls == [("firefox", "latex.example.edu")]
    assert pyoverleaf[0].host == "latex.example.edu"


def test_auto_works_when_pyoverleaf_cannot_be_set_up(monkeypatch):
    """pyoverleaf only adds the file tree. Without it the export still runs."""
    _fake_cookie_library(monkeypatch, {"firefox": _jar(SESSION)})
    monkeypatch.setitem(sys.modules, "pyoverleaf", types.SimpleNamespace())   # no Api at all
    client = OverleafClient()
    client.connect(browser="auto")
    assert client._api is None
    assert SESSION in {c.name for c in client.session.cookies}


# --- the reporter's machine, with the real cookie library ---------------------

def _firefox_profile_signed_in(home, root=None):
    """A Linux Firefox profile, signed in to Overleaf, laid out where Firefox puts it."""
    root = root or home / ".mozilla" / "firefox"
    profile = root / "abcd1234.default-release"
    profile.mkdir(parents=True)
    (root / "profiles.ini").write_text(
        "[Profile0]\nName=default-release\nIsRelative=1\nPath=abcd1234.default-release\nDefault=1\n",
        encoding="utf-8")
    with sqlite3.connect(profile / "cookies.sqlite") as db:
        db.execute("create table moz_cookies (id integer primary key, originAttributes text, "
                   "name text, value text, host text, path text, expiry integer, lastAccessed integer, "
                   "creationTime integer, isSecure integer, isHttpOnly integer)")
        db.execute("insert into moz_cookies (originAttributes, name, value, host, path, expiry, "
                   "lastAccessed, creationTime, isSecure, isHttpOnly) values ('', ?, ?, ?, '/', ?, 0, 0, 1, 1)",
                   (SESSION, "s%3Areal-looking-session", ".overleaf.com", int(time.time()) + 86400))


def test_the_reported_linux_setup_signs_in_with_firefox(monkeypatch, tmp_path, pyoverleaf):
    """Real browser_cookie3, on Linux, with only Firefox signed in: the setup
    in the report. Its own load() still crashes there, on its Arc reader."""
    pytest.importorskip("browser_cookie3")
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))     # what expanduser reads on Windows
    _firefox_profile_signed_in(tmp_path)

    client = OverleafClient()
    client.connect(browser="auto")
    assert client.browser_used == "firefox"
    assert {c.name: c.value for c in client.session.cookies}[SESSION] == "s%3Areal-looking-session"


# --- a session the server has forgotten ---------------------------------------

def test_auto_passes_over_a_browser_whose_session_has_expired(monkeypatch, pyoverleaf, live_sessions):
    """Firefox is tried first, so a session left there months ago used to win
    over the browser actually in use, and the export failed as signed out."""
    _fake_cookie_library(monkeypatch, {
        "firefox": _jar(SESSION, "a_stale_marker"),
        "safari": _jar(SESSION, "b_live_marker"),
    })
    live_sessions["a_stale_marker"] = False
    client = OverleafClient()
    client.connect(browser="auto")
    assert client.browser_used == "safari"


def test_only_expired_sessions_are_reported_as_expired(monkeypatch, pyoverleaf, live_sessions):
    _fake_cookie_library(monkeypatch, {"firefox": _jar(SESSION, "a_stale_marker")})
    live_sessions["a_stale_marker"] = False
    with pytest.raises(UserFacingError) as caught:
        OverleafClient().connect(browser="auto")
    assert "firefox: signed out, its saved session has expired" in str(caught.value)


def test_a_session_that_cannot_be_checked_is_used_anyway(monkeypatch, pyoverleaf, live_sessions):
    """Unsure, for example offline: the export says what went wrong itself."""
    _fake_cookie_library(monkeypatch, {"firefox": _jar(SESSION, "a_unsure_marker")})
    live_sessions["a_unsure_marker"] = None
    client = OverleafClient()
    client.connect(browser="auto")
    assert client.browser_used == "firefox"


def test_the_liveness_check_reads_the_login_redirect(monkeypatch):
    """The real method, against a server that redirects to the login page."""
    monkeypatch.undo()                  # the autouse stub is not wanted here
    calls = []

    class Reply:
        def __init__(self, status, location=""):
            self.status_code, self.headers = status, {"Location": location}
            self.is_redirect = status in (301, 302, 303, 307, 308)
            self.ok = status < 400

    for status, location, expected in [(302, "/login?redir=%2Fproject", False), (200, "", True),
                                       (403, "", False), (500, "", None)]:
        monkeypatch.setattr(requests.Session, "get",
                            lambda self, url, **kw: calls.append(url) or Reply(status, location))
        assert OverleafClient(base_url="https://latex.example.edu")._session_is_live(_jar(SESSION)) is expected
    assert calls[0] == "https://latex.example.edu/project"


def test_an_expired_session_names_the_server_and_the_browser(monkeypatch):
    """It said www.overleaf.com whatever the server, and "your browser"."""
    client = OverleafClient(base_url="https://latex.example.edu")
    client.connect(browser="manual", cookie_value="overleaf.sid=s%3Aabc")
    client.browser_used = "firefox"

    class Refused:
        status_code, ok, headers = 401, False, {}

    monkeypatch.setattr(client, "_request", lambda url, **kw: Refused())
    with pytest.raises(UserFacingError) as caught:
        client.get_threads("a" * 24)
    assert "https://latex.example.edu in Firefox" in str(caught.value)
    assert "www.overleaf.com" not in str(caught.value)


# --- where Firefox keeps profiles on Linux now ----------------------------------

@pytest.mark.parametrize("where", [".config/mozilla/firefox",
                                   ".var/app/org.mozilla.firefox/config/mozilla/firefox",
                                   ".var/app/org.mozilla.firefox/.mozilla/firefox"],
                         ids=["firefox-147-xdg", "flatpak-xdg", "flatpak-legacy"])
def test_firefox_is_found_where_newer_linux_installs_keep_it(monkeypatch, tmp_path, pyoverleaf, where):
    """browser-cookie3 0.20 looks only in ~/.mozilla and the Snap folder."""
    pytest.importorskip("browser_cookie3")
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _firefox_profile_signed_in(tmp_path, root=tmp_path / where)

    client = OverleafClient()
    client.connect(browser="firefox")
    assert {c.name: c.value for c in client.session.cookies}[SESSION] == "s%3Areal-looking-session"


# --- links ------------------------------------------------------------------------

@pytest.mark.parametrize("link", ["https://www.overleaf.com/read/abcdefghijkl",
                                  "https://www.overleaf.com/7581234567xvbnmqwertyz",
                                  "https://www.overleaf.com/read/abcdefghijkl#abc123"])
def test_a_share_link_is_explained_not_reported_as_a_bug(link):
    """What a co-author sends from the Share button. It printed a traceback."""
    from overleaf_comments_export.client import parse_project_id
    with pytest.raises(UserFacingError) as caught:
        parse_project_id(link)
    assert "link-sharing link" in str(caught.value)
    assert isinstance(caught.value, ValueError), "callers that check for ValueError broke"


def test_the_command_line_explains_a_share_link_without_a_traceback(capsys):
    from overleaf_comments_export.__main__ import main
    code = main(["--project-url", "https://www.overleaf.com/read/abcdefghijkl",
                 "--out", "unused", "--cookie", "overleaf_session2=x"])
    err = capsys.readouterr().err
    assert code == 1
    assert "link-sharing link" in err
    assert "Traceback" not in err and "looks like a bug" not in err


# --- the file tree over pyoverleaf's socket ---------------------------------------------

def test_the_file_tree_call_cannot_hang_the_export(monkeypatch):
    """pyoverleaf's socket has no timeout and waits in a loop for one message."""
    import threading
    from overleaf_comments_export import client as client_mod
    monkeypatch.setattr(client_mod, "PYOVERLEAF_SECONDS", 0.2)
    never = threading.Event()

    class Stuck:
        def project_get_files(self, project_id):
            never.wait()                 # what a socket that never answers does

    client = OverleafClient()
    client._api = Stuck()
    monkeypatch.setattr(client, "scrape_project_html", lambda pid: {})
    started = time.monotonic()
    result = client.get_project_metadata("a" * 24)
    assert time.monotonic() - started < 5
    assert result["files"] is None
    never.set()
