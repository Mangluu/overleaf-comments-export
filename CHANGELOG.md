# Changelog

All notable changes to this project are documented here.

## [Unreleased]

## [0.16.2] — 2026-08-18

### Changed
- **The field labels line up.** Each card has a grid of its own, so they could
  not share a column; every card now reserves the same measured width for its
  first column, and the entries start on a common edge down the window.
- **The technical log opens in a window of its own.** Inline it added a couple
  of hundred pixels to a window that has no scrollbar, which on a laptop pushed
  the folder card off the bottom where nothing could reach it. It is reference
  output, better read beside the window than shoving it. Lines said while it is
  closed are kept and appear when it opens.
- The folder moved to the right-hand column, next to what to include, since
  both are about what comes out. The two cards that grow when you tick
  something are both on the left, so the window no longer changes height when
  they do.
- The step numbers are gone. They implied a wizard, and once the third card
  moved columns they no longer read in order.

### Fixed
- Ticking "My university runs its own Overleaf" or choosing to paste a cookie
  added rows that could push the last card out of sight, with no scrollbar to
  reach it. The window grows to fit, and stops at the size of the screen.

## [0.16.1] — 2026-08-18

### Changed
- **Nothing scrolls any more.** The window was one long scrolling form, so half
  the decisions were always off screen and the wheel behaviour mattered. It is
  two columns now: what to point it at on the left, what to get out of it on
  the right, and the button along the bottom. Everything is visible at once,
  and the window will not shrink below the size its contents need.
- The progress bar is hidden until something is running. An idle indeterminate
  bar reads as a stuck one.

### Fixed
- A test asserting that the paste-your-cookie box stays hidden was checking
  `winfo_ismapped`, which is false for everything while the test window is
  withdrawn, so it passed without ever testing anything. It now checks the
  container that actually gets hidden.

## [0.16.0] — 2026-08-18

### Changed
- **The window was redesigned.** It read as a form with a dozen boxed outlines
  stacked down it, and everything was set within two points of everything else,
  so nothing stood out.

  It is paper and ink now. The light theme is the warm off-white of a printed
  page rather than screen white, the text is the warm near-black of ink, and
  the accent is a muted scholarly green. The name is set in a serif, because
  this is a tool for people writing papers and a serif says so before any of
  the words do.

  Sections are cards, which are a surface and generous space rather than a
  border, since a dozen outlines was most of what made it look busy. The twelve
  options are now three named groups, because "Keep it tidy for version
  control" and "A PDF of the paper" were sitting side by side as though they
  were the same kind of decision. The technical log is set in a monospaced
  face, which is what it always wanted.

### Fixed
- A `TclError` while the window was being built was reported as "there is no
  screen to open a window on", which is advice about headless servers and had
  nothing to do with the actual fault. Only a genuinely missing display says
  that now.

## [0.15.0] — 2026-08-17

### Added
- **`--doctor`, and a "Check my setup" button in the window.** One pass over
  everything that commonly goes wrong, with what to do about each in plain
  words: the Python version, whether the copy you are running is the current
  one, root certificates, PDF support, the Tk toolkit, whether Overleaf is
  reachable, and whether your session works.

  Every problem anyone hit was diagnosable and nobody diagnosed it. Someone ran
  a version from months earlier because `pip install` without `--upgrade` says
  "Requirement already satisfied" and stops. Someone else could not read a
  cookie because a downloaded app has no Full Disk Access. None of those
  announce themselves. It exits non-zero when something needs fixing, so it can
  be pasted into a bug report.

### Fixed
- **Scrolling barely worked, and on Linux not at all.** The wheel handler
  divided the movement by three and truncated, so on a Mac trackpad, where the
  system already scales it, a small movement scrolled zero and the window did
  not move. On Windows the same arithmetic jumped forty lines per notch. X11
  sends buttons rather than a delta and was not handled at all. Each platform
  is now treated the way it actually reports.
- The wheel was bound to every widget, so the technical log could not be
  scrolled once it was longer than its box. It keeps its own now.

## [0.14.1] — 2026-08-16

### Fixed
- **The macOS instructions did not work.** Both the README and the note inside
  the downloaded zip said to right-click the app and choose Open. Apple removed
  that in macOS 15, and on 15 and newer the warning offers only Done and Move to
  Bin, so anyone who downloaded the Mac app was told to do something impossible
  and given nothing else to try. Both now describe System Settings, Privacy &
  Security, Open Anyway, and the one-line `xattr` command for anyone who prefers
  the Terminal.
- **"Could not read Overleaf cookies" blamed Chrome.** On a Mac every browser's
  cookie store sits behind Full Disk Access, Safari included, and a freshly
  downloaded app has none. The message sent Safari users looking for a problem
  they did not have, and never mentioned that pasting the cookie needs no
  permission at all. It now gives the three routes in order of how little they
  ask of you.
- **`pip install` left old versions in place.** The README said
  `pip install overleaf-comments-export`, which pip satisfies with whatever is
  already installed, so someone who installed months ago upgraded nothing and
  saw "Requirement already satisfied". It now says `--upgrade`.
- The window title carries the version, so it is visible at a glance which one
  is running.

## [0.14.0] — 2026-08-14

