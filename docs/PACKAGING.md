# Packaging runbook (Phase 1 + Phase 2)

This file is a runbook for going beyond `pip install` to **packaged GUI
binaries** for macOS, Windows, and Linux, distributed via GitHub Releases.

Phase 0 (PyPI library, CI, tests, license, README) is already done — see the
repo root.

Phase 1 and 2 below are optional. They add a real cross-platform GUI app
experience at the cost of more code, more CI minutes, and per-platform
quirks. Skip them if `pip install overleaf-comments-export` is enough for
your audience.

---

## Phase 1 — Make the GUI genuinely cross-platform

Goal: a single `pip install overleaf-comments-export[gui]` + launching with
`overleaf-comments-export --gui` looks and works correctly on macOS,
Windows, and Linux.

### 1.1 Add a "paste cookie" auth path (recommended)

Browser cookie reading is the single biggest source of cross-platform
fragility (macOS Keychain, Windows App-Bound Encryption since Chrome 127,
Linux snap sandboxing).

Add a fourth option in the GUI's Browser dropdown: **"Paste session cookie
manually"**. When selected, replace the dropdown's help text with a text
field labeled "Cookie value (`overleaf_session2=…`)" and a "How to copy"
disclosure that links to the docs.

Implementation sketch:

```python
# In client.py, add:
def _connect_via_pasted_cookie(self, cookie_value: str) -> requests.Session:
    session = requests.Session()
    session.cookies.set(
        "overleaf_session2", cookie_value,
        domain="overleaf.com", path="/", secure=True,
    )
    return session

# In connect(), add a branch for browser == "manual" that pulls the
# cookie from a new parameter cookie_value: str.
```

In the GUI, when "manual" is selected, surface a text Entry for the cookie
value and pass it through to `run_export` via a new `cookie_value` kwarg.

User docs (`docs/MANUAL_COOKIE.md`):
1. Open your project in Overleaf.
2. Open DevTools (F12 / ⌘⌥I).
3. Application tab → Storage → Cookies → `https://www.overleaf.com`.
4. Copy the `Value` of `overleaf_session2`.
5. Paste it into the app's cookie field.

### 1.2 Modernize the Tkinter theme

Already wired: `sv_ttk.set_theme("light")` is called in `_apply_theme()`
when `sv-ttk` is installed (via the `[gui]` extra).

To verify the look across OSes:

- **macOS**: should pick up `aqua` even without sv-ttk; with sv-ttk, looks
  consistent with the Win/Linux build.
- **Windows**: Without sv-ttk, the default theme looks like Windows 95.
  With sv-ttk, looks modern.
- **Linux**: Default Tk theme is ugly. With sv-ttk, looks modern.

If you want to go further: try `ttkbootstrap` (more themes, larger
dependency).

### 1.3 Test on Linux + Windows

Easiest options:

- **Linux**: A free Ubuntu VM in UTM or VirtualBox, or just SSH into any
  Linux box with a graphical session. Install Python 3.12, `pip install -e
  ".[gui,test]"`, run `pytest`, then `overleaf-comments-export --gui`.
