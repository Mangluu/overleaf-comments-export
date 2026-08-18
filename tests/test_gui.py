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
    assert not app.base_entry.grid_info() != {}
    app.self_hosted_var.set(True)
    app._toggle_self_hosted()
    app.root.update()
    assert app.base_entry.grid_info() != {}


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
    assert not app.cookie_frame.grid_info() != {}

    app.browser_box.set("I will paste it myself")
    app._on_browser_change()
    app.root.update()
    assert app.cookie_frame.grid_info() != {}
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
    """It opens in a window of its own, so the main one keeps its size."""
    assert app.details_window is None
    assert app.log is None


def test_the_log_keeps_what_was_said_while_it_was_shut(app):
    """Lines arrive during an export whether or not the window is open."""
    app._append_log("said while shut")
    app.details_var.set(True)
    app._toggle_details()
    assert "said while shut" in app.log.get("1.0", "end")
    app._append_log("said while open")
    assert "said while open" in app.log.get("1.0", "end")
    app.details_var.set(False)
    app._toggle_details()
    assert app.details_window is None and app.log is None
    app._append_log("safe with it shut")


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


def test_nothing_scrolls_and_it_all_fits(app):
    """The form used to scroll, which hid half the decisions and made the
    wheel behaviour matter. Now everything is on screen at once."""
    app.root.update_idletasks()
    assert not hasattr(app, "canvas"), "the scrolling canvas is gone"
    # A window taller than this does not fit a 1280x800 laptop once the menu
    # bar and dock are taken off, and there is no scrollbar to rescue it.
    # Must fit a 1280x800 laptop once the menu bar and dock are gone.
    assert app.root.winfo_reqheight() < 780, app.root.winfo_reqheight()


def test_the_progress_bar_is_hidden_until_something_runs(app):
    """An idle indeterminate bar reads as a stuck one."""
    assert not app.progress.winfo_manager(), "an idle bar reads as a stuck one"


def test_optional_rows_do_not_push_anything_out_of_reach(app):
    """Ticking the self-hosted box and choosing to paste a cookie both add
    rows, and the window has to ask for the room.

    This used to assert winfo_height() >= winfo_reqheight(), which measures
    what the window manager did rather than what the window asked for. On a
    withdrawn window that is whatever was last applied, so it passed on a
    developer's machine and failed the moment CI ran it headless. It also
    could not have held on a screen too short for the content, which is a
    real gap tracked separately.
    """
    app.root.update_idletasks()
    app.self_hosted_var.set(True)
    app._toggle_self_hosted()
    app.browser_box.set("I will paste it myself")
    app._on_browser_change()
    app.root.update_idletasks()

    # The window asks for everything it needs, up to what the screen allows.
    assert app.root.minsize()[1] == min(
        app.root.winfo_reqheight(), app.root.winfo_screenheight() - 140)




def test_the_window_never_grows_past_the_screen(app):
    """A window taller than the display is no more reachable than a card
    scrolled off the bottom."""
    app.details_var.set(True)
    app._toggle_details()
    app.root.update_idletasks()
    assert app.root.winfo_height() <= app.root.winfo_screenheight()


def test_settings_that_cannot_be_saved_say_so(tmp_path, monkeypatch):
    """It used to fail in total silence, so everything you typed came back
    empty next time with nothing said and nothing logged."""
    from overleaf_comments_export import gui

    # A file where the folder should be, so writing into it cannot work.
    blocked = tmp_path / "wall"
    blocked.write_text("not a folder", encoding="utf-8")
    monkeypatch.setattr(gui, "CONFIG_PATH", blocked / "config.json")

    why = gui._save_config({"project_url": "https://www.overleaf.com/project/x"})
    assert why, "a failed save reported nothing"
    assert isinstance(why, str)


def test_a_save_that_works_reports_nothing(tmp_path, monkeypatch):
    from overleaf_comments_export import gui
    monkeypatch.setattr(gui, "CONFIG_PATH", tmp_path / "sub" / "config.json")
    assert gui._save_config({"a": 1}) is None
    assert (tmp_path / "sub" / "config.json").exists(), "it did not make the folder"
