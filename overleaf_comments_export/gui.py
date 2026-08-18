"""The window.

Written for people who do not use a terminal: numbered steps, plain language,
every option visible rather than hidden behind a toggle, and the technical log
folded away until it is needed.
"""

from __future__ import annotations

import json
import logging
import queue
import subprocess
import sys
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

from .client import UserFacingError, parse_project_id
from .export import ExportCancelled, ExportResult, run_export

logger = logging.getLogger(__name__)


# Paper and ink. This is a tool for people working on a manuscript, so the
# light theme is the warm off-white of printed paper rather than screen white,
# and the text is the warm near-black of ink rather than pure black. The accent
# is a muted scholarly green, close to Overleaf's own but calmer, because it
# appears beside a lot of text and a saturated green would shout.
PALETTES = {
    "light": {
        "bg": "#F7F5F0",          # the page
        "surface": "#FFFFFF",     # cards sitting on it
        "fg": "#1C1B18",          # ink
        "hint": "#6E6A61",        # pencil
        "rule": "#E3DFD5",        # hairline
        "field_bg": "#FFFFFF",
        "accent": "#2E7D4F", "accent_fg": "#FFFFFF", "accent_soft": "#E8F1EA",
        "ok": "#2E7D4F", "bad": "#A8352A", "warn": "#8A6A1F",
        "tip_bg": "#FFFDF4", "tip_fg": "#2A2822",
    },
    "dark": {
        "bg": "#141311",          # warm dark, not blue-black
        "surface": "#232019",
        "fg": "#EDE9E0",
        "hint": "#9C968B",
        "rule": "#332F2A",
        "field_bg": "#2A2622",
        "accent": "#5FB98A", "accent_fg": "#10241A", "accent_soft": "#243128",
        "ok": "#5FB98A", "bad": "#E08C81", "warn": "#D2AC5E",
        "tip_bg": "#2C2822", "tip_fg": "#EDE9E0",
    },
}

# A serif for the name, because this is a tool for people writing papers and a
# serif says that before any of the words do. Each platform's best is tried in
# turn, and Tk falls back on its own if none are installed.
_SERIF_STACK = ("New York", "Iowan Old Style", "Palatino", "Georgia",
                "Charter", "Times New Roman", "serif")
_MONO_STACK = ("SF Mono", "Menlo", "Cascadia Mono", "Consolas",
               "DejaVu Sans Mono", "monospace")


def _first_installed(root, families: tuple[str, ...]) -> str:
    available = {f.lower() for f in tkfont.families(root)}
    for name in families:
        if name.lower() in available:
            return name
    return families[-1]


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
    "safari": "Reads Safari's cookies. No password needed.",
    "firefox": "Reads Firefox's cookies. No password needed.",
    "manual": "Works everywhere. Press How? for the steps.",
    "auto": "Tries the browsers on this computer.",
    "chrome": "Asks for your login password. On Windows, paste instead.",
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
            # Named encoding: on Windows the default is cp1252, and a project
            # title or path with any non-Latin character in it would make
            # the window fail to open at all.
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_config(data: dict) -> str | None:
    """Save the settings. Returns why it could not, or None when it did.

    Never raises. A settings file that cannot be written must not stop an
    export, since the export does not need it. But it used to fail in total
    silence, so everything you typed came back empty next time with nothing
    said and nothing logged. A full disk, a read-only home directory, or a
    config file owned by another account all land here.
    """
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        # This file holds an Overleaf session cookie when "remember" is ticked,
        # and it was being written world-readable. Owner only, and the folder
        # too, so nobody else with an account on the machine can read it. Not
        # supported on Windows, where the call is a no-op.
        _owner_only(CONFIG_PATH, 0o600)
        _owner_only(CONFIG_PATH.parent, 0o700)
        return None
    except OSError as e:
        logger.warning("Could not save settings to %s: %s", CONFIG_PATH, e)
        return e.strerror or str(e)
    except Exception as e:                        # json, or something stranger
        logger.warning("Could not save settings: %s", e)
        return str(e)


