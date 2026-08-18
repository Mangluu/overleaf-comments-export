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

It also writes **a PDF of your paper with the comments highlighted on the words
they were written about**, coloured by who wrote them. No LaTeX to install and
nothing to compile. See [Comments inside the PDF](#comments-inside-the-pdf).

There are two ways to run it. A **browser extension** that works on the project
tab you already have open and never touches your session cookie, and a **Python
tool with a window** that does everything, including the PDF. There is a
[table below](#which-one-to-use) saying which does what.

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
its replies underneath and a stable id you can point at. A comment written on a
caption says which figure or table it is in. At the end there is a tick list of
every comment, so you can see how much of the review is left.

## Get it

**If you do not write code**, download the app for your computer from the
[latest release](https://github.com/Mangluu/overleaf-comments-export/releases/latest),
unzip it, and open it. There is nothing else to install, and no Python needed.

| Your computer | Download |
|---|---|
| Windows | `OverleafCommentsExport-Windows.zip` |
| Linux | `OverleafCommentsExport-Linux.zip`, then `chmod +x "Overleaf Comments Export"` |

On **Windows** the first time you open it you will be warned about an app that
has not been checked. That is because signing an app costs money every year,
not because anything is wrong. Click More info, then Run anyway.

**There is no Mac download.** There was, and it did not work. macOS blocks apps
it has not checked, signing one costs money every year, and the way people used
to get past the warning, right-clicking and choosing Open, was removed in macOS
15. Everybody who downloaded it hit a wall. Shipping something that does not
open is worse than not shipping it.

On a Mac, use either of these instead. Both work, and neither is gated.

- The browser extension below, if you would rather not touch a terminal.
- `pip install "overleaf-comments-export[gui,pdf]"`, then run
  `overleaf-comments-export --gui` for the same window.

**If you prefer a browser extension**, Chrome, Edge, and other Chromium
browsers can run the exporter inside the Overleaf project you already have
open. It uses that tab's signed-in session without reading or storing the
session cookie, which makes it the easiest option on Windows, where Chrome
encrypts its cookie store in a way the other options cannot read.

Load [`browser-extension/`](browser-extension/) as an unpacked extension. The
[extension guide](browser-extension/README.md) has the installation steps and
explains its deliberately limited permissions.

### Which one to use

|  | Extension | Python tool and app |
|---|---|---|
| To install | Load a folder in your browser | pip, or download an app |
| Session cookie | Never touched | Read from your browser, or pasted |
| Markdown, JSON, JSONL, reply letter | Yes | Yes |
| `commented.pdf`, the paper with the comments highlighted | No | Yes |
| Comments written into your LaTeX | No | Yes |
| One report per reviewer, reviewer filters, git-stable output | No | Yes |
| Interface language | English and Chinese | English |

Use the extension when you want the comments out with nothing to install. Use
the Python tool when you want the PDF, or any of the rest of it. Both write the
same Markdown and JSON, under the same `schema_version`, and a test in the suite
fails if that ever stops being true.

**If you use Python**, it is one command. `--upgrade` matters: without it pip
leaves an old version in place and says "Requirement already satisfied", so you
end up running whatever you installed months ago.

```bash
pip install --upgrade "overleaf-comments-export[gui,pdf]"
overleaf-comments-export --gui
```

That opens the same window. Paste your project link, choose a folder, press the
button.

The window is not a reduced version of the tool. Everything below is in it,
including the reply letter, the comments-in-the-PDF option, and the tidy output
for version control. If you prefer the terminal:

```bash
overleaf-comments-export \
    --project-url https://www.overleaf.com/project/YOUR_PROJECT_ID \
    --out ./paper-comments
```

Python 3.10 or newer, tested up to 3.14, on macOS, Windows, and Linux.

## What you get

| File | What it is |
|---|---|
| `comments-<date>.md` | The readable export, or `comments.md` with `--stable`. Grouped by file, then section, then line. Stable ids `C001`, `T001`. |
| `comments.json` | The same data, structured. Threads, anchors, tracked changes, source context. |
| `comments.jsonl` | One self-contained record per comment, for pipelines. |
| `agents.md` | A short brief telling an AI assistant how to read the other two. |
| `whats-new.md` | Only what changed since your last export into that folder. Written from the second run onwards. |
| `response-letter.md` | Optional. A point-by-point reply document with a blank slot under every open comment. |
| `commented.pdf` | Optional. Your paper as Overleaf builds it, with the comments highlighted on the text. |
| `annotated/` | Optional. Your LaTeX with the comments embedded, if you would rather compile it yourself. |
| `source/` | Optional. The text of every commented file. The offsets in `comments.json` index into these. |
| `by-reviewer/<name>.md` | Optional. One file per reviewer, so you can work through them one person at a time. |

## What changed since last time

Reviews arrive in waves. Export into the same folder again and you get
`whats-new.md`, which lists only what moved since the previous run.

- Comments that are new
- Threads that picked up replies, with just the new replies
- Comments somebody edited after you had already read them, showing both versions
- What was marked resolved, and what was reopened
- Threads that are gone, usually because somebody deleted them
- New tracked changes

Nothing needs turning on. The previous export is already sitting in the folder,
and it gets read before this run overwrites it. To compare against some other
export instead, point `--since` at that folder. To skip it, `--no-since`.

The same lists are in `comments.json` under `since`, as short ids, so you can
ask an assistant to work through only the new feedback.

Two things worth knowing. Short ids are assigned in file then line order, so
one new comment near the top shifts every id below it. `whats-new.md` uses the
ids from the run that wrote it, and the comparison itself is done on thread
ids, so renumbering never shows up as change. And if you run with different
filters than last time, deletions are not reported, because a comment hidden by
`--no-resolved` has not gone anywhere.

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

By default an assistant sees a short window around each comment and no more,
which is not enough to rewrite a paragraph. Add `--include-source` and the text
of every commented file is written to `source/`, with the offsets on each
comment indexing into it, so it can read the paragraph it is being asked to
change.

## Useful options

```bash
--pdf                      # a PDF of your paper with the comments in it
--include-source           # the full text of every commented file
--response-letter          # draft a point-by-point reply document
--annotated-tex            # a copy of your source with the comments embedded
--annotate-style todonotes # put those comments in the margin instead
--per-reviewer             # one report per reviewer
--reviewer "Emma"          # only threads this person touched
--no-resolved              # only what is still open
--no-open                  # only what is already resolved
--no-changes               # skip tracked changes
--render-mode detailed     # more source context around each comment
--stable                   # output that only changes when the comments change
--cookie "PASTE"           # sign in with a pasted cookie
--base-url https://...     # a self-hosted Overleaf
--since ../january         # compare against a different earlier export
--no-since                 # do not compare against an earlier export
--no-jsonl                 # skip comments.jsonl
--include-raw              # keep the untouched Overleaf data in comments.json
--version                  # which version this is
```

Run `overleaf-comments-export --help` for the full list.

A cookie passed as `--cookie` goes into your shell history, and on most systems
it is visible to anyone who can run `ps` while the export is going. It is a live
session, so prefer the environment variable, which the tool reads on its own:

```bash
OVERLEAF_SESSION="paste it here" overleaf-comments-export --project-url https://...
```

The window stores it only if you tick the box, in a file only your account can
read.

## Stopping an export

Press Stop in the window, or Ctrl-C on the command line. Nothing is written
when you stop, so the folder is left as it was. A step already in progress has
to finish first, so it can take a moment.

## Appearance

The window follows whether your computer is set to light or dark. There is an
Appearance picker in the top right if you would rather fix it one way.

## Comments inside the PDF

```bash
pip install --upgrade "overleaf-comments-export[pdf]"
overleaf-comments-export --project-url <link> --out ./review --pdf
```

This writes `commented.pdf`: your paper exactly as Overleaf builds it, with
each comment highlighted on the words it was written about, in the colour of
whoever wrote it. Hover a highlight and the comment appears. This is what
people have been asking Overleaf for since 2023.

There is nothing to install beyond that one line, and nothing to compile. The
PDF Overleaf already built is fetched and the highlights are written into it,
so it has your real document class, your real figures, and your real
bibliography, and it cannot fail to build. Your project is never modified.

If Overleaf has no build to hand, the tool asks it to compile, so this works
whether or not you have opened the project recently.

### Which PDF reader to open it in

Use a **browser**. Chrome, Edge, Firefox and Safari all show the highlights and
the comment on hover, and none of them need anything installed. Adobe Acrobat
Reader works too, and shows the comments in a side panel.

**Preview on a Mac shows the highlights but not the comments.** Preview does
not display the note attached to a highlight, so hovering does nothing. This is
Preview, not the file, and it affects any commented PDF, not just these. Drag
the file onto a browser window instead.

Whatever you open it in, the last pages list every comment in full with the
page it is on, so nothing depends on your reader supporting annotations.

### How the comments find their place

A PDF does not know where the LaTeX went, so the commented words are found by
matching the source against the text on the page. Citations and cross
references are dropped, because they print as numbers. Maths is treated as
unknowable and the words either side of it are used instead. Line-break hyphens
are ignored, so a comment on `force-feedback` still matches when it was set as
`force-` and `feedback` on two lines. A phrase that appears more than once is
resolved by reading in step with the source order.

On the paper this was built against, 82 of 83 comments landed on the right
words. The one that did not was written on a `\abstract` command, which prints
nothing. A comment that cannot be placed is listed rather than put somewhere
plausible.

Papers split across several `.tex` files are handled; every file that carries a
comment is matched against the same pages.

### If you would rather compile it yourself

`--annotated-tex` writes a copy of your LaTeX into `annotated/` with the same
highlighting, to compile on Overleaf or on your own machine.

```bash
overleaf-comments-export --project-url <link> --out ./review --annotated-tex
```

```tex
We propose \pdfmarkupcomment[markup=Highlight,color=ocehlA,author={A. Reviewer}]%
{a novel framework}{[C014] A. Reviewer: Needs a citation. | Reply: Smith 2023 would work}
for measuring quality.
```

A key at the top of the document says whose colour is whose. Where more than
one comment covers the same words, that stretch gets its own colour and a
single note listing all of them. Where the same person has commented twice on
overlapping words, their own colour darkens rather than changing, so it does
not read as somebody else. Resolved comments are struck through in grey.

Some spans cannot be highlighted, because the package that draws the markup
rebuilds the text and fails on maths, on LaTeX commands, and across paragraph
breaks. Those become a pin at the nearest safe point instead. Every comment,
highlighted or not, is listed on a page at the end, which is also what you get
when the PDF is printed, since readers do not print annotations.

`--annotate-style pdfcomment` goes back to a pin at each spot, and
`--annotate-style todonotes` puts notes in the margin.

Your own source is never touched. The annotated copies keep their original
names and folder structure, so `\input` still resolves if you upload the folder.

Reviewer text is made safe before it goes anywhere near the file. A comment
containing `50% of $x$`, a stray backslash, a Greek letter, or punctuation typed
on a Chinese keyboard cannot break the build, because everything written out is
reduced to plain ASCII first. Overleaf compiles with pdflatex, which stops the
whole document on a single character it cannot encode.

## A reply letter to fill in

`--response-letter` writes the document you actually have to hand in. Every
open comment, grouped by whoever raised it, with the passage it refers to,
where it sits, the discussion so far, and blank lines for your answer.

```markdown
### C102 — § Method > Measures (line 192)

**Referring to:** "drawing selected quotes to point at possible sources of mismatch"

**Comment:**
> more than just mismatch i would say

**Response:**
_TODO_

**Change made:**
_TODO — what changed, and where._
```

The ids match `comments.json`, so you can ask an assistant to draft any point by
id and it already knows the quote and the location.

## Keeping the comments in git

By default each run writes `comments-<date>.md`, so you end up with one file per
run. That is fine for a one-off export and useless for version control.

`--stable` writes a single `comments.md` with no timestamps in it. Re-run it and
the file does not move unless the comments actually moved.

```bash
overleaf-comments-export --project-url <link> --out ./review --stable
git add review/comments.md
git commit -m "reviewer comments as of today"
```

Next time you pull the comments, `git diff` shows the new ones and nothing else.

```diff
 thread_count: 41
+thread_count: 42

+**C042** _open_ — "the axis labels"
+- **A. Reviewer** · 2026-08-14 09:12 UTC: units are missing here
```

## Self-hosted Overleaf

If your university runs its own Overleaf rather than using overleaf.com, tick
"My university runs its own Overleaf" in the window and put in its address, or
pass `--base-url https://overleaf.my-university.edu` on the command line.

Comments work. Tracked changes do not, because Overleaf makes them part of
Server Pro rather than the free Community Edition, so there are none to export.

A self-hosted Overleaf keeps your session in a cookie named after itself, so an
instance called ifftex uses `ifftex.sid` rather than `overleaf_session2`.
Anything ending in `.sid` is found without being told, so this normally needs no
setting up. If your server names it something else entirely, the export lists
the cookies it did find and you can name the right one.

```bash
overleaf-comments-export --project-url <link> --out ./out \
  --base-url https://overleaf.my-university.edu --cookie-name my_session
```

There is a box for it in the window too, under the self-hosted options.

Filenames work on every sign-in route now. Where the file tree is unavailable,
the project is fetched as a zip and each document is named by matching its
contents, so comments still group per file.

This path is less tested than overleaf.com, so if something does not work,
please [say so](https://github.com/Mangluu/overleaf-comments-export/issues/new/choose).

## Signing in

The tool needs the session your browser already has. It reads that session and
nothing else, and it only ever reads.

| How | Notes |
|---|---|
| Safari or Firefox | Reads the cookie file directly. No password prompt. |
| Paste it yourself | Works on every computer and browser. The window shows you how, step by step. |
| Chrome, Edge, Brave | Works on macOS but asks for your Keychain password every run. Chrome 127 and newer on Windows cannot be read at all. Use the browser extension there, or paste the cookie. |
| The browser extension | Nothing to sign in to. It uses the tab you already have open and never reads the cookie at all. |

To paste it, open Overleaf, press F12, go to Application or Storage, then
Cookies, then `https://www.overleaf.com`, and copy the value of
`overleaf_session2`. Treat it like a password. It stops working when you sign
out. Nothing is stored unless you tick the box that says so.

```bash
overleaf-comments-export --project-url <link> --out ./out --cookie "PASTE_HERE"
```

## When something goes wrong

Run the check first. It looks at everything that commonly breaks and says what
to do about each.

```bash
overleaf-comments-export --doctor
```

There is a **Check my setup** button in the window that does the same thing.

| What you see | What it means |
|---|---|
| Could not look up www.overleaf.com | This computer is offline, or a VPN is in the way. Nothing to do with your project. |
| Overleaf refused the request | The session expired. Sign in again in your browser and re-run. |
| Could not read Overleaf cookies | Use the browser extension, or the paste method above. This is the usual outcome on Windows with Chrome. |
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
