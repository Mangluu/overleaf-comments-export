# overleaf-comments-export

Get the review comments out of an Overleaf paper, into Markdown and JSON you
can read, keep, commit, and hand to an AI assistant.

[![CI](https://github.com/Mangluu/overleaf-comments-export/actions/workflows/ci.yml/badge.svg)](https://github.com/Mangluu/overleaf-comments-export/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/overleaf-comments-export.svg)](https://pypi.org/project/overleaf-comments-export/)
[![Downloads](https://img.shields.io/pypi/dm/overleaf-comments-export.svg)](https://pypi.org/project/overleaf-comments-export/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%20to%203.14-blue.svg)](https://www.python.org/)

Overleaf leaves comments out of both the source download and the Git sync, so
the only way to work through them is inside the editor, one at a time. On a
paper with ninety comments from three co-authors that stops being workable.

## What the output looks like

```markdown
## Summary

- **Threads:** 2 (2 open, 0 resolved)
- **Tracked changes:** 0
- **Most active reviewers:** A. Reviewer (2), Co Author (1)

### § Method

**Line 142** — 2 comments

> …We propose **▸a novel framework◂** for measuring perceived quality across conditions.

**C014** _open · 1 reply_ — "a novel framework"
- **A. Reviewer** · 2026-02-25 06:13 UTC: Needs a citation. Which studies show this?
  - ↳ **Co Author** · 2026-02-26 10:00 UTC: Agree, Smith 2023 would work here.

**C015** _open_ — "coherent"
- **A. Reviewer** · 2026-02-27 13:46 UTC: This word is doing a lot of work. Define it.
```

Every comment sits in its section, next to the words it was attached to, with
its replies underneath and a stable id you can point at.

## Install and run

```bash
pip install overleaf-comments-export
overleaf-comments-export --gui
```

That opens a small window. Paste your project link, choose a folder, press the
button. If you prefer the terminal:

```bash
overleaf-comments-export \
    --project-url https://www.overleaf.com/project/YOUR_PROJECT_ID \
    --out ./paper-comments
```

Python 3.10 or newer, tested up to 3.14, on macOS, Windows, and Linux.

## What you get

| File | What it is |
|---|---|
| `comments-<date>.md` | The readable export. Grouped by file, then section, then line. Stable ids `C001`, `T001`. |
| `comments.json` | The same data, structured. Threads, anchors, tracked changes, source context. |
| `comments.jsonl` | One self-contained record per comment, for pipelines. |
| `agents.md` | A short brief telling an AI assistant how to read the other two. |
| `response-letter.md` | Optional. A point-by-point reply document with a blank slot under every open comment. |
| `by-reviewer/<name>.md` | Optional. One file per reviewer, so you can work through them one person at a time. |

## Working through comments with an AI

This is what the export is shaped for. Hand an assistant the folder and it can
work on any comment by id, because it already knows the quoted passage, the
section it lives in, and what the replies said.

Some things that work well.

- Draft a reply to C014 that answers the reviewer and says what we changed.
- Which comments are asking for the same thing? Group them.
- Fill in the response letter for every comment from A. Reviewer.

Tracked changes come through too, as insertions and deletions with the
surrounding text, so a deletion reads as `before ~~removed~~ after`.

## Useful options

```bash
--response-letter        # draft a point-by-point reply document
--per-reviewer           # one report per reviewer
--reviewer "Emma"        # only threads this person touched
--no-resolved            # only what is still open
--render-mode detailed   # more source context around each comment
```

Run `overleaf-comments-export --help` for the full list.

## Signing in

The tool needs the session your browser already has. It reads that session and
nothing else, and it only ever reads.

| How | Notes |
|---|---|
| Safari or Firefox | Reads the cookie file directly. No password prompt. |
| Paste it yourself | Works on every computer and browser. The window shows you how, step by step. |
| Chrome, Edge, Brave | Works on macOS but asks for your Keychain password every run. Chrome 127 and newer on Windows cannot be read at all, so use the paste option there. |

To paste it, open Overleaf, press F12, go to Application or Storage, then
Cookies, then `https://www.overleaf.com`, and copy the value of
`overleaf_session2`. Treat it like a password. It stops working when you sign
out. Nothing is stored unless you tick the box that says so.

```bash
overleaf-comments-export --project-url <link> --out ./out --cookie "PASTE_HERE"
```

## When something goes wrong

| What you see | What it means |
|---|---|
| Could not look up www.overleaf.com | This computer is offline, or a VPN is in the way. Nothing to do with your project. |
| Overleaf refused the request | The session expired. Sign in again in your browser and re-run. |
| Could not read Overleaf cookies | Use the paste method above. |
| The window cannot open | Python's Tk toolkit is missing. The message tells you what to install for your system. |

Anything else, please [open an issue](https://github.com/Mangluu/overleaf-comments-export/issues/new/choose).
Never paste your session cookie into an issue.

## Related projects

Several people hit this same wall independently. Different approaches suit
different people, so here are the others.

- [adakite/extract-overleaf-comments](https://github.com/adakite/extract-overleaf-comments)
  works from a saved copy of the page, and can put comments in the PDF margins.
- [salokr/overleaf-comment-exporter](https://github.com/salokr/overleaf-comment-exporter)
  is a browser extension, so there is nothing to install on the command line.
- [IcarusLemon/overleaf-comments-cli](https://github.com/IcarusLemon/overleaf-comments-cli)
  is another command line exporter, driving a real browser under the hood.

All of them exist because of
[this three year old request](https://github.com/overleaf/overleaf/issues/1126).
An official export would make every one of us unnecessary, which would be the
better outcome.

## Honest limitations

This is an unofficial tool. It uses Overleaf's internal endpoints, which are
undocumented and can change with any release. It identifies itself honestly in
every request, backs off when asked to, and cannot modify your project. Even
so, it may stop working one day without warning. If that happens, please say so
in an issue, because you may be the first to notice.

It is not affiliated with or endorsed by Overleaf. Use it on projects you have
access to, in line with
[Overleaf's terms](https://www.overleaf.com/legal).

## Feedback and contributing

Feedback shapes what gets built next.

- Something broke, or the output was wrong. [Open an issue.](https://github.com/Mangluu/overleaf-comments-export/issues/new/choose)
  You do not need to be a programmer. Paste what the tool said and that is plenty.
- Want it to do something it does not. [Suggest a feature.](https://github.com/Mangluu/overleaf-comments-export/issues/new/choose)
  Describe the task, not only the feature. The real task usually leads somewhere better.
- A question, or something you built with it. [Discussions.](https://github.com/Mangluu/overleaf-comments-export/discussions)
- Code. See [CONTRIBUTING.md](CONTRIBUTING.md). Two minutes to get the tests
  running, and there are items marked *help wanted* in [ROADMAP.md](ROADMAP.md).

What is coming next is in [ROADMAP.md](ROADMAP.md). What already changed is in
[CHANGELOG.md](CHANGELOG.md).

Maintained by [Shivang Gupta](https://github.com/Mangluu), who wrote it to
handle the review comments on his own papers.

## License

MIT. See [LICENSE](LICENSE).
