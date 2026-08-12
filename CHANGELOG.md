# Changelog

All notable changes to this project are documented here.

## [Unreleased]

## [0.8.0] — 2026-08-12

### Added
- **Dark mode.** The window follows whether the computer is set to light or
  dark, on macOS, Windows and Linux. An Appearance picker in the top right
  overrides it if you would rather fix it one way, and the choice is
  remembered.

### Fixed
- **The option that puts comments in the PDF was impossible to find.** It was
  labelled "A copy of the paper with comments in it", and the word PDF only
  appeared in the hover text, so anyone scanning the list for "PDF" concluded
  the feature did not exist. It is now called "Comments inside the PDF", and
  after the export the window says what to do with the folder it wrote.

## [0.7.0] — 2026-08-11

### Added
- **Downloadable apps.** Every release now carries a double-clickable
  application for macOS, Windows, and Linux, built automatically. People who do
  not write code no longer need Python at all.
- **The window was rewritten for people who do not use a terminal.** Three
  numbered steps rather than a form, plain language instead of jargon, hover
  explanations on anything unavoidably technical, the project link checked as
  you type, and the technical log folded away until it is wanted. Every option
  the command line has is now in the window, including the reply letter, the
  annotated LaTeX, and keeping the output tidy for version control.
- **Self-hosted Overleaf can be used from the window**, not only from the
  command line. Tick "My university runs its own Overleaf" and give its
  address.

### Fixed
- Reading the cookie from a browser looked it up under `overleaf.com` no matter
  which server you had asked for, so it never found anything on a self-hosted
  Overleaf. It now uses the address you gave.
- Self-hosted Overleaf names its session cookie `overleaf.sid`, and older
  installs use `sharelatex.sid`. Both are now recognised.
- Failing to find a browser cookie is an ordinary explainable problem, so it no
  longer arrives as an unexpected error.

## [0.6.0] — 2026-08-11

### Added
- `--annotated-tex` writes a copy of your LaTeX source with each comment
  embedded at the point it was made, so compiling it produces a PDF that
  carries the comments. This is the original request in
  [overleaf/overleaf#1126](https://github.com/overleaf/overleaf/issues/1126),
  open since 2023. `--annotate-style todonotes` puts the comments in the margin
  instead of using clickable PDF notes.

  Reviewer text is escaped before it is written, so a comment containing
  `50% of $x$`, a stray backslash, or pasted LaTeX cannot break the build.
  Notes are never placed inside inline maths or after a `%`, and insertion runs
  backwards through the document so earlier notes cannot move later ones.

## [0.5.0] — 2026-08-11

### Added
- `--stable` writes output that only changes when the comments change. One
  `comments.md` rather than a new dated file every run, and no timestamps
  inside it. Re-running with nothing new produces a byte-identical file, so the
  export can live in a git repository and a diff shows the new comments and
  nothing else. There is a tick box for it in the window as well.

### Fixed
- Output ordering no longer depends on the order Overleaf happened to return
  things. Threads and orphan ids are sorted, and reviewers with the same number
  of comments are listed by name. Two runs over the same data now produce the
  same bytes.

### Changed
- Rewrote the README around what the tool actually produces, with a real
  sample of the output, an honest limitations section, and links to the other
  Overleaf comment exporters people have built.
- Added a release checklist to the contributing guide, so the docs move with
  the code.

## [0.4.0] — 2026-08-11

### Added
- `--response-letter` writes `response-letter.md`: a point-by-point reply
  document pre-filled with every open comment, grouped by whoever raised it,
  each with its quote, location, the discussion so far, and blanks for your
  response and the change you made. Available as a tick box in the window too.
- Unexpected crashes now print where to report them, with the version number.
- Issue templates, a contributing guide, a roadmap, and this changelog.

### Fixed
- Asking for the window on a machine without Python's Tk toolkit produced a
  raw `ModuleNotFoundError`. It now explains what to install, per operating
  system, and points at the command line as an alternative. Tk is **not**
  bundled with Python on most Linux distributions, so this affected a real
  share of users.
- Asking for the window on a machine with no screen (a server, or an SSH
  session) now explains that and suggests the command line, instead of
  raising `TclError`.
- Python 3.14 is now tested in CI and declared in the package metadata.

## [0.3.0] — 2026-08-11

### Fixed
- Network failures (DNS, timeout, SSL) showed a raw Python traceback. They now
  explain what went wrong and what to do about it, and the tool exits cleanly.
- Transient failures are retried: three attempts with backoff, honouring
  `Retry-After`. Client errors other than 429 are not retried.
- The version was inconsistent — the library said 0.1.0 while the package was
  0.2.0 and the User-Agent said 0.1. There is one source of truth now, and it
  is stamped into `comments.json` and the Markdown front matter.
- The User-Agent was never actually sent: `requests` pre-fills the header, so
  `setdefault` silently did nothing.
- Tracked deletions had no surrounding context, because deleted text is not in
  the live document and could not be found by offset. Deletions now render as
  `before ~~deleted~~ after`.

### Added
- Paste-your-own-cookie authentication, via `--cookie`, the `OVERLEAF_SESSION`
  environment variable, or a GUI option with step-by-step instructions. This
  works everywhere, including where reading the browser's cookie store cannot
  work: Chrome 127+ on Windows, snap-packaged browsers on Linux, and
  locked-down macOS. The cookie is not saved unless you ask for it.
- Replies are distinguishable from the comment they answer. JSON tags each
  message `role: comment` or `role: reply` with `reply_index` and
  `reply_count`; Markdown indents replies under the original with `↳`.
- `resolved_by` resolves to a name and email instead of a raw user id.
- A `--version` flag and a troubleshooting table in the README.

## [0.2.0] — 2026-05-17

First public release.

- Markdown grouped by file, section, and line, with stable short IDs
  (`C001`, `T001`).
- `comments.json`, `comments.jsonl`, and an `agents.md` brief for AI consumers.
- Filters by open/resolved/tracked-changes and by reviewer; optional
  per-reviewer reports.
- Compact and detailed rendering modes.
- Tkinter GUI.

[Unreleased]: https://github.com/Mangluu/overleaf-comments-export/compare/v0.8.0...HEAD
[0.8.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.8.0
[0.7.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.7.0
[0.6.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.6.0
[0.5.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.5.0
[0.4.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.4.0
[0.3.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.3.0
[0.2.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.2.0
