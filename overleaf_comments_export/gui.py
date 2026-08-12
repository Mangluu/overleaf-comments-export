"""The window.

Written for people who do not use a terminal: numbered steps, plain language,
every option visible rather than hidden behind a toggle, and the technical log
folded away until it is needed.
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

from .client import UserFacingError, parse_project_id
from .export import ExportResult, run_export


PALETTES = {
    "light": {
        "bg": "#ffffff", "fg": "#1a1a1a", "hint": "#666666",
        "field_bg": "#ffffff", "ok": "#1a7f4b", "bad": "#b3261e",
        "tip_bg": "#ffffe0", "tip_fg": "#222222",
    },
    "dark": {
        "bg": "#1c1c1c", "fg": "#e6e6e6", "hint": "#a0a0a0",
        "field_bg": "#2b2b2b", "ok": "#5ddb9a", "bad": "#ff8a80",
        "tip_bg": "#3a3a2a", "tip_fg": "#f0f0e0",
    },
}


def detect_system_theme() -> str:
    """"dark" or "light", following whatever this computer is set to."""
    try:
        if sys.platform == "darwin":
            out = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True, timeout=3,
            )
            # The key only exists in dark mode; reading it fails in light mode.
            return "dark" if "dark" in out.stdout.strip().lower() else "light"
        if sys.platform.startswith("win"):
            import winreg  # type: ignore
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            light, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if light else "dark"
        out = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True, text=True, timeout=3,
        )
        return "dark" if "dark" in out.stdout.lower() else "light"
    except Exception:
        return "light"


def _config_path() -> Path:
    """Per-user config location, cross-platform."""
    try:
        from platformdirs import user_config_dir  # type: ignore
        d = Path(user_config_dir("overleaf-comments-export", "overleaf-comments-export"))
        d.mkdir(parents=True, exist_ok=True)
        return d / "config.json"
    except ImportError:
        return Path.home() / ".overleaf_comments_export.json"


CONFIG_PATH = _config_path()

BROWSER_LABELS = {
    "safari": "Safari",
    "firefox": "Firefox",
    "manual": "I will paste it myself",
    "auto": "Work it out for me",
    "chrome": "Google Chrome",
    "chromium": "Chromium",
    "edge": "Microsoft Edge",
    "brave": "Brave",
}

BROWSER_NOTES = {
    "safari": "Reads Safari's cookie file. No password needed.",
    "firefox": "Reads Firefox's cookie file. No password needed.",
    "manual": "Works on every computer and browser. Press How? for the steps.",
    "auto": "Looks through the browsers installed on this computer.",
    "chrome": "Asks for your computer's login password every time. On Windows "
              "this cannot work at all, so paste the cookie instead.",
    "chromium": "Asks for your computer's login password every time.",
    "edge": "Asks for your computer's login password every time.",
    "brave": "Asks for your computer's login password every time.",
}

PRIVACY_FRIENDLY = ("safari", "firefox", "manual")
ADVANCED_BROWSERS = ("auto", "chrome", "chromium", "edge", "brave")

COOKIE_HELP_TEXT = """\
How to copy your Overleaf session cookie
────────────────────────────────────────
You only need this when the app cannot read the cookie from your browser by
itself. That is common with Chrome on Windows, and with browsers installed from
the Snap store on Linux.

1. Open your paper in Overleaf, in any browser, and make sure you are signed in.

2. Open the developer tools:
   • Windows and Linux : press F12
   • Mac               : press Command + Option + I

3. Find the cookie list:
   • Chrome, Edge, Brave : the "Application" tab, then "Cookies" in the left
     sidebar, then your Overleaf address
   • Firefox             : the "Storage" tab, then "Cookies"
   • Safari              : the "Storage" tab, then "Cookies". Safari needs the
     developer menu turned on first, under Settings, then Advanced.

4. Find the row named  overleaf_session2
   On a self-hosted Overleaf it is called  overleaf.sid  instead.

5. Double-click its Value and copy the whole thing. It is long, and usually
   starts with  s%3A

6. Paste it into the box in this window.

