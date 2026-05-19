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

Requires Python 3.10+. Works on macOS, Linux, and Windows.

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
doesn't fully decrypt yet — prefer Firefox or Edge on Windows.

On Linux, snap-packaged browsers sandbox their cookies — install browsers as
native packages if you can.

## Status & maintenance

This is a personal research utility published in case it's useful to others.
It is provided as-is, with no guaranteed maintenance, no SLA, and no roadmap.
Pull requests are welcome; issues may or may not be acted upon.

If Overleaf changes their internal API, this tool may stop working until
someone (you?) adapts it.

## License

MIT — see [LICENSE](LICENSE).
