from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .client import UserFacingError
from .export import ExportResult, run_export


def _config_path() -> Path:
    """Per-user config location, cross-platform.

    Uses platformdirs when available (preferred for cross-platform correctness);
    falls back to ~/.overleaf_comments_export.json if the dependency is missing
    (lets the library run without it as a soft dep)."""
    try:
        from platformdirs import user_config_dir  # type: ignore
        d = Path(user_config_dir("overleaf-comments-export", "overleaf-comments-export"))
        d.mkdir(parents=True, exist_ok=True)
        return d / "config.json"
    except ImportError:
        return Path.home() / ".overleaf_comments_export.json"


CONFIG_PATH = _config_path()

BROWSER_LABELS = {
    "safari": "Safari — reads its cookie file, no password prompt",
    "firefox": "Firefox — reads its cookie file, no password prompt",
    "manual": "Paste the cookie myself — works on every computer",
    "auto": "Auto-detect (try all installed browsers)",
    "chrome": "Google Chrome (will prompt for Keychain password)",
    "chromium": "Chromium (will prompt for Keychain password)",
    "edge": "Microsoft Edge (will prompt for Keychain password)",
    "brave": "Brave (will prompt for Keychain password)",
}

PRIVACY_FRIENDLY = ("safari", "firefox", "manual")
ADVANCED_BROWSERS = ("auto", "chrome", "chromium", "edge", "brave")

COOKIE_HELP_TEXT = """\
How to copy your Overleaf session cookie
────────────────────────────────────────
You only need to do this when reading the cookie straight from your browser
does not work (common with Chrome on Windows, and with browsers installed
from the Snap store on Linux).

1. Open your paper in Overleaf, in any browser, and make sure you are
   signed in.

2. Open the developer tools:
   • Windows / Linux : press F12
   • Mac             : press Command + Option + I

3. Find the cookie list:
   • Chrome / Edge / Brave : click the "Application" tab, then in the left
     sidebar open "Cookies" and click "https://www.overleaf.com"
   • Firefox               : click the "Storage" tab, then "Cookies"
   • Safari                : click the "Storage" tab, then "Cookies"
     (Safari needs Develop menu enabled: Settings → Advanced →
      "Show features for web developers")

4. In the list, find the row named exactly:  overleaf_session2

5. Double-click its "Value" and copy the whole thing. It is a long piece of
   text that usually starts with  s%3A

6. Paste it into the box in this window and click Export Comments.

Notes
─────
• The cookie is like a temporary key to your account. Do not share it with
  anyone. It stops working when you sign out of Overleaf.
• This app does not save the cookie anywhere. It is kept in memory only
  while the export runs, unless you tick "Remember cookie".
"""

