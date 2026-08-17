"""Check the setup and say, in plain words, what is wrong.

Everything that went wrong for people so far was diagnosable and nobody
diagnosed it. Someone ran a version from months earlier because `pip install`
without `--upgrade` says "Requirement already satisfied" and stops. Someone
else could not read a cookie because a downloaded app has no Full Disk Access.
A third had no root certificates because Python was installed without running
Install Certificates.

None of those announce themselves. This does one pass over the things that
break, and prints what to do about each.
"""

from __future__ import annotations

import platform
import ssl
import sys
from dataclasses import dataclass
from typing import Callable

from . import __version__

OK, WARN, BAD = "ok", "warn", "bad"

# What the symbols mean, spelled out, because a bare tick and cross in a
# terminal is not obvious to everyone who will run this.
_MARK = {OK: "  ok  ", WARN: " note ", BAD: " FIX  "}


@dataclass
class Check:
    name: str
    state: str
    detail: str
    fix: str = ""


def _python() -> Check:
    v = sys.version_info
    if v < (3, 10):
        return Check("Python", BAD, f"{platform.python_version()}",
                     "This needs Python 3.10 or newer. Install a current "
                     "Python from python.org and try again.")
    return Check("Python", OK, f"{platform.python_version()} at {sys.executable}")


def _version() -> Check:
    """The commonest silent failure: an old copy that pip did not replace."""
    return Check(
        "This tool", OK, f"{__version__}",
        "" if __version__ else "",
    )


def _latest_release() -> Check:
    try:
        # requests rather than urllib, because urllib uses Python's own
        # certificate store and on the machines that most need this check
        # there isn't one. requests carries certifi.
        import requests

        latest = requests.get(
            "https://pypi.org/pypi/overleaf-comments-export/json", timeout=10
        ).json()["info"]["version"]
    except Exception as e:
        return Check("Newest release", WARN, f"could not ask PyPI ({type(e).__name__})",
                     "Not a problem in itself. It only means this check could "
                     "not confirm you are up to date.")
    if latest == __version__:
        return Check("Newest release", OK, f"{latest}, which is what you have")
    return Check(
        "Newest release", WARN, f"{latest}, and you have {__version__}",
        'Update with:  pip install --upgrade "overleaf-comments-export[gui,pdf]"\n'
        "         Without --upgrade pip leaves the old one in place and says "
        '"Requirement already satisfied".',
    )


def _certificates() -> Check:
    if ssl.create_default_context().cert_store_stats()["x509_ca"] > 0:
        return Check("Certificates", OK, "root certificates are installed")
    return Check(
        "Certificates", WARN, "this Python has no root certificates",
        "Anything that does not carry its own would fail to verify. This tool "
        "falls back to the ones it ships with, so it still works. To fix it "
        "properly, run Install Certificates.command in your "
        "/Applications/Python 3.x/ folder.",
    )


def _pdf_support() -> Check:
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        return Check(
            "PDF export", WARN, "PyMuPDF is not installed",
            "Everything else works. To get commented.pdf, install with:\n"
            '         pip install --upgrade "overleaf-comments-export[pdf]"',
        )
    return Check("PDF export", OK, "PyMuPDF is installed")


def _window() -> Check:
    try:
        import tkinter  # noqa: F401
    except ImportError:
        return Check(
            "The window", WARN, "this Python has no Tk toolkit",
            "The command line works regardless. For the window, install "
            "python3-tk on Debian or Ubuntu, python3-tkinter on Fedora, or "
            "use the Python from python.org on macOS and Windows.",
        )
    return Check("The window", OK, "Tk is available")


def _reachable(base_url: str) -> Check:
    import requests

    try:
        r = requests.get(base_url, timeout=15)
    except Exception as e:
        from .client import _network_hint

        return Check("Overleaf", BAD, f"could not be reached ({type(e).__name__})",
                     _network_hint(e))
    return Check("Overleaf", OK if r.ok else WARN, f"{base_url} answered {r.status_code}",
                 "" if r.ok else "That is not the usual answer. If it persists, "
                                 "check the address.")


def _signed_in(base_url: str, browser: str, cookie_value: str | None,
               cookie_name: str | None) -> list[Check]:
    """The one that matters most, and the one that fails most."""
    from .client import OverleafClient, UserFacingError

    client = OverleafClient(base_url=base_url, cookie_name=cookie_name)
    try:
        client.connect(browser=browser, cookie_value=cookie_value)
    except UserFacingError as e:
        where = "the cookie you pasted" if cookie_value else f"{browser}"
        return [Check("Signing in", BAD, f"no Overleaf session found in {where}", str(e))]
    except Exception as e:
        return [Check("Signing in", BAD, f"{type(e).__name__}: {e}",
                      "That is unexpected. Please report it with this output.")]

    checks = [Check("Signing in", OK, "found a session")]
    try:
        r = client.session.get(f"{client.base_url}/project", timeout=20,
                               allow_redirects=False)
        if r.status_code in (301, 302, 303, 307, 308) and "login" in r.headers.get("Location", "").lower():
            checks.append(Check(
                "The session", BAD, "Overleaf sent us to the login page",
                "The session has expired. Sign in to Overleaf in your browser "
                "again, then re-run this."))
        else:
            checks.append(Check("The session", OK, "Overleaf accepted it"))
    except Exception as e:
        checks.append(Check("The session", WARN, f"could not be confirmed ({type(e).__name__})",
                            "The session was found but not tested."))
    return checks


def run(base_url: str = "https://www.overleaf.com", browser: str = "auto",
        cookie_value: str | None = None, cookie_name: str | None = None,
        check_session: bool = True,
        out: Callable[[str], None] = print) -> int:
    """Print the report. Returns 0 when nothing needs fixing, 1 otherwise."""
    checks = [_python(), _version(), _latest_release(), _certificates(),
              _pdf_support(), _window(), _reachable(base_url)]
    if check_session:
        checks += _signed_in(base_url, browser, cookie_value, cookie_name)
    else:
        checks.append(Check("Signing in", WARN, "not checked",
                            "Re-run without --no-session to test your login."))

    out(f"overleaf-comments-export {__version__} on "
        f"{platform.system()} {platform.release()}")
    out("")
    width = max(len(c.name) for c in checks)
    for c in checks:
        out(f"[{_MARK[c.state]}] {c.name.ljust(width)}  {c.detail}")
        if c.fix and c.state != OK:
            for line in c.fix.splitlines():
                out(f"           {line}")
            out("")

    bad = [c for c in checks if c.state == BAD]
    warn = [c for c in checks if c.state == WARN]
    out("")
    if bad:
        out(f"{len(bad)} thing(s) to fix before this will work.")
    elif warn:
        out("Everything needed is working. The notes above are optional.")
    else:
        out("Everything checks out.")
    return 1 if bad else 0