- **Windows**: Use the free [Microsoft Windows 11 dev VM](https://developer.microsoft.com/en-us/windows/downloads/virtual-machines/)
  in UTM (Apple Silicon) or VMware/VirtualBox. Install Python 3.12 from
  python.org (it ships with tkinter), then `pip install -e ".[gui,test]"`.

Things to specifically verify:

- File dialog ("Browse…") returns the right paths on each OS.
- Output folder path with spaces and unicode works.
- The "Open Markdown" / "Open Output Folder" buttons launch the right app
  (`open` on macOS, `os.startfile` on Windows, `xdg-open` on Linux —
  already handled in `_open_path`).
- Config file lands in `platformdirs.user_config_dir()` on each OS
  (`~/Library/Application Support/...` on Mac, `%APPDATA%\...` on Win,
  `~/.config/...` on Linux).

---

## Phase 2 — Packaged binaries via GitHub Actions

Goal: `.dmg` for macOS, `.msi` or `.exe` for Windows, `.AppImage` or
`.deb` for Linux, downloadable from GitHub Releases.

### 2.1 Choose a packager

| Tool | Pros | Cons |
|---|---|---|
| **Briefcase (BeeWare)** | One config, all three OSes. Active dev. | Heavier setup, slower builds. |
| **PyInstaller** | Simple, well-known, fast. | Per-OS spec files. |
| **Nuitka** | Best startup time. | Slower builds; per-OS complexity. |

Recommendation: **Briefcase** — it handles all three OSes from one
`pyproject.toml` config and you already have `pyproject.toml`.

### 2.2 Add Briefcase config

Append to `pyproject.toml`:

```toml
[tool.briefcase]
project_name = "Overleaf Comments Export"
bundle = "com.example.overleaf_comments_export"
version = "0.2.0"
url = "https://github.com/Mangluu/overleaf-comments-export"
license = "MIT license"
author = "Shivang"
author_email = "shivang@users.noreply.github.com"  # replace with your real address

[tool.briefcase.app.overleaf-comments-export]
formal_name = "Overleaf Comments Export"
description = "Export Overleaf comments to Markdown + JSON."
icon = "src/overleaf_comments_export/resources/icon"
sources = ["src/overleaf_comments_export"]
requires = [
    "pyoverleaf>=0.1.7",
    "browser-cookie3>=0.19",
    "requests>=2.31",
    "platformdirs>=4.0",
    "sv-ttk>=2.6",
]

[tool.briefcase.app.overleaf-comments-export.macOS]
requires = ["std-nslog>=1.0.0"]

[tool.briefcase.app.overleaf-comments-export.linux]
requires = []
system_requires = []

[tool.briefcase.app.overleaf-comments-export.windows]
requires = []
```

Then locally:

```bash
pipx install briefcase
briefcase create
briefcase build
briefcase package      # produces a platform installer in ./dist
```

### 2.3 GitHub Actions matrix for binary builds

Add `.github/workflows/release.yml`:

```yaml
name: Release binaries

on:
  release:
    types: [published]

jobs:
  build:
    name: Build ${{ matrix.os }} binary
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: python -m pip install --upgrade pip briefcase
      - run: briefcase create
      - run: briefcase build
      - run: briefcase package --no-sign
      - uses: actions/upload-release-asset@v1
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          upload_url: ${{ github.event.release.upload_url }}
          asset_path: dist/*
          asset_name: overleaf-comments-export-${{ matrix.os }}
          asset_content_type: application/octet-stream
```

(Adjust `asset_path` once you see what Briefcase produces; the wildcard
may need to be per-OS.)

### 2.4 The "scary first-launch warning"

Without code signing:

- **macOS** users will see "Apple cannot verify…". Workaround they must
  do once: right-click → Open → Open.
- **Windows** users will see SmartScreen "Windows protected your PC".
  Workaround: More info → Run anyway.
- **Linux AppImages** don't have this problem.

Document these clearly in the README's install section.

### 2.5 Code signing (only if it matters)

Skip unless you start getting "scary warning" complaints from real users.

- macOS: ~$99/yr Apple Developer ID + notarization. Use the `gon` CLI or
  Briefcase's signing options.
- Windows: ~$300–500/yr for an EV code-signing certificate. Or wait — the
  reputation system eventually trusts unsigned binaries from a stable
  source, but it takes a while.

---

## Phase 1+2 checklist

When you (or a contributor) are ready to do this, the rough order:

- [ ] Add "Paste cookie manually" auth path in `client.py` + `gui.py`
- [ ] Document the cookie-copy flow in `docs/MANUAL_COOKIE.md`
- [ ] Verify the GUI on a Linux box (Ubuntu 22.04+) and a Windows VM
- [ ] Make a small icon set for the app (`icon.icns`, `icon.ico`, `icon.png`)
- [ ] Add Briefcase config to `pyproject.toml`
- [ ] Add `.github/workflows/release.yml`
- [ ] Tag a release `v0.3.0` and let CI build + attach binaries
- [ ] Update README install section with binary download links
- [ ] Add a one-paragraph "first-launch warning" note for Mac/Win
- [ ] (Optional, much later) Pay for signing certificates

---

## What to skip

- **Auto-update.** Each platform has its own mechanism (Sparkle, MSIX,
  AppImageUpdate, Snap). Users can just re-download. Don't bother unless
  this becomes a daily-use tool for a wide audience.
- **App stores.** Mac App Store and Microsoft Store both have review
  processes and content rules that don't fit a scraper. GitHub Releases
  is the right home.
- **Telemetry / crash reporting.** For a "use at your own risk" tool, the
  log file is enough.
