"""The setup check.

Every problem people hit was diagnosable and nobody diagnosed it: an old
version pip had left in place, a cookie store behind Full Disk Access, a Python
with no root certificates. This is one command that looks at all of them.
"""

from __future__ import annotations

import pytest

from overleaf_comments_export import doctor


def _report(**kwargs) -> tuple[str, int]:
    lines: list[str] = []
    code = doctor.run(out=lines.append, **kwargs)
    return "\n".join(lines), code


def test_it_reports_and_says_nothing_is_wrong_when_nothing_is(monkeypatch):
    monkeypatch.setattr(doctor, "_signed_in",
                        lambda *a: [doctor.Check("Signing in", doctor.OK, "found a session")])
    monkeypatch.setattr(doctor, "_reachable",
                        lambda url: doctor.Check("Overleaf", doctor.OK, "answered 200"))
    monkeypatch.setattr(doctor, "_latest_release",
                        lambda: doctor.Check("Newest release", doctor.OK, "up to date"))
    text, code = _report()
    assert code == 0
    assert "Everything" in text


def test_a_broken_login_is_a_fix_not_a_note(monkeypatch):
    """The exit code matters: it is what a script or a support reply keys on."""
    monkeypatch.setattr(doctor, "_signed_in", lambda *a: [
        doctor.Check("Signing in", doctor.BAD, "no session", "Paste the cookie instead.")])
    monkeypatch.setattr(doctor, "_reachable",
                        lambda url: doctor.Check("Overleaf", doctor.OK, "answered 200"))
    monkeypatch.setattr(doctor, "_latest_release",
                        lambda: doctor.Check("Newest release", doctor.OK, "up to date"))
    text, code = _report()
    assert code == 1
    assert "FIX" in text
    assert "Paste the cookie instead." in text, "the remedy has to be printed"
    assert "to fix before this will work" in text


def test_an_old_version_says_to_use_upgrade(monkeypatch):
    """The failure that cost the most: pip says "already satisfied" and stops."""
    class Response:
        @staticmethod
        def json():
            return {"info": {"version": "99.0.0"}}

    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: Response())
    check = doctor._latest_release()
    assert check.state == doctor.WARN
    assert "--upgrade" in check.fix
    assert "Requirement already satisfied" in check.fix


def test_being_up_to_date_is_not_a_warning(monkeypatch):
    from overleaf_comments_export import __version__

    class Response:
        @staticmethod
        def json():
            return {"info": {"version": __version__}}

    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: Response())
    assert doctor._latest_release().state == doctor.OK


def test_pypi_being_unreachable_is_only_a_note(monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.exceptions.ConnectionError("offline")

    monkeypatch.setattr(requests, "get", boom)
    check = doctor._latest_release()
    assert check.state == doctor.WARN, "being offline must not read as broken"


def test_missing_pdf_support_is_a_note_not_a_failure(monkeypatch):
    """Everything except commented.pdf works without it."""
    import builtins

    real = builtins.__import__

    def no_pymupdf(name, *a, **k):
        if name == "pymupdf":
            raise ImportError("nope")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_pymupdf)
    check = doctor._pdf_support()
    assert check.state == doctor.WARN
    assert "[pdf]" in check.fix


def test_the_session_check_can_be_skipped(monkeypatch):
    """It is the only part that touches the browser, so it must be optional."""
    monkeypatch.setattr(doctor, "_reachable",
                        lambda url: doctor.Check("Overleaf", doctor.OK, "answered 200"))
    monkeypatch.setattr(doctor, "_latest_release",
                        lambda: doctor.Check("Newest release", doctor.OK, "up to date"))
    text, code = _report(check_session=False)
    assert "not checked" in text
    assert code == 0, "skipping a check is not a failure"


def test_an_unreachable_overleaf_explains_the_network(monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.exceptions.ConnectionError("Failed to resolve 'www.overleaf.com'")

    monkeypatch.setattr(requests, "get", boom)
    check = doctor._reachable("https://www.overleaf.com")
    assert check.state == doctor.BAD
    assert "network problem" in check.fix