PRIVACY_INFO_TEXT = """\
What this app reads from your machine
─────────────────────────────────────
• Your Overleaf session cookie. This is the same cookie your browser uses to
  stay signed in to overleaf.com. Without it, the Overleaf server won't return
  your comments.

Where it reads the cookie from, by browser:
• Paste it myself → nothing on this computer is read at all; you supply the
             cookie directly. The most private option, and the one that works
             on every operating system.
• Safari   → its cookie file (macOS may ask permission the first time)
• Firefox  → its cookies.sqlite file (no Keychain access required)
• Chrome / Edge / Brave / Chromium → cookies are encrypted on disk and the key
             lives in the system Keychain, so reading them prompts for your
             login password every single time.

The cookie is used only to make HTTPS requests to www.overleaf.com.
Nothing is sent anywhere else. There is no telemetry.

What's saved to disk
────────────────────
• Your last-used inputs (browser choice, project link, output folder) go in a
  small settings file so the form fills itself in next time. Delete it any
  time — its exact location is shown at the bottom of this window.
• The export itself (Markdown + JSON + log) goes only to the folder you pick.
• Diagnostic logs go to your user log folder.

About the session cookie
────────────────────────
• It is normally kept in memory only, and forgotten when the app closes.
• It is written to the settings file ONLY if you tick "Remember cookie on
  this computer". That file is not encrypted, so leave the box unticked on
  a shared machine.
• Your Overleaf password is never asked for and never stored.
"""


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save_config(data: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Overleaf Comments Export")
        root.geometry("720x780")
        root.minsize(560, 600)

        self.config = _load_config()
        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.last_result: ExportResult | None = None

        self._apply_theme()

        outer = ttk.Frame(root, padding=14)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(
            outer,
            text="Export comment threads and tracked changes from an Overleaf paper.",
            wraplength=620,
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 12))
        row += 1

        # Browser
        ttk.Label(outer, text="Browser:").grid(row=row, column=0, sticky="w", pady=4)
        default_browser = self.config.get("browser", "safari")
        if default_browser not in BROWSER_LABELS:
            default_browser = "safari"
        self.browser_var = tk.StringVar(value=default_browser)
        self.browser_box = ttk.Combobox(
            outer,
            textvariable=self.browser_var,
            state="readonly",
            width=20,
        )
        self.browser_box.grid(row=row, column=1, sticky="w", pady=4)
        self.browser_box.bind(
            "<<ComboboxSelected>>", lambda _e: self._on_browser_change()
        )
        self.browser_help = ttk.Label(
            outer, text="", foreground="#666", wraplength=320
        )
        self.browser_help.grid(row=row, column=2, sticky="w", padx=6, pady=4)
        row += 1

        # Show-advanced checkbox + privacy info button
        adv_row = ttk.Frame(outer)
        adv_row.grid(row=row, column=1, columnspan=2, sticky="w", pady=(0, 4))
        self.show_advanced_var = tk.BooleanVar(
            value=bool(self.config.get("show_advanced_browsers", False))
            or default_browser in ADVANCED_BROWSERS
        )
        ttk.Checkbutton(
            adv_row,
            text="Show Chrome / Edge / Brave (uses Keychain)",
            variable=self.show_advanced_var,
            command=self._refresh_browser_choices,
        ).pack(side="left")
        ttk.Button(
            adv_row, text="Privacy info…", command=self._show_privacy_info
        ).pack(side="left", padx=(12, 0))
        row += 1

        self._refresh_browser_choices()

        # Cookie paste row (shown only when "Paste the cookie myself" is picked)
        self.cookie_label = ttk.Label(outer, text="Session cookie:")
        self.cookie_label.grid(row=row, column=0, sticky="w", pady=4)
        cookie_row = ttk.Frame(outer)
        cookie_row.grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
        cookie_row.columnconfigure(0, weight=1)
        self.cookie_var = tk.StringVar(value=self.config.get("cookie_value", ""))
        self.cookie_entry = ttk.Entry(
            cookie_row, textvariable=self.cookie_var, show="•"
        )
        self.cookie_entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(
            cookie_row, text="How?", width=6, command=self._show_cookie_help
        ).grid(row=0, column=1, padx=(6, 0))
        self.remember_cookie_var = tk.BooleanVar(
            value=bool(self.config.get("remember_cookie", False))
        )
        self.cookie_remember_cb = ttk.Checkbutton(
            outer,
            text="Remember cookie on this computer (stored unencrypted)",
            variable=self.remember_cookie_var,
        )
        self.cookie_row_widgets = (self.cookie_label, cookie_row, self.cookie_remember_cb)
        row += 1
        self.cookie_remember_cb.grid(row=row, column=1, columnspan=2, sticky="w")
        row += 1
        self._toggle_cookie_row()

        # Project URL
        ttk.Label(outer, text="Overleaf project URL:").grid(
            row=row, column=0, sticky="w", pady=4
        )
        self.url_var = tk.StringVar(value=self.config.get("project_url", ""))
        ttk.Entry(outer, textvariable=self.url_var).grid(
            row=row, column=1, columnspan=2, sticky="ew", pady=4
        )
        row += 1
        ttk.Label(
            outer,
            text="(Open your paper in Overleaf and copy the URL from the address bar.)",
            foreground="#666",
        ).grid(row=row, column=1, columnspan=2, sticky="w")
        row += 1

        # Title
        ttk.Label(outer, text="Paper title (optional):").grid(
            row=row, column=0, sticky="w", pady=4
        )
        self.title_var = tk.StringVar(value=self.config.get("project_title", ""))
        ttk.Entry(outer, textvariable=self.title_var).grid(
            row=row, column=1, columnspan=2, sticky="ew", pady=4
        )
        row += 1

        # Output folder
        ttk.Label(outer, text="Save to folder:").grid(
            row=row, column=0, sticky="w", pady=4
        )
        self.out_var = tk.StringVar(value=self.config.get("out_dir", ""))
        out_entry = ttk.Entry(outer, textvariable=self.out_var)
        out_entry.grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Button(outer, text="Browse…", command=self._pick_folder).grid(
            row=row, column=2, sticky="w", padx=6, pady=4
        )
        row += 1

        # ---- Options (expandable) ----
        self.show_options_var = tk.BooleanVar(
            value=bool(self.config.get("show_options", False))
        )
        ttk.Checkbutton(
            outer,
            text="Show options (filters, output format, extras)",
            variable=self.show_options_var,
            command=self._toggle_options_visibility,
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 0))
        row += 1

        self.options_frame = ttk.LabelFrame(outer, text="Options", padding=8)
        self.options_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(4, 6))
        self.options_frame.columnconfigure(1, weight=1)
        self._build_options_panel(self.options_frame)
        row += 1

        # Action buttons
        button_row = ttk.Frame(outer)
        button_row.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(12, 6))
        self.run_btn = ttk.Button(
            button_row, text="Export Comments", command=self._on_run
        )
        self.run_btn.pack(side="left")
        self.open_md_btn = ttk.Button(
            button_row,
            text="Open Markdown",
            command=self._open_markdown,
            state="disabled",
        )
        self.open_md_btn.pack(side="left", padx=8)
        self.open_folder_btn = ttk.Button(
            button_row,
            text="Open Output Folder",
            command=self._open_folder,
            state="disabled",
        )
        self.open_folder_btn.pack(side="left")
        row += 1

        # Progress + log
        self.progress = ttk.Progressbar(outer, mode="indeterminate")
        self.progress.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        row += 1

        ttk.Label(outer, text="Log:").grid(row=row, column=0, sticky="w")
        row += 1

        log_frame = ttk.Frame(outer)
        log_frame.grid(row=row, column=0, columnspan=3, sticky="nsew")
        outer.rowconfigure(row, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=12, wrap="word", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=log_scroll.set)

        self.root.after(80, self._pump_queue)

    def _apply_theme(self) -> None:
        """Use sv-ttk (modern theme) when available — looks consistent across
        macOS/Windows/Linux. Falls back to native aqua/clam if not installed."""
        try:
            import sv_ttk  # type: ignore
            sv_ttk.set_theme("light")
            return
        except Exception:
            pass
        try:
            style = ttk.Style()
            names = style.theme_names()
            for preferred in ("aqua", "vista", "clam"):
                if preferred in names:
                    style.theme_use(preferred)
                    return
        except Exception:
            pass

    def _build_options_panel(self, parent: ttk.LabelFrame) -> None:
        r = 0
        # Filters
        ttk.Label(parent, text="Include:", foreground="#333").grid(
            row=r, column=0, sticky="w"
        )
        filters_row = ttk.Frame(parent)
        filters_row.grid(row=r, column=1, columnspan=2, sticky="w")
        self.include_open_var = tk.BooleanVar(
            value=bool(self.config.get("include_open", True))
        )
        self.include_resolved_var = tk.BooleanVar(
            value=bool(self.config.get("include_resolved", True))
        )
        self.include_changes_var = tk.BooleanVar(
            value=bool(self.config.get("include_changes", True))
        )
        ttk.Checkbutton(
            filters_row, text="Open comments", variable=self.include_open_var
        ).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(
            filters_row, text="Resolved comments", variable=self.include_resolved_var
        ).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(
            filters_row, text="Tracked changes", variable=self.include_changes_var
        ).pack(side="left")
        r += 1

        ttk.Label(parent, text="Reviewers:", foreground="#333").grid(
            row=r, column=0, sticky="w", pady=(6, 0)
        )
        self.reviewer_filter_var = tk.StringVar(
            value=self.config.get("reviewer_filter", "")
        )
        ttk.Entry(parent, textvariable=self.reviewer_filter_var).grid(
            row=r, column=1, columnspan=2, sticky="ew", pady=(6, 0)
        )
        r += 1
        ttk.Label(
            parent,
            text="(comma-separated name/email substrings; leave empty for all)",
            foreground="#666",
        ).grid(row=r, column=1, columnspan=2, sticky="w")
        r += 1

        ttk.Label(parent, text="Format:", foreground="#333").grid(
            row=r, column=0, sticky="w", pady=(8, 0)
        )
        self.render_mode_var = tk.StringVar(
            value=self.config.get("render_mode", "compact")
        )
        fmt_row = ttk.Frame(parent)
        fmt_row.grid(row=r, column=1, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Radiobutton(
            fmt_row, text="Compact (one-line per comment)",
            variable=self.render_mode_var, value="compact",
        ).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(
            fmt_row, text="Detailed (multi-line code fence)",
            variable=self.render_mode_var, value="detailed",
        ).pack(side="left")
        r += 1

        ttk.Label(parent, text="Extras:", foreground="#333").grid(
            row=r, column=0, sticky="w", pady=(8, 0)
        )
        extras_row = ttk.Frame(parent)
        extras_row.grid(row=r, column=1, columnspan=2, sticky="w", pady=(8, 0))
        self.write_jsonl_var = tk.BooleanVar(
            value=bool(self.config.get("write_jsonl", True))
        )
        self.per_reviewer_var = tk.BooleanVar(
            value=bool(self.config.get("per_reviewer_reports", False))
        )
        self.response_letter_var = tk.BooleanVar(
            value=bool(self.config.get("response_letter", False))
        )
        self.include_raw_var = tk.BooleanVar(
            value=bool(self.config.get("include_raw", False))
        )
        ttk.Checkbutton(
            extras_row,
            text="comments.jsonl (streaming companion)",
            variable=self.write_jsonl_var,
        ).pack(anchor="w")
        ttk.Checkbutton(
            extras_row,
            text="Response letter draft (response-letter.md)",
            variable=self.response_letter_var,
        ).pack(anchor="w")
        ttk.Checkbutton(
            extras_row,
            text="Per-reviewer reports (by-reviewer/<name>.md)",
            variable=self.per_reviewer_var,
        ).pack(anchor="w")
        ttk.Checkbutton(
            extras_row,
            text="Embed raw Overleaf API data in comments.json (larger file)",
            variable=self.include_raw_var,
        ).pack(anchor="w")
        r += 1

        self._toggle_options_visibility()

    def _toggle_options_visibility(self) -> None:
        if self.show_options_var.get():
            self.options_frame.grid()
        else:
            self.options_frame.grid_remove()

    def _on_browser_change(self) -> None:
        key = self.browser_var.get()
        self.browser_help.config(text=BROWSER_LABELS.get(key, key))
        self._toggle_cookie_row()

    def _toggle_cookie_row(self) -> None:
        """Only show the cookie box when the user chose to paste it."""
        widgets = getattr(self, "cookie_row_widgets", None)
        if not widgets:
            return
        show = self.browser_var.get() == "manual"
        for w in widgets:
            if show:
                w.grid()
            else:
                w.grid_remove()

    def _show_cookie_help(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("How to copy your Overleaf cookie")
        win.geometry("640x560")
        win.transient(self.root)
        frame = ttk.Frame(win, padding=12)
        frame.pack(fill="both", expand=True)
        txt = tk.Text(frame, wrap="word")
        txt.insert("1.0", COOKIE_HELP_TEXT)
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True)
        ttk.Button(frame, text="Close", command=win.destroy).pack(
            anchor="e", pady=(8, 0)
        )

    def _refresh_browser_choices(self) -> None:
        """Update the combobox's items based on the advanced toggle."""
        if self.show_advanced_var.get():
            values = list(BROWSER_LABELS.keys())
        else:
            values = list(PRIVACY_FRIENDLY)
        self.browser_box.configure(values=values)
        if self.browser_var.get() not in values:
            self.browser_var.set(values[0])
        self._on_browser_change()

    def _show_privacy_info(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Privacy info")
        win.geometry("620x500")
        win.transient(self.root)
        frame = ttk.Frame(win, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text="What this app touches on your machine",
            font=("", 14, "bold"),
        ).pack(anchor="w", pady=(0, 8))
        txt = tk.Text(frame, wrap="word", height=22)
        txt.insert("1.0", PRIVACY_INFO_TEXT)
        txt.insert("end", f"\nSettings file on this computer:\n{CONFIG_PATH}\n")
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True)
        scroll = ttk.Scrollbar(frame, command=txt.yview)
        txt.configure(yscrollcommand=scroll.set)
        ttk.Button(frame, text="Close", command=win.destroy).pack(
            anchor="e", pady=(8, 0)
        )

    def _pick_folder(self) -> None:
        initial = self.out_var.get() or str(Path.home())
        chosen = filedialog.askdirectory(
            initialdir=initial,
            title="Choose a folder to save the comments export into",
            mustexist=False,
        )
        if chosen:
            self.out_var.set(chosen)

    def _append_log(self, msg: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", msg.rstrip("\n") + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _on_run(self) -> None:
        url = self.url_var.get().strip()
        out_dir = self.out_var.get().strip()
        if not url:
            messagebox.showerror(
                "Missing input", "Please paste your Overleaf project URL."
            )
            return
        if not out_dir:
            messagebox.showerror(
                "Missing input", "Please choose an output folder."
            )
            return

        reviewer_text = self.reviewer_filter_var.get().strip()
        reviewer_filter = [r.strip() for r in reviewer_text.split(",") if r.strip()]

        cookie_value = self.cookie_var.get().strip() or None
        if self.browser_var.get() == "manual" and not cookie_value:
            messagebox.showerror(
                "Missing cookie",
                "Paste your Overleaf session cookie, or pick a browser to read "
                "it from automatically. Click \"How?\" for step-by-step help.",
            )
            return

        _save_config(
            {
                "browser": self.browser_var.get(),
                # Only persisted if the user explicitly opts in.
                "cookie_value": cookie_value if self.remember_cookie_var.get() else "",
                "remember_cookie": bool(self.remember_cookie_var.get()),
                "show_advanced_browsers": bool(self.show_advanced_var.get()),
                "show_options": bool(self.show_options_var.get()),
                "project_url": url,
                "project_title": self.title_var.get().strip(),
                "out_dir": out_dir,
                "include_open": bool(self.include_open_var.get()),
                "include_resolved": bool(self.include_resolved_var.get()),
                "include_changes": bool(self.include_changes_var.get()),
                "reviewer_filter": reviewer_text,
                "render_mode": self.render_mode_var.get(),
                "write_jsonl": bool(self.write_jsonl_var.get()),
                "per_reviewer_reports": bool(self.per_reviewer_var.get()),
                "response_letter": bool(self.response_letter_var.get()),
                "include_raw": bool(self.include_raw_var.get()),
            }
        )

        self.run_btn.configure(state="disabled")
        self.open_md_btn.configure(state="disabled")
        self.open_folder_btn.configure(state="disabled")
        self.progress.start(10)
        self._append_log("─" * 60)
        self._append_log("Starting export…")

        params = dict(
            project_url=url,
            out_dir=Path(out_dir).expanduser(),
            project_title=self.title_var.get().strip() or None,
            browser=self.browser_var.get(),
            cookie_value=cookie_value,
            include_open=bool(self.include_open_var.get()),
            include_resolved=bool(self.include_resolved_var.get()),
            include_changes=bool(self.include_changes_var.get()),
            reviewer_filter=reviewer_filter,
            render_mode=self.render_mode_var.get(),
            write_jsonl=bool(self.write_jsonl_var.get()),
            per_reviewer_reports=bool(self.per_reviewer_var.get()),
            response_letter=bool(self.response_letter_var.get()),
            include_raw=bool(self.include_raw_var.get()),
        )
        self.worker = threading.Thread(
            target=self._worker, args=(params,), daemon=True
        )
        self.worker.start()

    def _worker(self, params: dict) -> None:
        def progress(msg: str) -> None:
            self.queue.put(("log", msg))

        try:
            result = run_export(progress=progress, **params)
            self.queue.put(("done", result))
        except Exception as e:
            self.queue.put(("error", (e, traceback.format_exc())))

    def _pump_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "done":
                    self._on_done(payload)  # type: ignore[arg-type]
                elif kind == "error":
                    err, tb = payload  # type: ignore[misc]
                    self._on_error(err, tb)
        except queue.Empty:
            pass
        self.root.after(80, self._pump_queue)

    def _on_done(self, result: ExportResult) -> None:
        self.last_result = result
        self.progress.stop()
        self.run_btn.configure(state="normal")
        self.open_md_btn.configure(state="normal")
        self.open_folder_btn.configure(state="normal")
        summary = (
            f"\nDone. {result.thread_count} thread(s) — "
            f"{result.open_count} open, {result.resolved_count} resolved. "
            f"{result.tracked_change_count} tracked change(s). "
            f"{result.stale_anchor_count} stale anchor(s)."
        )
        self._append_log(summary)
        self._append_log(f"Markdown: {result.markdown_path}")
        if result.jsonl_path is not None:
            self._append_log(f"JSONL:    {result.jsonl_path}")
        if result.agents_path is not None:
            self._append_log(f"Agents:   {result.agents_path}")
        if result.response_letter_path is not None:
            self._append_log(f"Letter:   {result.response_letter_path}")
        if result.by_reviewer_dir is not None:
            self._append_log(f"Per-reviewer: {result.by_reviewer_dir}")

    def _on_error(self, err: BaseException, tb: str) -> None:
        self.progress.stop()
        self.run_btn.configure(state="normal")
        if isinstance(err, UserFacingError):
            # Expected, explainable failure — show the plain-English message
            # only. The traceback would just frighten a non-technical user.
            self._append_log(str(err))
            messagebox.showwarning("Export could not finish", str(err))
            return
        self._append_log(f"ERROR: {err}")
        self._append_log(tb)
        messagebox.showerror(
            "Export failed",
            f"{type(err).__name__}: {err}\n\n"
            "This looks like a bug. The full details are in the log box, and in "
            "the log file next to your export. You can report it at\n"
            "https://github.com/Mangluu/overleaf-comments-export/issues",
        )

    def _open_markdown(self) -> None:
        if not self.last_result:
            return
        _open_path(self.last_result.markdown_path)

    def _open_folder(self) -> None:
        if not self.last_result:
            return
        _open_path(self.last_result.markdown_path.parent)


def _open_path(p: Path) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(p)])
    elif sys.platform.startswith("win"):
        import os
        os.startfile(str(p))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(p)])


def launch_gui() -> int:
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(launch_gui())
