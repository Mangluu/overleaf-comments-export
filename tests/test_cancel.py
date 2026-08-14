"""Stopping an export part way through.

An export can take a while, and until this existed there was no way to stop
one. The window's button stayed disabled until it finished, which on a hung
step meant forever.

Cancellation is cooperative. A request already in flight cannot be interrupted
from another thread, so the checks sit at every step boundary and inside the
loops. What matters, and what these tests hold to, is that stopping takes
effect promptly and that nothing is left half written.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from overleaf_comments_export import export as export_mod
from overleaf_comments_export.export import ExportCancelled

# The fake Overleaf lives with the wiring tests. Importing it by path keeps
# one definition rather than two that can drift.
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_export_wiring import DOC_TEXT, FakeClient  # noqa: E402


def _run(out_dir: Path, should_cancel, **kwargs):
    return export_mod.run_export(
        project_url="https://www.overleaf.com/project/" + "a" * 24,
        out_dir=out_dir, should_cancel=should_cancel, **kwargs,
    )


def test_stopping_immediately_writes_nothing_but_the_log(tmp_path, monkeypatch):
    monkeypatch.setattr(export_mod, "OverleafClient", FakeClient)
    with pytest.raises(ExportCancelled):
        _run(tmp_path, lambda: True)
    left = sorted(p.name for p in tmp_path.iterdir())
    assert left == ["comments.log"], f"a cancelled export left {left} behind"


def test_stopping_part_way_through_writes_nothing(tmp_path, monkeypatch):
    """Stop once the documents are being fetched, which is where a real export
    spends its time."""
    calls = {"n": 0}

    class Slow(FakeClient):
        def download_doc_text(self, project_id, doc_id):
            calls["n"] += 1
            return DOC_TEXT

    monkeypatch.setattr(export_mod, "OverleafClient", Slow)
    with pytest.raises(ExportCancelled):
        _run(tmp_path, lambda: calls["n"] >= 1)
    assert not (tmp_path / "comments.json").exists()
    assert not list(tmp_path.glob("comments-*.md"))


def test_an_export_that_is_not_cancelled_still_finishes(tmp_path, monkeypatch):
    """The checks must not be able to stop an export nobody asked to stop."""
    monkeypatch.setattr(export_mod, "OverleafClient", FakeClient)
    result = _run(tmp_path, lambda: False)
    assert json.loads(result.json_path.read_text(encoding="utf-8"))["comments"]


def test_no_cancel_check_at_all_is_fine(tmp_path, monkeypatch):
    """The command line passes nothing, and everything else calling this as a
    library predates the parameter."""
    monkeypatch.setattr(export_mod, "OverleafClient", FakeClient)
    result = export_mod.run_export(
        project_url="https://www.overleaf.com/project/" + "a" * 24, out_dir=tmp_path)
    assert result.thread_count == 1


def test_the_client_stops_between_retries(monkeypatch):
    """A failing request backs off for seconds at a time. Stopping should not
    have to wait out the whole delay."""
    import requests

    from overleaf_comments_export.client import OverleafClient

    client = OverleafClient()
    client.connect(browser="manual", cookie_value="overleaf_session2=s%3Aabc")
    attempts = {"n": 0}

    def flaky(method, url, **kwargs):
        attempts["n"] += 1
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(client.session, "request", flaky)
    client.should_cancel = lambda: attempts["n"] >= 1
    with pytest.raises(ExportCancelled):
        client._request("https://www.overleaf.com/project/x/threads")
    assert attempts["n"] == 1, "it retried after being asked to stop"


def test_waiting_out_a_backoff_notices_a_cancel_quickly():
    """The wait is broken into short steps so a stop is seen while waiting."""
    import time

    from overleaf_comments_export.client import OverleafClient

    client = OverleafClient()
    client.should_cancel = lambda: True
    began = time.monotonic()
    with pytest.raises(ExportCancelled):
        client._sleep(30)
    assert time.monotonic() - began < 1, "it slept through the cancel"
