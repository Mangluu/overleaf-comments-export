# overleaf-comments-export

> **⚠️ Unofficial tool.** This is a third-party utility that talks to Overleaf's
> undocumented internal HTTP endpoints. It is not affiliated with or endorsed
> by Overleaf. Endpoints may change without notice. Use at your own risk and
> in accordance with [Overleaf's Terms of Service](https://www.overleaf.com/legal).

Export the comment threads and tracked changes from an Overleaf project into
clean Markdown + structured JSON — designed so an AI assistant (Claude,
ChatGPT, etc.) can ingest reviewer feedback and help you address it.

[![CI](https://github.com/Mangluu/overleaf-comments-export/actions/workflows/ci.yml/badge.svg)](https://github.com/Mangluu/overleaf-comments-export/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/overleaf-comments-export.svg)](https://pypi.org/project/overleaf-comments-export/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

## Why

Overleaf doesn't provide a way to export comments or tracked changes for use
outside the editor. If you want to:

- have an AI agent draft point-by-point replies to reviewers,
- archive reviewer discussions outside of Overleaf,
- batch-address feedback across a large paper, or
- split feedback by reviewer to delegate work,

… you currently have to copy comments by hand. This tool automates that, given
an Overleaf project URL and a logged-in browser session.

## Install

```bash
pip install overleaf-comments-export
```

Requires Python 3.10 or newer (tested up to 3.14). Works on macOS, Linux, and
Windows.

The graphical window needs Python's Tk toolkit, which most Linux distributions
package separately (`sudo apt install python3-tk` on Debian/Ubuntu). The
command line never needs it, and `--gui` tells you what to install if it is
missing.

## Quick start

### CLI

```bash
overleaf-comments-export \
    --project-url https://www.overleaf.com/project/<24-hex-id> \
    --out ./paper-comments \
    --browser safari
```

The first time you run it, sign in to Overleaf in your browser of choice;
the tool reads the session cookie from there.

### GUI

```bash
overleaf-comments-export --gui
```

Opens a small Tkinter window with all options surfaced. Best for non-technical
users.

## What it produces

In your output folder, by default:

| File | Purpose |
|---|---|
| `comments-<date>.md` | Human-readable Markdown grouped by file → section → line, with stable IDs (`C001`, `C002`, …) and source-context snippets around each anchor. |
| `comments.json` | Structured data — `summary`, top-level `threads`, `files`, `comments`, `tracked_changes`, etc. Schema described in `agents.md`. |
| `comments.jsonl` | One self-contained JSON record per comment for streaming/pipelines. |
| `agents.md` | A brief instruction file telling an AI agent how to consume the batch. |
| `response-letter.md` | (Optional, `--response-letter`) A point-by-point reply document, pre-filled with every open comment grouped by who raised it, with blanks for your response. |
| `by-reviewer/<name>.md` | (Optional, `--per-reviewer`) One Markdown per reviewer with only their threads. |
| `comments.log` | Diagnostic log for the run. |

## Filtering

```bash
# Only open comments
overleaf-comments-export --project-url … --out ./out --no-resolved

# Only one reviewer's threads
overleaf-comments-export --project-url … --out ./out --reviewer "Emma"

# Compact (default) vs. detailed (multi-line code-fence) layout
overleaf-comments-export --project-url … --out ./out --render-mode detailed

# Per-reviewer sub-reports under ./out/by-reviewer/
overleaf-comments-export --project-url … --out ./out --per-reviewer

# Draft a point-by-point response letter for the open comments
overleaf-comments-export --project-url … --out ./out --response-letter
```

Full flag reference: `overleaf-comments-export --help`.

## Browser authentication

The tool reads the `overleaf_session2` cookie from your browser. Trade-offs
by browser on macOS:

| Browser | Notes |
|---|---|
| Safari | Recommended. No Keychain prompt; macOS may ask once for permission to read `~/Library/Cookies/`. |
| Firefox | No Keychain prompt; plain SQLite cookie store. |
| Chrome / Edge / Brave | Cookies are AES-encrypted with a Keychain-stored key; **you'll get a Keychain password prompt every run.** Hidden behind an opt-in in the GUI. |

On Windows, Chrome 127+ uses App-Bound Encryption that `browser-cookie3`
can't decrypt. On Linux, snap-packaged browsers sandbox their cookie stores.

**If reading the cookie from your browser fails, paste it instead** — this
works on every OS and browser:

```bash
overleaf-comments-export --project-url <url> --out ./out --cookie "PASTE_HERE"
```

Or set it once: `export OVERLEAF_SESSION="PASTE_HERE"`. In the GUI, choose
**"Paste the cookie myself"** and click **How?** for step-by-step instructions.

To find it: open Overleaf, press F12, go to Application (or Storage) →
Cookies → `https://www.overleaf.com`, and copy the Value of `overleaf_session2`.
Treat it like a password; it stops working when you sign out.

## Troubleshooting

| What you see | What it means |
|---|---|
| "Could not look up www.overleaf.com" | This computer is offline, or a VPN/DNS problem. Not an Overleaf issue. |
| "Overleaf refused the request (not signed in)" | Your session expired. Sign in again in the browser, then re-run. |
| "Could not read Overleaf cookies from chrome" | Use the paste-the-cookie method above. |
| "Overleaf could not find that project" | Wrong link, or this account has no access. |

## Feedback, questions, and contributing

This tool is actively maintained, and feedback shapes what gets built next.

- **Something broke, or the output was wrong?**
  [Open an issue.](https://github.com/Mangluu/overleaf-comments-export/issues/new/choose)
  You do not need to be a programmer — paste what the tool said and that is
  plenty. If Overleaf changes something, everything here stops working at once,
  and you may be the first person to notice.
- **Want it to do something it doesn't?**
  [Suggest a feature.](https://github.com/Mangluu/overleaf-comments-export/issues/new/choose)
  Tell me what you are trying to do, not just the feature — the real task
  usually leads somewhere better.
- **Just a question, or want to show what you built with it?**
  [Discussions.](https://github.com/Mangluu/overleaf-comments-export/discussions)
- **Want to contribute code?** See [CONTRIBUTING.md](CONTRIBUTING.md). It takes
  about two minutes to get the tests running, and there are items marked
  *help wanted* in [ROADMAP.md](ROADMAP.md).

Never include your session cookie in an issue — it is a password for your
Overleaf account, and nobody needs it to fix a bug.

Maintained by [Shivang Gupta](https://github.com/Mangluu), who wrote it to deal
with the review comments on his own papers.

## What's coming next

See [ROADMAP.md](ROADMAP.md). Short version: a response-letter scaffold,
writing out the full source so an AI can see more than a snippet, and a diff
between two exports so you can work through review comments in waves.

Changes are recorded in [CHANGELOG.md](CHANGELOG.md).

## A caution

This tool uses Overleaf's internal endpoints, which are undocumented and can
change without notice. It identifies itself honestly in every request, backs
off when asked to, and only ever reads — it cannot modify your project. Even
so, it may stop working the day Overleaf changes something. If that happens,
please say so in an issue.

## License

MIT — see [LICENSE](LICENSE).
