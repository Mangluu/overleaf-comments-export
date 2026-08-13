# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Fixed
- **A self-hosted Overleaf whose session cookie was not called `overleaf.sid`
  could not be used at all.** These servers name the cookie after themselves,
  so an instance called ifftex uses `ifftex.sid`, and there is no list of those
  worth keeping. Anything ending in `.sid` is now recognised, which needs no
  setting up, and `--cookie-name` names one that is something else entirely.
  There is a box for it in the window as well.
  ([#6](https://github.com/Mangluu/overleaf-comments-export/issues/6), reported
  by @dixr)
- When no session is found, the message now lists the cookies that were
  actually there for that address, and says which names were looked for. The
  old message said only that nothing was found, which left nowhere to go.

### Added
- A first-party Manifest V3 extension for Chrome, Edge, and other Chromium
  browsers. It exports the project already open in the current tab without
  reading or storing its session cookie. Markdown, JSON, JSONL, and a response
  letter are available in English or Chinese; comments and tracked changes keep
  their original timestamps, and each run downloads into its own UTC-stamped
  folder. The extension is read-only, has no backend or telemetry, and requests
  only `activeTab`, `scripting`, and `downloads`.

  It writes the same Markdown, JSON and `agents.md` as the Python export, under
  the same `schema_version`, and the test suite fails if the two ever stop
  agreeing. The PDF with the comments highlighted, the annotated LaTeX, the
  per-reviewer reports and the reviewer filters remain Python only. The README
  has a table saying which does what.

## [0.10.0] — 2026-08-12

### Added
- **A PDF with the comments in it, straight out of the tool.** `--pdf`, or the
  tick box in the window, writes `commented.pdf`: your paper exactly as
  Overleaf builds it, with each comment highlighted on the words it was written
  about and coloured by who wrote it. Hover a highlight to read the comment.

  There is no LaTeX to install and nothing to compile. The PDF Overleaf already
  built is fetched and the highlights are written into it, so the result has
  your real document class, your real figures, and your real bibliography, and
  it cannot fail to build. Overleaf needs to have compiled the project at least
  once; if it has not, the tool says so rather than guessing.

  The commented words are found by matching the source against the text on the
  page, which copes with the hyphens typesetting inserts at line breaks and
  with a phrase that occurs more than once. A comment that cannot be placed is
  listed rather than put somewhere plausible. Every comment is listed at the
  end with the page it is on, because annotations do not print.

  A paper split across several `.tex` files is handled: every file carrying a
  comment is matched against the same pages.

  Install with `pip install 'overleaf-comments-export[pdf]'` to enable it. The
  annotated LaTeX is still there for anyone who wants to compile it themselves.

  Open the result in a web browser. Preview on a Mac draws the highlights but
  never shows the note attached to one, which is a limitation of Preview rather
  than of the file. Every comment is listed on the last pages regardless, with
  the page it is on, since annotations do not print.

### Fixed
- Exported files were named `unknown-<id>.tex` rather than `main.tex` on any
  Mac where Python was installed without running "Install Certificates.command".
  Python has no root certificates in that state, so fetching the file tree
  could not verify the connection and the names were lost. When the certificate
  store is empty, the one `requests` already carries is used.
- A missing `resolved-thread-ids` endpoint was logged as "Overleaf could not
  find that project", which reads like the project has gone. It is optional,
  and resolved state is read from the thread list regardless.

## [0.9.1] — 2026-08-12

### Fixed
- **The highlighting added in 0.9.0 never ran.** The export ignored the style
  it was given and always produced the old pins, so nobody had actually seen
  the feature, from the window or from the command line. Every style is now
  covered by a test that goes through the same entry point the window uses,
  which is where this slipped through: each piece worked on its own and the
  wiring between them did not.
- **A comment on text containing maths or a command is now highlighted
  anyway**, on the longest run of ordinary words inside it, instead of falling
  back to a pin. Reviewers write on sentences with `$x$` and `\emph{}` in them
  constantly. On the paper this was tested against it took the comments shown
  in place from 60 to 72 out of 83, and the popup says when the highlight
  covers a little less than the comment did.
- A comment on a whole paragraph marks its opening sentence rather than
  colouring half a page.
- Nothing is written inside a section heading or a caption. LaTeX writes those
  out to a file and reads them back for the contents page, and markup does not
  survive the trip. Comments on a heading get a pin beside it.
- **Pins now carry the colour of whoever wrote the comment**, like highlights
  do, and no longer print on top of the word after them.
- **Files were exported as `unknown-<id>.tex` instead of `main.tex` on Macs.**
  Python installed from python.org has no root certificates until you run
  "Install Certificates.command", so fetching the file tree failed to verify
  and the names were lost. When there are no certificates at all, the ones
  `requests` already carries are used.
- A missing `resolved-thread-ids` endpoint logged "Overleaf could not find that
  project", which reads like the project has gone. It is an optional endpoint
  that some Overleaf versions do not have, and resolved state is read from the
  thread list regardless.

## [0.9.0] — 2026-08-12

### Changed
- **The commented words are now highlighted, in the colour of whoever wrote the
  comment, and the comment appears when you hover the highlight.** The previous
  behaviour, a pin at a point or a note in the margin, never showed you which
  words were being talked about. Both are still available with
  `--annotate-style pdfcomment` and `--annotate-style todonotes`.

  A key at the top says whose colour is whose. When more than one comment
  covers the same words, the shared part gets its own colour and one popup
  listing all of them. When the same person comments twice on overlapping
  words, their own colour darkens rather than switching, so it does not read as
  a second reviewer. Resolved comments are struck through in grey. Every
  comment is also listed on a page at the end, which is what you get when the
  PDF is printed, since readers do not print annotations.

### Fixed
- A comment whose text had changed was pinned at its recorded position, which
  landed one inside `\usepackage[utf8]{inputenc}` and split the command in
  half. Nothing is ever written into the preamble now, nothing is written into
  the middle of a command, and a comment whose text has gone is listed rather
  than guessed at.
- Fallback pins were positioned against the original text but inserted after
  the highlights had already shifted it, so they landed inside other comments'
  popups and vanished. All changes to the file are now made in one pass from
  the end backwards.

## [0.8.1] — 2026-08-12

### Fixed
- **The annotated LaTeX did not compile on Overleaf.** Overleaf builds with
  pdflatex, which stops on any character it has no encoding for, and reviewer
  comments are full of them. The comments on the paper this was tested against
  contained a Greek eta and fullwidth punctuation typed on a Chinese keyboard,
  and either one is enough to fail the whole document.

  Anything written into the file is now reduced to plain ASCII first. Greek
  letters become their names, so eta squared reads as "eta squared". Fullwidth
  punctuation and accents are normalised. Anything with no ASCII meaning at all
  becomes a question mark, because losing one character is better than losing
  the document. There is a test asserting the output is ASCII, and the
  annotated output is now compiled during development rather than only reasoned
  about.

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

[Unreleased]: https://github.com/Mangluu/overleaf-comments-export/compare/v0.10.0...HEAD
[0.10.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.10.0
[0.9.1]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.9.1
[0.9.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.9.0
[0.8.1]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.8.1
[0.8.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.8.0
[0.7.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.7.0
[0.6.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.6.0
[0.5.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.5.0
[0.4.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.4.0
[0.3.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.3.0
[0.2.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.2.0