Two things worth knowing
────────────────────────
• The cookie is like a temporary key to your account. Do not share it with
  anyone. It stops working when you sign out of Overleaf.
• This app keeps it in memory only, unless you tick "Remember it on this
  computer".
"""

PRIVACY_INFO_TEXT = """\
What this app reads
───────────────────
Only your Overleaf session, which is the thing your browser already uses to
keep you signed in. Without it, Overleaf will not hand over your comments.

Where it is read from depends on what you choose:
• I will paste it myself → nothing on this computer is read at all. You supply
  it directly. The most private option, and it works everywhere.
• Safari or Firefox → their cookie files. No password needed.
• Chrome, Edge, Brave → their cookies are encrypted and the key lives in your
  system keychain, so your login password is requested every time.

The session is used only to talk to your Overleaf server. Nothing is sent
anywhere else. There is no tracking of any kind in this app.

What gets written to this computer
──────────────────────────────────
• Your answers on this form, so it fills itself in next time. The file is named
  at the bottom of this window and you can delete it whenever you like.
• The export itself, only in the folder you choose.
• A log file, to help work out what went wrong if something does.

About the cookie
────────────────
• Normally kept in memory, and forgotten when this window closes.
• Written to the settings file only if you tick "Remember it on this computer".
  That file is not encrypted, so leave it unticked on a shared machine.
• Your Overleaf password is never asked for, and never stored.
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