### Added
- **A checklist of what is left to address.** The export said what the comments
  were and nothing about progress, and on a paper with ninety of them across
  three reviewers, "what is left" is the question you ask most often. Every
  comment now appears as a tick box at the end of the Markdown, with a count in
  the summary that links to it.

  Deliberately stateless. A tick means Overleaf says that thread is resolved,
  nothing more. Progress is not kept in a side file, because a file that has to
  be merged on every run is the easiest way to introduce bugs nobody can
  reproduce. Tick the boxes as you work, and a fresh export starts from
  Overleaf again.
  ([#1](https://github.com/Mangluu/overleaf-comments-export/issues/1))

- **A comment inside a figure or table says so.** It reads `in Figure 3
  (\`fig:spi-by-condition\`)` rather than giving a line number under whichever
  section happened to be above it, which is often the wrong one because a float
  drifts from the text it was written beside. Reviewers comment on captions
  constantly.

  `figure*` and `table*` share their counter with the unstarred form, an
  uncaptioned float takes no number because LaTeX does not give it one, a
  caption belonging to a subfigure or to a nested float is not mistaken for the
  outer one, and a commented-out float is ignored. A comment that is not in a
  float is unchanged. The enclosing float is in `comments.json` too.
  ([#2](https://github.com/Mangluu/overleaf-comments-export/issues/2))

## [0.13.0] — 2026-08-14

### Added
- **`--include-source` writes the text of every commented file.** The export
  gave an assistant a short window either side of each comment and nothing
  more, so asking it to rewrite a paragraph meant asking it to rewrite
  something it could not see. `source/` now holds each commented file exactly
  as it is in the project, and the `offset` and `line` on every comment index
  into those files, so the paragraph can actually be read. There is a tick box
  for it in the window.

  Verified on a real paper: all 83 comments' offsets index correctly into the
  file that was written.

### Fixed
- A document's path is written into the export folder, and since the project
  zip became a source of filenames that name can come from a zip member. Zip
  entries are allowed to say `../../elsewhere`. Paths are now reduced to
  something that stays inside the chosen folder.

## [0.12.0] — 2026-08-14

### Added
- **An export can be stopped.** There is a Stop button in the window while one
  is running, and Ctrl-C on the command line. Until now the Run button stayed
  disabled until the export finished, so a step that hung left the window stuck
  with no way out short of quitting it.

  Nothing is written when you stop. The checks sit between steps and inside the
  loops that do the repeated work, including the last one before any file is
  created, so the output folder is left exactly as it was rather than holding
  half an export. Waiting out a retry is broken into short steps too, so
  stopping during a backoff does not have to sit through the whole delay.

  A step already in progress has to finish first. A request in flight cannot be
  interrupted from another thread, and neither can reading a browser's cookie
  store, so stopping takes effect at the next boundary rather than instantly.
  The window says so while it waits.

## [0.11.1] — 2026-08-13

### Fixed
- **Running a second export in the window left the first one's log file
  attached.** Every later run wrote into it as well, and a file handle was kept
  open for each. Only the current run's log receives anything now.
- **Choosing a folder that cannot be written to reported an unexpected bug.**
  It is an ordinary mistake, and it now says so in plain words before anything
  is fetched, rather than surfacing a raw permission error part way through.
- The project zip fetched to recover filenames was read into memory whole. It
  is streamed and capped at 250 MB now, because it is a fallback that runs when
  something has already gone wrong and it must not be the thing that takes the
  machine down.

## [0.11.0] — 2026-08-13

### Added
- **A browser extension**, contributed by [@Agent-QG](https://github.com/Agent-QG).
  It exports the project open in the current tab and never reads or stores the
  session cookie, which makes it the easiest option on Windows, where Chrome
  encrypts its cookie store in a way nothing else here can read. It writes the
  same Markdown, JSON and `agents.md` as the Python export, under the same
  `schema_version`, and a test fails if the two ever stop agreeing. The PDF with
  the comments highlighted, the annotated LaTeX and the per-reviewer reports
  remain Python only; the README has a table.
  ([#7](https://github.com/Mangluu/overleaf-comments-export/pull/7))

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
- **Comments filed under `<unknown-6a21dec…>` instead of a filename.** Real
  names come from the file tree, and there was no way to get one after signing
  in with a pasted cookie, because that route needs a browser. Overleaf will
  hand over the whole project as a zip on request, over the same ordinary
  authenticated HTTP everything else here uses, and a file is identified well
  enough by what is in it. The document text is already downloaded, so it is
  matched against the zip and takes that file's name.

  The zip is fetched only when the file tree came up short, and only once.
  Where two files in a project have identical contents, both are left with the
  placeholder, because a wrong filename is worse than an honest one. Cosmetic
  on a single-file paper; on a multi-file one it restores the grouping.
  ([#4](https://github.com/Mangluu/overleaf-comments-export/issues/4))
- The settings file was read without naming an encoding, so on Windows a saved
  project title or output path containing any non-Latin character stopped the
  window opening at all.

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

[Unreleased]: https://github.com/Mangluu/overleaf-comments-export/compare/v0.16.2...HEAD
[0.16.2]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.16.2
[0.16.1]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.16.1
[0.16.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.16.0
[0.15.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.15.0
[0.14.1]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.14.1
[0.14.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.14.0
[0.13.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.13.0
[0.12.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.12.0
[0.11.1]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.11.1
[0.11.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.11.0
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