def _owner_only(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except (OSError, NotImplementedError):
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
        # The version goes in the title bar. Someone who installed with pip
        # and no --upgrade can be running a year-old copy without knowing, and
        # every bug report is easier when the version is on screen.
        from . import __version__
        root.title(f"Overleaf Comments Export {__version__}")
        root.geometry("780x900")
        root.minsize(640, 600)

        self.config = _load_config()
        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        # Set when Stop is pressed. The worker reads it between steps.
        self.cancel_requested = False
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
            self.themed = True
        except Exception:
            self.themed = False
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
            size = abs(base.cget("size") or 13)
            # A real hierarchy. Everything used to sit within two points of
            # everything else, which is why nothing stood out.
            self.font_title = tkfont.Font(
                family=_first_installed(self.root, _SERIF_STACK),
                size=size + 8, weight="normal")
            self.font_section = base.copy()
            self.font_section.configure(size=size, weight="bold")
            self.font_label = base.copy()
            self.font_small = base.copy()
            self.font_small.configure(size=max(9, size - 2))
            self.font_status = base.copy()
            self.font_status.configure(size=size)
            self.font_mono = tkfont.Font(
                family=_first_installed(self.root, _MONO_STACK), size=max(9, size - 2))

        # Hint text is one shared style, so a theme change repaints all of it
        # at once instead of chasing every label.
        p = self.palette
        style = ttk.Style()
        style.configure("Hint.TLabel", foreground=p["hint"], background=p["surface"])
        style.configure("Ok.TLabel", foreground=p["ok"], background=p["surface"])
        style.configure("Bad.TLabel", foreground=p["bad"], background=p["surface"])
        # Cards are a surface colour and generous padding, with no border.
        # Borders around every group were most of what made this look busy.
        style.configure("Card.TFrame", background=p["surface"])
        style.configure("Page.TFrame", background=p["bg"])
        style.configure("Card.TLabel", background=p["surface"], foreground=p["fg"])
        style.configure("Title.TLabel", background=p["bg"], foreground=p["fg"],
                        font=self.font_title)
        style.configure("Section.TLabel", background=p["surface"], foreground=p["fg"],
                        font=self.font_section)
        style.configure("PageHint.TLabel", background=p["bg"], foreground=p["hint"])
        style.configure("Card.TCheckbutton", background=p["surface"], foreground=p["fg"])
        style.configure("Card.TRadiobutton", background=p["surface"], foreground=p["fg"])
        # The one button that matters gets the accent; everything else stays quiet.
        style.configure("Go.TButton", font=self.font_section)
        try:
            style.configure("Go.TButton", background=p["accent"],
                            foreground=p["accent_fg"])
            style.map("Go.TButton",
                      background=[("active", p["accent"]), ("disabled", p["rule"])],
                      foreground=[("disabled", p["hint"])])
        except tk.TclError:
            pass

        # Classic tk widgets are not themed by ttk, so they need doing by hand.
        for widget, opts in (
            (getattr(self, "log", None) if getattr(self, "log", None) is not None else None,
             {"background": self.palette["field_bg"],
              "foreground": self.palette["fg"],
              "insertbackground": self.palette["fg"],
              "highlightbackground": self.palette["rule"]}),
            (getattr(self, "_rule", None),
             {"background": self.palette["rule"]}),
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

    # The widest field label there is. Every card reserves this many pixels for
    # its first column, so the entries line up down the whole window even
    # though each card has a grid of its own. Measured in the actual font
    # rather than set in characters, because a character width is an average
    # and reserving 19 of them made the window 200 pixels wider than it needed.
    WIDEST_LABEL = "Link to your paper"

    def _label_column(self, card) -> None:
        card.columnconfigure(0, minsize=self.font_label.measure(self.WIDEST_LABEL) + 12)

    def _field_label(self, parent, text: str, row: int, **kw):
        """A label in the left column of a card, aligned with all the others."""
        self._label_column(parent)
        label = ttk.Label(parent, text=text, anchor="w", style="Card.TLabel")
        label.grid(row=row, column=0, sticky="w", pady=4, **kw)
        return label

    def _card(self, parent, title: str | None = None):
        """A section as a card: a surface, generous padding, and no border.

        Every group used to be a ttk.LabelFrame, and a dozen boxed outlines
        stacked down the window was most of what made this look cluttered.
        Space and a heading separate things perfectly well.
        """
        wrap = ttk.Frame(parent, style="Page.TFrame")
        wrap.pack(fill="x", pady=(0, 8))
        card = ttk.Frame(wrap, style="Card.TFrame", padding=13)
        card.pack(fill="x")
        if title:
            ttk.Label(card, text=title, style="Section.TLabel").pack(
                anchor="w", pady=(0, 8))
        # The contents get their own frame, so a caller can use grid or pack
        # as it likes. Tk refuses to have both inside one container, and the
        # heading above is packed.
        body = ttk.Frame(card, style="Card.TFrame")
        body.pack(fill="both", expand=True)
        return body

    def _hint(self, parent, text, row, col=1, span=2):
        lbl = ttk.Label(parent, text=text, style="Hint.TLabel", font=self.font_small,
                        wraplength=380, justify="left")
        lbl.grid(row=row, column=col, columnspan=span, sticky="w", pady=(0, 6))
        return lbl

    # ---------------- layout ----------------

    def _build(self) -> None:
        # No scrolling. Everything that has to be decided is on screen at once,
        # in two columns: what to point it at on the left, what to get out of it
        # on the right. A form you have to scroll through hides half the
        # decisions, and the wheel behaviour was never going to be as good as
        # simply not needing it.
        outer = ttk.Frame(self.root, padding=22, style="Page.TFrame")
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        header = ttk.Frame(outer, style="Page.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Overleaf Comments Export",
                  style="Title.TLabel").grid(row=0, column=0, sticky="w")

        appearance = ttk.Frame(header, style="Page.TFrame")
        appearance.grid(row=0, column=1, sticky="e")
        ttk.Label(appearance, text="Appearance", style="PageHint.TLabel",
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
            style="PageHint.TLabel", font=self.font_small, wraplength=760,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(4, 12))
        self._rule = tk.Frame(outer, height=1, background=self.palette["rule"])
        self._rule.grid(row=1, column=0, sticky="sew")

        body = ttk.Frame(outer, style="Page.TFrame")
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body, style="Page.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right = ttk.Frame(body, style="Page.TFrame")
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        # Left is what to point it at, right is what comes out. The two cards
        # that grow when you tick something are both on the left, so putting
        # the folder on the right keeps the columns level when they do.
        self._build_step_paper(left)
        self._build_step_signin(left)
        self._build_step_save(right)
        self._build_include(right, aside=left)

        self._build_actions(outer, row=3)
        self._build_status(outer, row=4)
        self._build_details(outer, row=5)

        self._fit_window()

    def _step_box(self, parent, number, title):
        box = self._card(parent, title)
        box.pack(fill="x", pady=(0, 12))
        box.columnconfigure(1, weight=1)
        return box

    # ---- 1. the paper ----

    def _build_step_paper(self, parent) -> None:
        box = self._step_box(parent, 1, "Which paper")

        self._field_label(box, "Link to your paper", 0)
        self.url_var = tk.StringVar(value=self.config.get("project_url", ""))
        self.url_var.trace_add("write", lambda *_: self._validate_url())
        self.url_entry = ttk.Entry(box, textvariable=self.url_var, width=44)
        self.url_entry.grid(row=0, column=1, columnspan=2, sticky="ew", pady=4)
        self.url_status = ttk.Label(box, text="", font=self.font_small,
                                    style="Hint.TLabel")
        self.url_status.grid(row=1, column=1, columnspan=2, sticky="w")
        self._hint(box, "Copy it from your browser's address bar.", row=2)

        self._field_label(box, "Title (optional)", 3)
        self.title_var = tk.StringVar(value=self.config.get("project_title", ""))
        ttk.Entry(box, textvariable=self.title_var).grid(
            row=3, column=1, columnspan=2, sticky="ew", pady=4)
        self._hint(box, "Used as the heading of the export.", row=4)

        self.self_hosted_var = tk.BooleanVar(
            value=bool(self.config.get("self_hosted", False)))
        cb = ttk.Checkbutton(
            box, text="My university runs its own Overleaf",
            variable=self.self_hosted_var, command=self._toggle_self_hosted)
        cb.grid(row=5, column=0, columnspan=3, sticky="w", pady=(6, 0))
        Tooltip(cb, "Tick this if you do not use overleaf.com, for example an "
                    "Overleaf your department installed itself.", self)

        self.base_label = ttk.Label(box, text="Its address", anchor="w",
                                    style="Card.TLabel")
        self.base_var = tk.StringVar(
            value=self.config.get("base_url", "https://www.overleaf.com"))
        self.base_entry = ttk.Entry(box, textvariable=self.base_var)
        self.base_note = ttk.Label(
            box, text="For example  https://overleaf.my-university.edu\n"
                 "Tracked changes need Server Pro.",
            style="Hint.TLabel", font=self.font_small, wraplength=380, justify="left")
        self.base_label.grid(row=6, column=0, sticky="w", pady=4)
        self.base_entry.grid(row=6, column=1, columnspan=2, sticky="ew", pady=4)
        self.base_note.grid(row=7, column=1, columnspan=2, sticky="w")

        # Almost nobody needs this. A self-hosted Overleaf names its session
        # cookie after itself, and anything ending in .sid is found without
        # being told, so the box is here only for the servers that do neither.
        self.cookie_name_label = ttk.Label(box, text="Cookie name",
                                           anchor="w", style="Card.TLabel")
        self.cookie_name_var = tk.StringVar(value=self.config.get("cookie_name", ""))
        self.cookie_name_entry = ttk.Entry(box, textvariable=self.cookie_name_var)
        self.cookie_name_note = ttk.Label(
            box, text="Only if the export says it could not find a session.",
            style="Hint.TLabel", font=self.font_small, wraplength=380, justify="left")
        self.cookie_name_label.grid(row=8, column=0, sticky="w", pady=4)
        self.cookie_name_entry.grid(row=8, column=1, columnspan=2, sticky="ew", pady=4)
        self.cookie_name_note.grid(row=9, column=1, columnspan=2, sticky="w")
        Tooltip(self.cookie_name_entry,
                "The name of the cookie your Overleaf keeps your session in. "
                "overleaf.com calls it overleaf_session2. A self-hosted server "
                "usually names it after itself, like ifftex.sid, and those are "
                "found automatically.", self)
        self._toggle_self_hosted()

    def _fit_window(self) -> None:
        """Keep the window at least as big as what is in it.

        Without a scrollbar there is no way to reach anything that falls off
        the bottom, and ticking the self-hosted box or choosing to paste a
        cookie adds rows. Growing the window is the only honest answer: the
        alternative is a card the user cannot see or scroll to.
        """
        self.root.update_idletasks()
        need_w = self.root.winfo_reqwidth()
        need_h = self.root.winfo_reqheight()
        # Never grow past the screen. Opening the technical log wants more room
        # than a laptop has, and a window taller than the display is no more
        # reachable than a card scrolled off the bottom. The log has a
        # scrollbar of its own, so it is the part that gives.
        room_w = self.root.winfo_screenwidth() - 80
        room_h = self.root.winfo_screenheight() - 140
        want_w, want_h = min(need_w, room_w), min(need_h, room_h)
        self.root.minsize(min(need_w, room_w), min(need_h, room_h))
        if self.root.winfo_width() < want_w or self.root.winfo_height() < want_h:
            self.root.geometry(f"{max(self.root.winfo_width(), want_w)}x"
                               f"{max(self.root.winfo_height(), want_h)}")

    def _toggle_self_hosted(self) -> None:
        show = self.self_hosted_var.get()
        for w in (self.base_label, self.base_entry, self.base_note,
                  self.cookie_name_label, self.cookie_name_entry,
                  self.cookie_name_note):
            w.grid() if show else w.grid_remove()
        if not show:
            self.base_var.set("https://www.overleaf.com")
        self._fit_window()

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

        self._field_label(box, "Sign in using", 0)
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

        self.cookie_label = ttk.Label(box, text="Paste it here", anchor="w",
                                      style="Card.TLabel")
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
        self._fit_window()

    # ---- 3. where to put it ----

    def _build_step_save(self, parent) -> None:
        box = self._step_box(parent, 3, "Where to save it")
        self._field_label(box, "Folder", 0)
        self.out_var = tk.StringVar(value=self.config.get("out_dir", ""))
        ttk.Entry(box, textvariable=self.out_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(box, text="Choose…", command=self._pick_folder).grid(
            row=0, column=2, sticky="w", padx=8)
        self._hint(box, "A new folder of its own is easiest.", row=1)

    # ---- what to include ----

    def _build_include(self, parent, aside=None) -> None:
        box = self._card(parent, "What to include")

        cfg = self.config
        self.include_open_var = tk.BooleanVar(value=bool(cfg.get("include_open", True)))
        self.include_resolved_var = tk.BooleanVar(value=bool(cfg.get("include_resolved", True)))
        self.include_changes_var = tk.BooleanVar(value=bool(cfg.get("include_changes", True)))
        self.response_letter_var = tk.BooleanVar(value=bool(cfg.get("response_letter", False)))
        self.per_reviewer_var = tk.BooleanVar(value=bool(cfg.get("per_reviewer_reports", False)))
        self.annotated_var = tk.BooleanVar(value=bool(cfg.get("annotated_tex", False)))
        self.annotated_pdf_var = tk.BooleanVar(value=bool(cfg.get("annotated_pdf", True)))
        self.include_source_var = tk.BooleanVar(value=bool(cfg.get("include_source", False)))
        self.stable_var = tk.BooleanVar(value=bool(cfg.get("stable", False)))
        self.detailed_var = tk.BooleanVar(value=cfg.get("render_mode", "compact") == "detailed")
        self.write_jsonl_var = tk.BooleanVar(value=bool(cfg.get("write_jsonl", True)))
        self.include_raw_var = tk.BooleanVar(value=bool(cfg.get("include_raw", False)))

        # Three named groups rather than twelve boxes in a grid. The old list
        # put "Keep it tidy for version control" next to "A PDF of the paper",
        # which are not the same kind of decision at all.
        groups = [
            ("Which comments", [
                (self.include_open_var, "Still open",
                 "Comments nobody has marked as done yet."),
                (self.include_resolved_var, "Marked done",
                 "Threads someone already ticked off in Overleaf."),
                (self.include_changes_var, "Tracked changes",
                 "Text people inserted or deleted with Track Changes on. Needs "
                 "Overleaf Premium, or Server Pro if self-hosted."),
            ]),
            ("Documents to write", [
                (self.annotated_pdf_var, "The paper, with comments highlighted in it",
                 "Writes commented.pdf: your paper exactly as Overleaf builds "
                 "it, with each comment highlighted on the words it was written "
                 "about, coloured by who wrote it. Nothing to install and "
                 "nothing to compile. Open it in a web browser: Preview on a "
                 "Mac shows the highlights but not the comments."),
                (self.response_letter_var, "A reply letter to fill in",
                 "response-letter.md, a point-by-point document with a blank "
                 "space under each comment for your answer."),
                (self.per_reviewer_var, "One file per person",
                 "So you can work through one reviewer at a time."),
                (self.annotated_var, "The LaTeX, with comments in it",
                 "A copy of your source with the commented words highlighted, "
                 "to compile yourself. Your own files are never touched."),
                (self.include_source_var, "The text of the commented files",
                 "source/, the full text of every file that has a comment in "
                 "it, so an assistant can read the whole paragraph rather than "
                 "the few words either side."),
            ]),
            ("How to write it", [
                (self.stable_var, "Tidy for version control",
                 "One file that only changes when the comments change, so it "
                 "can live in a git repository without noise."),
                (self.detailed_var, "More of the surrounding text",
                 "More of the sentence around each comment, on several lines."),
                (self.write_jsonl_var, "The data file for other tools",
                 "comments.jsonl, one comment per line. Harmless to leave on."),
                (self.include_raw_var, "The raw data from Overleaf",
                 "Only useful for reporting a problem. Makes the file bigger."),
            ]),
        ]

        def put(parent, title, rows):
            if title:
                ttk.Label(parent, text=title, style="Section.TLabel").pack(
                    anchor="w", pady=(6, 2))
            for var, label, tip in rows:
                cb = ttk.Checkbutton(parent, text=label, variable=var,
                                     style="Card.TCheckbutton")
                cb.pack(anchor="w")
                Tooltip(cb, tip, self)

        # The documents are the real choice, so they get the full width. The
        # two qualifying groups sit side by side underneath, which keeps the
        # whole window short enough not to need scrolling.
        by_title = {title: rows for title, rows in groups}
        put(box, "", by_title["Documents to write"])

        # The two qualifying groups sit side by side underneath, which is what
        # keeps the window short enough not to need scrolling. Giving each its
        # own card cost more in padding than the pairing saved.
        pair = ttk.Frame(box, style="Card.TFrame")
        pair.pack(fill="x")
        pair.columnconfigure(0, weight=1, uniform="opts")
        pair.columnconfigure(1, weight=1, uniform="opts")
        for i, title in enumerate(("Which comments", "How to write it")):
            col = ttk.Frame(pair, style="Card.TFrame")
            col.grid(row=0, column=i, sticky="nw")
            put(col, title, by_title[title])

        who = ttk.Frame(box, style="Card.TFrame")
        who.pack(fill="x", pady=(12, 0))
        ttk.Label(who, text="Only these people (everyone, if empty)",
                  style="Card.TLabel").pack(anchor="w")
        self.reviewer_filter_var = tk.StringVar(value=self.config.get("reviewer_filter", ""))
        ent = ttk.Entry(who, textvariable=self.reviewer_filter_var)
        ent.pack(fill="x", pady=(3, 0))
        Tooltip(ent, "Part of a name or email keeps only their comments. "
                     "Separate several with commas. Leave empty for everybody.", self)


    # ---- run ----

    def _build_actions(self, parent, row=None) -> None:
        holder = ttk.Frame(parent, style="Page.TFrame")
        holder.grid(row=row, column=0, sticky="ew", pady=(10, 6))
        row = holder
        # sv_ttk ships an Accent button that already matches its theme, so use
        # that when it is there and fall back to our own colours when it is not.
        style_name = "Go.TButton"
        try:
            ttk.Style().layout("Accent.TButton")
            style_name = "Accent.TButton"
        except tk.TclError:
            pass                       # no sv_ttk here, our own colours stand in
        self.run_btn = ttk.Button(row, text="Export my comments",
                                  command=self._on_run, style=style_name)
        self.run_btn.pack(side="left")
        self.doctor_btn = ttk.Button(row, text="Check my setup",
                                     command=self._on_doctor)
        self.doctor_btn.pack(side="right")
        Tooltip(self.doctor_btn,
                "Looks at everything that commonly goes wrong, and says what "
                "to do about each. Run this first when something does not "
                "work.", self)
        self.stop_btn = ttk.Button(row, text="Stop", command=self._on_stop)
        Tooltip(self.stop_btn,
                "Stops the export. Nothing is written when you stop, so the "
                "folder is left as it was. A step already in progress has to "
                "finish first, so it can take a moment.", self)
        self.open_md_btn = ttk.Button(row, text="Open the comments",
                                      command=self._open_markdown, state="disabled")
        self.open_md_btn.pack(side="left", padx=8)
        self.open_folder_btn = ttk.Button(row, text="Open the folder",
                                          command=self._open_folder, state="disabled")
        self.open_folder_btn.pack(side="left")

    def _build_status(self, parent, row=None) -> None:
        box = ttk.Frame(parent, style="Page.TFrame")
        box.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        self.progress = ttk.Progressbar(box, mode="indeterminate")
        self._progress_holder = box
        self.status = ttk.Label(box, text="Fill in the boxes above, then press "
                                          "Export my comments.",
                                font=self.font_status, wraplength=680, justify="left")
        self.status.pack(anchor="w", pady=(6, 0))

    def _build_details(self, parent, row=None) -> None:
        """The log lives in a window of its own.

        Inline it added a couple of hundred pixels to a window that has no
        scrollbar, which on a laptop pushed the folder card off the bottom
        where nothing could reach it. It is reference output anyway: you want
        it open beside the window while the export runs, not shoving it.
        """
        holder = ttk.Frame(parent, style="Page.TFrame")
        holder.grid(row=row, column=0, sticky="ew")
        self.details_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(holder, text="Show technical details",
                        variable=self.details_var,
                        command=self._toggle_details).pack(anchor="w")
        ttk.Label(holder, text=f"Settings file: {CONFIG_PATH}",
                  style="PageHint.TLabel", font=self.font_small).pack(
            anchor="w", pady=(2, 0))
        # Everything said so far, so opening the window later still shows it.
        self._log_lines: list[str] = []
        self.details_window = None
        self.log = None

    def _toggle_details(self) -> None:
        if not self.details_var.get():
            if self.details_window is not None:
                self.details_window.destroy()
            self.details_window, self.log = None, None
            return
        if self.details_window is not None:
            self.details_window.lift()
            return

        win = tk.Toplevel(self.root)
        win.title("Technical details")
        win.configure(background=self.palette["bg"])
        win.geometry(f"720x420+{self.root.winfo_rootx() + 60}"
                     f"+{self.root.winfo_rooty() + 80}")
        frame = ttk.Frame(win, style="Page.TFrame", padding=12)
        frame.pack(fill="both", expand=True)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.log = tk.Text(frame, wrap="word", state="disabled",
                           font=self.font_mono, relief="flat", padx=10, pady=8,
                           borderwidth=0, highlightthickness=1,
                           highlightbackground=self.palette["rule"],
                           background=self.palette["field_bg"],
                           foreground=self.palette["fg"],
                           insertbackground=self.palette["fg"])
        self.log.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Scrollbar(frame, command=self.log.yview)
        bar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=bar.set)

        def closed():
            self.details_var.set(False)
            win.destroy()
            self.details_window, self.log = None, None

        win.protocol("WM_DELETE_WINDOW", closed)
        self.details_window = win
        if self._log_lines:
            self.log.configure(state="normal")
            self.log.insert("end", "\n".join(self._log_lines) + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")

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
        line = msg.rstrip("\n")
        self._log_lines.append(line)
        if self.log is None:
            return                      # kept in memory until the window opens
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
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
        why_not_saved = _save_config({
            "theme": self.theme_choice.get(),
            "browser": self.browser_var.get(),
            "show_advanced_browsers": bool(self.show_advanced_var.get()),
            "cookie_value": cookie_value if self.remember_cookie_var.get() else "",
            "remember_cookie": bool(self.remember_cookie_var.get()),
            "project_url": url,
            "project_title": self.title_var.get().strip(),
            "out_dir": out_dir,
            "self_hosted": bool(self.self_hosted_var.get()),
            "cookie_name": self.cookie_name_var.get().strip(),
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
            "annotated_pdf": bool(self.annotated_pdf_var.get()),
            "include_source": bool(self.include_source_var.get()),
            "stable": bool(self.stable_var.get()),
            "include_raw": bool(self.include_raw_var.get()),
        })

        self.run_btn.configure(state="disabled")
        self.cancel_requested = False
        self.stop_btn.configure(state="normal")
        self.stop_btn.pack(side="left", padx=8)
        self.open_md_btn.configure(state="disabled")
        self.open_folder_btn.configure(state="disabled")
        self.progress.pack(fill="x", pady=(0, 4))
        self.progress.start(12)
        self._set_status("Working… this usually takes a few seconds.")
        self._append_log("-" * 60)
        # Said once per export rather than shown as an alert. The export does
        # not need the settings file, so this must not interrupt it, but going
        # quiet is what made this invisible: the boxes came back empty next
        # time with no explanation anywhere.
        if why_not_saved:
            self._append_log(
                f"Your settings could not be saved to {CONFIG_PATH}, so the "
                f"boxes will be empty next time. The export itself is not "
                f"affected. The system said: {why_not_saved}")

        base = self.base_var.get().strip() if self.self_hosted_var.get() else "https://www.overleaf.com"
        cookie_name = (self.cookie_name_var.get().strip()
                       if self.self_hosted_var.get() else "")
        params = dict(
            project_url=url,
            out_dir=Path(out_dir).expanduser(),
            project_title=self.title_var.get().strip() or None,
            base_url=base or "https://www.overleaf.com",
            browser=self.browser_var.get(),
            cookie_value=cookie_value,
            cookie_name=cookie_name or None,
            include_open=bool(self.include_open_var.get()),
            include_resolved=bool(self.include_resolved_var.get()),
            include_changes=bool(self.include_changes_var.get()),
            reviewer_filter=[r.strip() for r in reviewer_text.split(",") if r.strip()],
            render_mode="detailed" if self.detailed_var.get() else "compact",
            write_jsonl=bool(self.write_jsonl_var.get()),
            per_reviewer_reports=bool(self.per_reviewer_var.get()),
            response_letter=bool(self.response_letter_var.get()),
            annotated_tex=bool(self.annotated_var.get()),
            annotated_pdf=bool(self.annotated_pdf_var.get()),
            include_source=bool(self.include_source_var.get()),
            stable=bool(self.stable_var.get()),
            include_raw=bool(self.include_raw_var.get()),
        )
        self.worker = threading.Thread(target=self._worker, args=(params,), daemon=True)
        self.worker.start()

    def _worker(self, params: dict) -> None:
        def progress(msg: str) -> None:
            self.queue.put(("log", msg))
        try:
            self.queue.put(("done", run_export(
                progress=progress, should_cancel=lambda: self.cancel_requested,
                **params)))
        except ExportCancelled as e:
            self.queue.put(("cancelled", e.written))
        except Exception as e:
            self.queue.put(("error", (e, traceback.format_exc())))

    def _on_doctor(self) -> None:
        """Run the checks and show them, without touching the browser.

        The sign-in test is left out on purpose: it can sit for a long time
        reading a cookie store, and this needs to answer quickly.
        """
        from .doctor import run as run_doctor

        self.doctor_btn.configure(state="disabled")
        self._set_status("Checking…", "hint")
        self.root.update_idletasks()
        lines: list[str] = []
        try:
            base = (self.base_var.get().strip() if self.self_hosted_var.get()
                    else "https://www.overleaf.com")
            run_doctor(base_url=base or "https://www.overleaf.com",
                       check_session=False, out=lines.append)
        except Exception as e:                     # a check must never crash the window
            lines.append(f"The check itself failed: {type(e).__name__}: {e}")
        finally:
            self.doctor_btn.configure(state="normal")
        self._set_status("", "hint")
        self.details_var.set(True)
        self._toggle_details()
        for line in lines:
            self._append_log(line)

    def _on_stop(self) -> None:
        if not self.worker or not self.worker.is_alive():
            return
        self.cancel_requested = True
        self.stop_btn.configure(state="disabled")
        self._set_status("Stopping…", "hint")
        self._append_log(
            "Stopping. The step in progress has to finish first, so this can "
            "take a moment.")

    def _on_cancelled(self, written: list[str] | None = None) -> None:
        self.progress.stop()
        self.progress.pack_forget()
        self.cancel_requested = False
        self.stop_btn.pack_forget()
        self.stop_btn.configure(state="normal")
        self.run_btn.configure(state="normal")
        # Stopping during the slow extras happens after the comments are
        # already on disk. Saying "nothing was written" there sends people
        # looking for files that are sitting in the folder.
        if written:
            self._set_status(f"Stopped. {', '.join(written)} had already been "
                             "written. The rest was not.", "hint")
        else:
            self._set_status("Stopped. Nothing was written.", "hint")
        self._append_log("Stopped.")

    def _pump_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "done":
                    self._on_done(payload)  # type: ignore[arg-type]
                elif kind == "cancelled":
                    self._on_cancelled(payload or [])
                elif kind == "error":
                    err, tb = payload  # type: ignore[misc]
                    self._on_error(err, tb)
        except queue.Empty:
            pass
        self.root.after(80, self._pump_queue)

    def _on_done(self, result: ExportResult) -> None:
        self.last_result = result
        self.progress.stop()
        self.progress.pack_forget()
        self.stop_btn.pack_forget()
        self.run_btn.configure(state="normal")
        self.open_md_btn.configure(state="normal")
        self.open_folder_btn.configure(state="normal")

        bits = [f"{result.thread_count} comment thread(s)"]
        if result.open_count:
            bits.append(f"{result.open_count} still open")
        if result.tracked_change_count:
            bits.append(f"{result.tracked_change_count} tracked change(s)")
        done = "Done. Found " + ", ".join(bits) + "."
        # What changed since last time is the more useful half of the sentence
        # once you have exported the same paper before.
        if result.since_summary:
            done += " " + result.since_summary
        self._set_status(done, "ok")

        self._append_log(f"Comments: {result.markdown_path}")
        for label, path in (
            ("Data", result.json_path), ("Lines", result.jsonl_path),
            ("Letter", result.response_letter_path),
            ("Commented PDF", result.annotated_pdf_path),
            ("Source", result.source_dir),
            ("Annotated LaTeX", result.annotated_dir),
            ("Per person", result.by_reviewer_dir), ("Notes for AI", result.agents_path),
            ("What is new", result.since_path),
        ):
            if path is not None:
                self._append_log(f"{label}: {path}")
        if result.annotated_pdf_path is not None:
            self._append_log(
                "Open commented.pdf in a web browser. Chrome, Edge, Firefox "
                "and Safari all show the comment when you hover a highlight. "
                "Preview on a Mac shows the highlights but not the comments, "
                "so drag the file onto a browser window instead. Every comment "
                "is also listed on the last pages.")
        if result.annotated_dir is not None:
            self._append_log(
                "The annotated folder holds your LaTeX with the same "
                "highlighting, to compile on Overleaf or on this computer.")
        if result.stale_anchor_count:
            self._append_log(
                f"{result.stale_anchor_count} comment(s) point at text that has "
                "changed since they were written.")

    def _on_error(self, err: BaseException, tb: str) -> None:
        self.progress.stop()
        self.progress.pack_forget()
        self.stop_btn.pack_forget()
        self.cancel_requested = False
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