class Tooltip:
    """A plain explanation on hover, for the words that are unavoidably jargon.

    Also shows on keyboard focus, so it is not mouse-only.
    """

    def __init__(self, widget: tk.Widget, text: str, app: "App | None" = None) -> None:
        self.widget = widget
        self.text = text
        self.app = app
        self.tip: tk.Toplevel | None = None
        for event, handler in (
            ("<Enter>", self._show), ("<FocusIn>", self._show),
            ("<Leave>", self._hide), ("<FocusOut>", self._hide),
            ("<Destroy>", self._hide),
        ):
            widget.bind(event, handler, add="+")

    def _show(self, _event=None) -> None:
        if self.tip or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 18
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        except tk.TclError:
            return
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        palette = self.app.palette if self.app else PALETTES["light"]
        tk.Label(
            self.tip, text=self.text, justify="left", wraplength=330,
            background=palette["tip_bg"], foreground=palette["tip_fg"],
            relief="solid", borderwidth=1, padx=8, pady=5,
        ).pack()

    def _hide(self, _event=None) -> None:
        if self.tip is not None:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = None


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Overleaf Comments Export")
        root.geometry("780x900")
        root.minsize(640, 600)

        self.config = _load_config()
        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.last_result: ExportResult | None = None
        self.theme_choice = tk.StringVar(value=self.config.get("theme", "system"))

        self._apply_theme()
        self._build()

        root.bind("<Return>", self._on_return)
        root.bind("<KP_Enter>", self._on_return)
        self.url_entry.focus_set()
        self._validate_url()
        self.root.after(80, self._pump_queue)

    # ---------------- appearance ----------------

    def _apply_theme(self) -> None:
        """Set the look. 'system' follows whatever this computer is set to."""
        choice = self.theme_choice.get() if hasattr(self, "theme_choice") else \
            self.config.get("theme", "system")
        mode = detect_system_theme() if choice == "system" else choice
        self.theme_mode = mode
        self.palette = PALETTES[mode]

        try:
            import sv_ttk  # type: ignore
            sv_ttk.set_theme(mode)
        except Exception:
            try:
                style = ttk.Style()
                for preferred in ("aqua", "vista", "clam"):
                    if preferred in style.theme_names():
                        style.theme_use(preferred)
                        break
            except Exception:
                pass

        if not hasattr(self, "font_title"):
            base = tkfont.nametofont("TkDefaultFont")
            size = base.cget("size") or 12
            self.font_title = base.copy()
            self.font_title.configure(size=size + 4, weight="bold")
            self.font_small = base.copy()
            self.font_small.configure(size=max(9, abs(size) - 1))
            self.font_status = base.copy()
            self.font_status.configure(size=size + 1)

        # Hint text is one shared style, so a theme change repaints all of it
        # at once instead of chasing every label.
        style = ttk.Style()
        style.configure("Hint.TLabel", foreground=self.palette["hint"])
        style.configure("Ok.TLabel", foreground=self.palette["ok"])
        style.configure("Bad.TLabel", foreground=self.palette["bad"])

        # Classic tk widgets are not themed by ttk, so they need doing by hand.
        for widget, opts in (
            (getattr(self, "canvas", None),
             {"background": self.palette["bg"]}),
            (getattr(self, "log", None),
             {"background": self.palette["field_bg"],
              "foreground": self.palette["fg"],
              "insertbackground": self.palette["fg"]}),
        ):
            if widget is not None:
                try:
                    widget.configure(**opts)
                except tk.TclError:
                    pass
        if hasattr(self, "root"):
            try:
                self.root.configure(background=self.palette["bg"])
            except tk.TclError:
                pass

    def _on_theme_pick(self, _event=None) -> None:
        self.theme_choice.set(
            {"Match my computer": "system", "Light": "light", "Dark": "dark"}
            .get(self.theme_box.get(), "system"))
        self._on_theme_change()

    def _on_theme_change(self) -> None:
        self._apply_theme()
        # Repaint the bits that carry a colour of their own.
        if hasattr(self, "url_status"):
            self._validate_url()

    def _hint(self, parent, text, row, col=1, span=2):
        lbl = ttk.Label(parent, text=text, style="Hint.TLabel", font=self.font_small,
                        wraplength=540, justify="left")
        lbl.grid(row=row, column=col, columnspan=span, sticky="w", pady=(0, 6))
        return lbl

    # ---------------- layout ----------------

    def _build(self) -> None:
        # A scrollable body, so the window still works on a small screen.
        container = ttk.Frame(self.root)
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container, highlightthickness=0,
                           background=self.palette["bg"])
        self.canvas = canvas
        scroll = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        outer = ttk.Frame(canvas, padding=16)
        outer.bind("<Configure>",
                   lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        window = canvas.create_window((0, 0), window=outer, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        canvas.bind_all(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1 * (e.delta / 3)), "units"),
        )
        outer.columnconfigure(0, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Overleaf Comments Export",
                  font=self.font_title).grid(row=0, column=0, sticky="w")

        appearance = ttk.Frame(header)
        appearance.grid(row=0, column=1, sticky="e")
        ttk.Label(appearance, text="Appearance:", style="Hint.TLabel",
                  font=self.font_small).pack(side="left", padx=(0, 6))
        self.theme_box = ttk.Combobox(
            appearance, state="readonly", width=13,
            values=["Match my computer", "Light", "Dark"])
        self.theme_box.set({"system": "Match my computer", "light": "Light",
                            "dark": "Dark"}[self.theme_choice.get()])
        self.theme_box.pack(side="left")
        self.theme_box.bind("<<ComboboxSelected>>", self._on_theme_pick)
        ttk.Label(
            outer,
            text="Pulls the review comments out of your paper and writes them "
                 "somewhere you can read them. Everything stays on this "
                 "computer.",
            style="Hint.TLabel", font=self.font_small, wraplength=680,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(2, 14))

        body = ttk.Frame(outer)
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)

        self._build_step_paper(body)
        self._build_step_signin(body)
        self._build_step_save(body)
        self._build_include(body)
        self._build_actions(body)
        self._build_status(body)
        self._build_details(body)

    def _step_box(self, parent, number, title):
        box = ttk.LabelFrame(parent, text=f" {number}. {title} ", padding=12)
        box.pack(fill="x", pady=(0, 12))
        box.columnconfigure(1, weight=1)
        return box

    # ---- 1. the paper ----

    def _build_step_paper(self, parent) -> None:
        box = self._step_box(parent, 1, "Which paper")

        ttk.Label(box, text="Link to your paper:").grid(row=0, column=0, sticky="w", pady=4)
        self.url_var = tk.StringVar(value=self.config.get("project_url", ""))
        self.url_var.trace_add("write", lambda *_: self._validate_url())
        self.url_entry = ttk.Entry(box, textvariable=self.url_var)
        self.url_entry.grid(row=0, column=1, columnspan=2, sticky="ew", pady=4)
        self.url_status = ttk.Label(box, text="", font=self.font_small,
                                    style="Hint.TLabel")
        self.url_status.grid(row=1, column=1, columnspan=2, sticky="w")
        self._hint(box, "Open the paper in Overleaf and copy the address from "
                        "the top of your browser.", row=2)

        ttk.Label(box, text="Title (optional):").grid(row=3, column=0, sticky="w", pady=4)
        self.title_var = tk.StringVar(value=self.config.get("project_title", ""))
        ttk.Entry(box, textvariable=self.title_var).grid(
            row=3, column=1, columnspan=2, sticky="ew", pady=4)
        self._hint(box, "Only used as the heading of the exported file.", row=4)

        self.self_hosted_var = tk.BooleanVar(
            value=bool(self.config.get("self_hosted", False)))
        cb = ttk.Checkbutton(
            box, text="My university runs its own Overleaf",
            variable=self.self_hosted_var, command=self._toggle_self_hosted)
        cb.grid(row=5, column=0, columnspan=3, sticky="w", pady=(6, 0))
        Tooltip(cb, "Tick this if you do not use overleaf.com, for example an "
                    "Overleaf your department installed itself.", self)

        self.base_label = ttk.Label(box, text="Its address:")
        self.base_var = tk.StringVar(
            value=self.config.get("base_url", "https://www.overleaf.com"))
        self.base_entry = ttk.Entry(box, textvariable=self.base_var)
        self.base_note = ttk.Label(
            box, text="For example  https://overleaf.my-university.edu  — comments "
                     "work, but tracked changes need Overleaf Server Pro.",
            style="Hint.TLabel", font=self.font_small, wraplength=520, justify="left")
        self.base_label.grid(row=6, column=0, sticky="w", pady=4)
        self.base_entry.grid(row=6, column=1, columnspan=2, sticky="ew", pady=4)
        self.base_note.grid(row=7, column=1, columnspan=2, sticky="w")
        self._toggle_self_hosted()

    def _toggle_self_hosted(self) -> None:
        show = self.self_hosted_var.get()
        for w in (self.base_label, self.base_entry, self.base_note):
            w.grid() if show else w.grid_remove()
        if not show:
            self.base_var.set("https://www.overleaf.com")

    def _validate_url(self) -> None:
        raw = self.url_var.get().strip()
        if not raw:
            self.url_status.configure(text="")
            return
        try:
            parse_project_id(raw)
        except ValueError:
            self.url_status.configure(
                text="This does not look like a project link yet. It should "
                     "contain /project/ followed by a long code.",
                style="Bad.TLabel")
        else:
            self.url_status.configure(text="Looks right.", style="Ok.TLabel")

    # ---- 2. signing in ----

    def _build_step_signin(self, parent) -> None:
        box = self._step_box(parent, 2, "Let it see your Overleaf")

        ttk.Label(box, text="Sign in using:").grid(row=0, column=0, sticky="w", pady=4)
        default_browser = self.config.get("browser", "safari")
        if default_browser not in BROWSER_LABELS:
            default_browser = "safari"
        self.browser_var = tk.StringVar(value=default_browser)
        self.browser_box = ttk.Combobox(box, state="readonly", width=26)
        self.browser_box.grid(row=0, column=1, sticky="w", pady=4)
        self.browser_box.bind("<<ComboboxSelected>>", lambda _e: self._on_browser_change())
        ttk.Button(box, text="What is this?", command=self._show_privacy_info).grid(
            row=0, column=2, sticky="w", padx=8)

        self.browser_note = ttk.Label(box, text="", style="Hint.TLabel",
                                      font=self.font_small, wraplength=540,
                                      justify="left")
        self.browser_note.grid(row=1, column=1, columnspan=2, sticky="w", pady=(0, 6))

        self.show_advanced_var = tk.BooleanVar(
            value=bool(self.config.get("show_advanced_browsers", False))
            or default_browser in ADVANCED_BROWSERS)
        ttk.Checkbutton(
            box, text="Show the browsers that need a password",
            variable=self.show_advanced_var, command=self._refresh_browser_choices,
        ).grid(row=2, column=1, columnspan=2, sticky="w")

        self.cookie_label = ttk.Label(box, text="Paste it here:")
        self.cookie_frame = ttk.Frame(box)
        self.cookie_frame.columnconfigure(0, weight=1)
        self.cookie_var = tk.StringVar(value=self.config.get("cookie_value", ""))
        self.cookie_entry = ttk.Entry(self.cookie_frame, textvariable=self.cookie_var,
                                      show="•")
        self.cookie_entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(self.cookie_frame, text="How?", width=7,
                   command=self._show_cookie_help).grid(row=0, column=1, padx=(6, 0))
        self.remember_cookie_var = tk.BooleanVar(
            value=bool(self.config.get("remember_cookie", False)))
        self.cookie_remember = ttk.Checkbutton(
            box, text="Remember it on this computer (not encrypted)",
            variable=self.remember_cookie_var)

        self.cookie_label.grid(row=3, column=0, sticky="w", pady=4)
        self.cookie_frame.grid(row=3, column=1, columnspan=2, sticky="ew", pady=4)
        self.cookie_remember.grid(row=4, column=1, columnspan=2, sticky="w")

        self.browser_box.configure(textvariable=self.browser_var)
        self._refresh_browser_choices()

    def _refresh_browser_choices(self) -> None:
        keys = list(BROWSER_LABELS) if self.show_advanced_var.get() else list(PRIVACY_FRIENDLY)
        self.browser_box.configure(values=[BROWSER_LABELS[k] for k in keys])
        self._browser_keys = keys
        current = self.browser_var.get()
        key = current if current in BROWSER_LABELS else "safari"
        if key not in keys:
            key = keys[0]
        self.browser_var.set(key)
        self.browser_box.set(BROWSER_LABELS[key])
        self._on_browser_change()

    def _on_browser_change(self) -> None:
        shown = self.browser_box.get()
        for k, label in BROWSER_LABELS.items():
            if label == shown:
                self.browser_var.set(k)
                break
        key = self.browser_var.get()
        self.browser_note.configure(text=BROWSER_NOTES.get(key, ""))
        manual = key == "manual"
        for w in (self.cookie_label, self.cookie_frame, self.cookie_remember):
            w.grid() if manual else w.grid_remove()

    # ---- 3. where to put it ----

    def _build_step_save(self, parent) -> None:
        box = self._step_box(parent, 3, "Where to save it")
        ttk.Label(box, text="Folder:").grid(row=0, column=0, sticky="w", pady=4)
        self.out_var = tk.StringVar(value=self.config.get("out_dir", ""))
        ttk.Entry(box, textvariable=self.out_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(box, text="Choose…", command=self._pick_folder).grid(
            row=0, column=2, sticky="w", padx=8)
        self._hint(box, "A new folder of its own is easiest, for example a "
                        "folder called Comments next to your paper.", row=1)

    # ---- what to include ----

    def _build_include(self, parent) -> None:
        box = ttk.LabelFrame(parent, text="  What to include  ", padding=12)
        box.pack(fill="x", pady=(0, 12))
        for i in (0, 1):
            box.columnconfigure(i, weight=1)

        cfg = self.config
        self.include_open_var = tk.BooleanVar(value=bool(cfg.get("include_open", True)))
        self.include_resolved_var = tk.BooleanVar(value=bool(cfg.get("include_resolved", True)))
        self.include_changes_var = tk.BooleanVar(value=bool(cfg.get("include_changes", True)))
        self.response_letter_var = tk.BooleanVar(value=bool(cfg.get("response_letter", False)))
        self.per_reviewer_var = tk.BooleanVar(value=bool(cfg.get("per_reviewer_reports", False)))
        self.annotated_var = tk.BooleanVar(value=bool(cfg.get("annotated_tex", False)))
        self.stable_var = tk.BooleanVar(value=bool(cfg.get("stable", False)))
        self.detailed_var = tk.BooleanVar(value=cfg.get("render_mode", "compact") == "detailed")
        self.write_jsonl_var = tk.BooleanVar(value=bool(cfg.get("write_jsonl", True)))
        self.include_raw_var = tk.BooleanVar(value=bool(cfg.get("include_raw", False)))

        rows = [
            (self.include_open_var, "Comments still open",
             "Comments nobody has marked as done yet."),
            (self.include_resolved_var, "Comments marked done",
             "Threads someone already ticked off in Overleaf."),
            (self.include_changes_var, "Tracked changes",
             "Text people inserted or deleted with Track Changes on. Needs "
             "Overleaf Premium, or Server Pro if self-hosted."),
            (self.response_letter_var, "A reply letter to fill in",
             "Writes response-letter.md, a point-by-point document with a "
             "blank space under each comment for your answer."),
            (self.per_reviewer_var, "A separate file per person",
             "One file for each person who commented, so you can work through "
             "them one at a time."),
            (self.annotated_var, "Comments inside the PDF",
             "Writes a copy of your LaTeX with every comment placed where it "
             "was made, into a folder called annotated. Compile that (upload "
             "it to Overleaf, or build it on your computer) and the PDF you "
             "get carries the comments. Your own files are never touched."),
            (self.stable_var, "Keep it tidy for version control",
             "Writes one file that only changes when the comments change, so "
             "it can live in a git repository without noise."),
            (self.detailed_var, "Show more of the surrounding text",
             "More of the sentence around each comment, on several lines."),
            (self.write_jsonl_var, "Also write the data file for other tools",
             "comments.jsonl, one comment per line. Harmless to leave on."),
            (self.include_raw_var, "Include the raw data from Overleaf",
             "Only useful for reporting a problem. Makes the file much bigger."),
        ]
        for i, (var, label, tip) in enumerate(rows):
            cb = ttk.Checkbutton(box, text=label, variable=var)
            cb.grid(row=i // 2, column=i % 2, sticky="w", pady=2, padx=(0, 12))
            Tooltip(cb, tip, self)

        ttk.Label(box, text="Only these people (optional):").grid(
            row=len(rows) // 2 + 1, column=0, sticky="w", pady=(10, 2))
        self.reviewer_filter_var = tk.StringVar(value=self.config.get("reviewer_filter", ""))
        ent = ttk.Entry(box, textvariable=self.reviewer_filter_var)
        ent.grid(row=len(rows) // 2 + 1, column=1, sticky="ew", pady=(10, 2))
        Tooltip(ent, "Type part of a name or email to keep only their comments. "
                     "Separate several with commas. Leave empty for everybody.", self)

    # ---- run ----

    def _build_actions(self, parent) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(4, 8))
        self.run_btn = ttk.Button(row, text="Get my comments", command=self._on_run)
        self.run_btn.pack(side="left")
        try:
            self.run_btn.configure(style="Accent.TButton")
        except tk.TclError:
            pass
        self.open_md_btn = ttk.Button(row, text="Open the comments",
                                      command=self._open_markdown, state="disabled")
        self.open_md_btn.pack(side="left", padx=8)
        self.open_folder_btn = ttk.Button(row, text="Open the folder",
                                          command=self._open_folder, state="disabled")
        self.open_folder_btn.pack(side="left")

    def _build_status(self, parent) -> None:
        box = ttk.Frame(parent)
        box.pack(fill="x", pady=(0, 8))
        self.progress = ttk.Progressbar(box, mode="indeterminate")
        self.progress.pack(fill="x")
        self.status = ttk.Label(box, text="Fill in the three steps above, then "
                                          "press Get my comments.",
                                font=self.font_status, wraplength=680, justify="left")
        self.status.pack(anchor="w", pady=(6, 0))

    def _build_details(self, parent) -> None:
        self.details_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(parent, text="Show technical details",
                        variable=self.details_var,
                        command=self._toggle_details).pack(anchor="w")
        self.details = ttk.Frame(parent)
        self.details.columnconfigure(0, weight=1)
        self.log = tk.Text(self.details, height=12, wrap="word", state="disabled",
                           font=self.font_small,
                           background=self.palette["field_bg"],
                           foreground=self.palette["fg"],
                           insertbackground=self.palette["fg"])
        self.log.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(self.details, command=self.log.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=sb.set)
        ttk.Label(self.details, text=f"Settings file: {CONFIG_PATH}",
                  style="Hint.TLabel", font=self.font_small).grid(
            row=1, column=0, sticky="w", pady=(4, 0))
        self.details.pack(fill="both", expand=True, pady=(4, 0))
        self.details.pack_forget()

    def _toggle_details(self) -> None:
        if self.details_var.get():
            self.details.pack(fill="both", expand=True, pady=(4, 0))
        else:
            self.details.pack_forget()

    # ---------------- dialogs ----------------

    def _text_window(self, title: str, body: str, extra: str = "") -> None:
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("660x580")
        win.transient(self.root)
        frame = ttk.Frame(win, padding=12)
        frame.pack(fill="both", expand=True)
        txt = tk.Text(frame, wrap="word",
                      background=self.palette["field_bg"],
                      foreground=self.palette["fg"],
                      insertbackground=self.palette["fg"])
        txt.insert("1.0", body + extra)
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(frame, command=txt.yview)
        sb.pack(side="right", fill="y")
        txt.configure(yscrollcommand=sb.set)
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=8)
        win.bind("<Escape>", lambda _e: win.destroy())

    def _show_cookie_help(self) -> None:
        self._text_window("How to copy your cookie", COOKIE_HELP_TEXT)

    def _show_privacy_info(self) -> None:
        self._text_window("What this app touches", PRIVACY_INFO_TEXT,
                          f"\nSettings file on this computer:\n{CONFIG_PATH}\n")

    def _pick_folder(self) -> None:
        chosen = filedialog.askdirectory(
            initialdir=self.out_var.get() or str(Path.home()),
            title="Choose a folder to save the comments into", mustexist=False)
        if chosen:
            self.out_var.set(chosen)

    # ---------------- running ----------------

    def _append_log(self, msg: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", msg.rstrip("\n") + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_status(self, text: str, kind: str = "") -> None:
        style = {"ok": "Ok.TLabel", "bad": "Bad.TLabel"}.get(kind, "TLabel")
        self.status.configure(text=text, style=style)

    def _on_return(self, _event=None):
        if str(self.run_btn["state"]) != "disabled":
            self._on_run()

    def _on_run(self) -> None:
        url = self.url_var.get().strip()
        out_dir = self.out_var.get().strip()
        if not url:
            messagebox.showwarning("Nearly there",
                                   "Paste the link to your Overleaf paper in step 1.")
            self.url_entry.focus_set()
            return
        try:
            parse_project_id(url)
        except ValueError:
            messagebox.showwarning(
                "That link does not look right",
                "The link should contain /project/ followed by a long code.\n\n"
                "Open your paper in Overleaf and copy the whole address from "
                "the top of the browser.")
            self.url_entry.focus_set()
            return
        if not out_dir:
            messagebox.showwarning("Nearly there",
                                   "Choose a folder to save into, in step 3.")
            return

        cookie_value = self.cookie_var.get().strip() or None
        if self.browser_var.get() == "manual" and not cookie_value:
            messagebox.showwarning(
                "The cookie is missing",
                "Paste your Overleaf cookie in step 2, or choose a browser to "
                "read it from.\n\nPress How? next to the box for the steps.")
            self.cookie_entry.focus_set()
            return

        reviewer_text = self.reviewer_filter_var.get().strip()
        _save_config({
            "theme": self.theme_choice.get(),
            "browser": self.browser_var.get(),
            "show_advanced_browsers": bool(self.show_advanced_var.get()),
            "cookie_value": cookie_value if self.remember_cookie_var.get() else "",
            "remember_cookie": bool(self.remember_cookie_var.get()),
            "project_url": url,
            "project_title": self.title_var.get().strip(),
            "out_dir": out_dir,
            "self_hosted": bool(self.self_hosted_var.get()),
            "base_url": self.base_var.get().strip(),
            "include_open": bool(self.include_open_var.get()),
            "include_resolved": bool(self.include_resolved_var.get()),
            "include_changes": bool(self.include_changes_var.get()),
            "reviewer_filter": reviewer_text,
            "render_mode": "detailed" if self.detailed_var.get() else "compact",
            "write_jsonl": bool(self.write_jsonl_var.get()),
            "per_reviewer_reports": bool(self.per_reviewer_var.get()),
            "response_letter": bool(self.response_letter_var.get()),
            "annotated_tex": bool(self.annotated_var.get()),
            "stable": bool(self.stable_var.get()),
            "include_raw": bool(self.include_raw_var.get()),
        })

        self.run_btn.configure(state="disabled")
        self.open_md_btn.configure(state="disabled")
        self.open_folder_btn.configure(state="disabled")
        self.progress.start(12)
        self._set_status("Working… this usually takes a few seconds.")
        self._append_log("-" * 60)

        base = self.base_var.get().strip() if self.self_hosted_var.get() else "https://www.overleaf.com"
        params = dict(
            project_url=url,
            out_dir=Path(out_dir).expanduser(),
            project_title=self.title_var.get().strip() or None,
            base_url=base or "https://www.overleaf.com",
            browser=self.browser_var.get(),
            cookie_value=cookie_value,
            include_open=bool(self.include_open_var.get()),
            include_resolved=bool(self.include_resolved_var.get()),
            include_changes=bool(self.include_changes_var.get()),
            reviewer_filter=[r.strip() for r in reviewer_text.split(",") if r.strip()],
            render_mode="detailed" if self.detailed_var.get() else "compact",
            write_jsonl=bool(self.write_jsonl_var.get()),
            per_reviewer_reports=bool(self.per_reviewer_var.get()),
            response_letter=bool(self.response_letter_var.get()),
            annotated_tex=bool(self.annotated_var.get()),
            stable=bool(self.stable_var.get()),
            include_raw=bool(self.include_raw_var.get()),
        )
        self.worker = threading.Thread(target=self._worker, args=(params,), daemon=True)
        self.worker.start()

    def _worker(self, params: dict) -> None:
        def progress(msg: str) -> None:
            self.queue.put(("log", msg))
        try:
            self.queue.put(("done", run_export(progress=progress, **params)))
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

        bits = [f"{result.thread_count} comment thread(s)"]
        if result.open_count:
            bits.append(f"{result.open_count} still open")
        if result.tracked_change_count:
            bits.append(f"{result.tracked_change_count} tracked change(s)")
        self._set_status("Done. Found " + ", ".join(bits) + ".", "ok")

        self._append_log(f"Comments: {result.markdown_path}")
        for label, path in (
            ("Data", result.json_path), ("Lines", result.jsonl_path),
            ("Letter", result.response_letter_path),
            ("Annotated", result.annotated_dir),
            ("Per person", result.by_reviewer_dir), ("Notes for AI", result.agents_path),
        ):
            if path is not None:
                self._append_log(f"{label}: {path}")
        if result.annotated_dir is not None:
            self._append_log(
                "To get a PDF with the comments in it: upload the annotated "
                "folder to Overleaf and compile it there, or compile it on "
                "this computer if you have LaTeX installed.")
        if result.stale_anchor_count:
            self._append_log(
                f"{result.stale_anchor_count} comment(s) point at text that has "
                "changed since they were written.")

    def _on_error(self, err: BaseException, tb: str) -> None:
        self.progress.stop()
        self.run_btn.configure(state="normal")
        if isinstance(err, UserFacingError):
            self._set_status("That did not work. See the message.", "bad")
            self._append_log(str(err))
            messagebox.showwarning("It could not finish", str(err))
            return
        self._set_status("Something unexpected went wrong.", "bad")
        self._append_log(f"ERROR: {err}")
        self._append_log(tb)
        self.details_var.set(True)
        self._toggle_details()
        messagebox.showerror(
            "Something went wrong",
            f"{type(err).__name__}: {err}\n\n"
            "This looks like a bug rather than something you did. The details "
            "are in the technical details box, and in the log file next to your "
            "export.\n\nYou can report it at\n"
            "github.com/Mangluu/overleaf-comments-export/issues")

    def _open_markdown(self) -> None:
        if self.last_result:
            _open_path(self.last_result.markdown_path)

    def _open_folder(self) -> None:
        if self.last_result:
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
