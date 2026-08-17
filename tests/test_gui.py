"""Tests for the window.

These build a real Tk window, so they skip anywhere without a display (CI on
Linux, an SSH session). What they check is the wiring a non-technical user
depends on: that every feature is reachable, that the fields that should hide
do hide, and that bad input is caught before anything runs.
"""

from __future__ import annotations

import os

import pytest

tk = pytest.importorskip("tkinter")

# Opening real windows hangs on some machines, and a test suite that can hang
# is worse than one that skips. Run these deliberately:
#     OCE_GUI_TESTS=1 pytest tests/test_gui.py
pytestmark = pytest.mark.skipif(
    not os.environ.get("OCE_GUI_TESTS"),
    reason="set OCE_GUI_TESTS=1 to run the window tests",
)


@pytest.fixture()
def app():
    from overleaf_comments_export.gui import App
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    root.withdraw()
    a = App(root)
    yield a
    root.destroy()


def test_every_feature_is_reachable_from_the_window(app):
    """The CLI and the window must not drift apart. Someone who never opens a
    terminal should be able to get at all of it."""
    for name in [
        "include_open_var", "include_resolved_var", "include_changes_var",
        "response_letter_var", "per_reviewer_var", "annotated_var",
        "stable_var", "detailed_var", "write_jsonl_var", "include_raw_var",
        "reviewer_filter_var", "browser_var", "cookie_var", "base_var",
        "url_var", "out_var", "title_var",
    ]:
        assert hasattr(app, name), f"{name} is not exposed in the window"


def test_bad_link_is_flagged_while_typing(app):
    app.url_var.set("https://example.com/not-a-project")
    app.root.update()
    assert "does not look like" in app.url_status.cget("text")


def test_good_link_is_confirmed(app):
    app.url_var.set("https://www.overleaf.com/project/507f1f77bcf86cd799439011")
    app.root.update()
    assert "Looks right" in app.url_status.cget("text")


def test_self_hosted_address_is_hidden_until_asked_for(app):
    assert not app.base_entry.winfo_ismapped()
    app.self_hosted_var.set(True)
    app._toggle_self_hosted()
    app.root.update()
    assert app.base_entry.winfo_ismapped()


def test_unticking_self_hosted_restores_the_normal_address(app):
    app.self_hosted_var.set(True)
    app._toggle_self_hosted()
    app.base_var.set("https://overleaf.my-uni.edu")
    app.self_hosted_var.set(False)
    app._toggle_self_hosted()
    assert app.base_var.get() == "https://www.overleaf.com"


def test_cookie_box_appears_only_when_pasting(app):
    app.browser_box.set("Safari")
    app._on_browser_change()
    app.root.update()
    assert not app.cookie_entry.winfo_ismapped()

    app.browser_box.set("I will paste it myself")
    app._on_browser_change()
    app.root.update()
    assert app.cookie_entry.winfo_ismapped()
    assert app.browser_var.get() == "manual"


def test_password_prompting_browsers_are_hidden_by_default(app):
    shown = list(app.browser_box.cget("values"))
    assert "Google Chrome" not in shown
    app.show_advanced_var.set(True)
    app._refresh_browser_choices()
    assert "Google Chrome" in list(app.browser_box.cget("values"))


def test_cookie_is_masked_on_screen(app):
    """It is a key to the account, so it should not be readable over a shoulder."""
    assert app.cookie_entry.cget("show") == "•"


def test_technical_log_starts_hidden(app):
    assert not app.details_var.get()
    assert not app.details.winfo_ismapped()


def test_stop_button_appears_only_while_running_and_recovers(app):
    """Until this existed the Run button stayed disabled until the export
    finished, which on a hung step meant forever."""
    import threading
    import time

    assert not app.stop_btn.winfo_manager(), "Stop is showing before anything runs"

    app.run_btn.configure(state="disabled")
    app.stop_btn.pack(side="left")
    app.worker = threading.Thread(target=lambda: time.sleep(5), daemon=True)
    app.worker.start()

    app._on_stop()
    assert app.cancel_requested is True
    # str(): ttk returns a Tcl index object here rather than a plain string.
    assert str(app.stop_btn.cget("state")) == "disabled", "Stop can be pressed twice"

    app._on_cancelled()
    assert str(app.run_btn.cget("state")) == "normal", "Run never came back"
    assert not app.stop_btn.winfo_manager()
    assert app.cancel_requested is False, "the flag would cancel the next run too"


def test_stop_does_nothing_when_nothing_is_running(app):
    app.worker = None
    app._on_stop()
    assert app.cancel_requested is False


def test_the_wheel_moves_the_page_on_every_platform(app, monkeypatch):
    """A Mac trackpad sends a delta of 1 or 2. Dividing it by three and
    truncating, as this used to, scrolled zero units and the window did not
    move at all."""
    import sys as _sys

    class Event:
        def __init__(self, delta=0, num=None):
            self.delta, self.num = delta, num

    monkeypatch.setattr(_sys, "platform", "darwin")
    assert app._wheel_units(Event(delta=1)) == -1, "a small trackpad move did nothing"
    assert app._wheel_units(Event(delta=2)) == -2
    assert app._wheel_units(Event(delta=-1)) == 1, "it must scroll both ways"

    monkeypatch.setattr(_sys, "platform", "win32")
    assert app._wheel_units(Event(delta=120)) == -3, "one notch, not forty lines"
    assert app._wheel_units(Event(delta=-120)) == 3

    # X11 sends buttons rather than a delta, and used to be ignored entirely.
    assert app._wheel_units(Event(num=4)) == -3
    assert app._wheel_units(Event(num=5)) == 3


def test_the_log_keeps_its_own_wheel(app):
    """bind_all took the wheel from every widget, so the log could not be
    scrolled once it was longer than its box."""
    import tkinter as tk

    scrolled = []
    app.canvas.yview_scroll = lambda *a: scrolled.append(a)

    class Event:
        delta, num = 3, None
        widget = None

    event = Event()
    event.widget = app.log
    app._on_wheel(event)
    assert not scrolled, "the page moved instead of the log"

    event.widget = app.canvas
    app._on_wheel(event)
    assert scrolled, "the page did not move"
