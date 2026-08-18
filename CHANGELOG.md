# Changelog

All notable changes to this project are documented here.

## [Unreleased]

## [0.21.1] — 2026-08-18

### Fixed
- **The new scenario matrix failed on Windows, and it was the matrix's own
  fault.** It runs the extension's core in node and read its output with
  `text=True`, which decodes with the locale encoding, and that is cp1252 on
  Windows. One scenario deliberately carries Greek and Chinese to catch
  exactly this class of thing, and the first thing it caught was the test
  that runs it.
- A rule now fails the build for any `subprocess` call that decodes with the
  locale encoding instead of naming one. It immediately found two more, in
  the theme detection. Neither was reachable on Windows, which reads the
  theme from the registry rather than a subprocess, so neither was a live
  bug, but both now name their encoding.

## [0.21.0] — 2026-08-18

The three worthwhile items from the second review's architecture list.

### Changed
- **An export appears all at once, or not at all.** Every file is now written
  into a staging folder inside the destination and moved into place in one
  step at the end. Before this, output went straight to the chosen folder one
  file at a time, so stopping an export, losing the disk, or a crash part-way
  left a folder holding some files from this run and some from the last one.

  Because of it, "Stopped. Nothing was written." is a promise the code can
  keep. The plumbing added in 0.18.0 to admit which files had already landed
  is gone, along with the case that made it necessary. A folder that had a
  `by-reviewer/` file from an earlier run also no longer keeps it.

  The log is the exception and is still written live, since it is what you
  read when an export fails and never reaches the end.

- **The settings file is created owner-only rather than made owner-only.** It
  was written and then chmodded, so a live Overleaf session sat in a
  world-readable file for as long as that took. It is now created 0600 with
  `os.open`, written beside the real file and moved into place, so a crash
  part-way cannot leave a truncated one either.

- **The cross-implementation parity test runs a matrix, not one happy path.**
  Seven scenarios now go through both Python and the browser extension and
  are compared: the baseline, orphan-only threads, a stale offset past the
  end of the file, a quoted title with Greek and Chinese text in the
  comments, one thread with two anchors, a long reply chain, and tracked
  changes with no comments at all.

  A single fixture is how the JSONL contract drifted apart unnoticed. Dropping
  orphan records from the extension's JSONL is now caught, and only the
  orphan-only scenario catches it.

## [0.20.0] — 2026-08-18

A second external review of 0.19.0. Every finding was real.

### Fixed
- **Releases were published to PyPI without any test having passed on them.**
  CI runs on pushes to a branch and this publishes on a tag push, which is a
  different event, so CI never ran on the tagged commit at all. They were two
  unrelated runs racing: on 0.19.0 the upload finished about 35 seconds before
  CI did. The tests now run inside the publish workflow and publishing waits
  for them.
- **A thread with no anchor was invisible in the JSON counts.** `open_count`
  and `resolved_count` were worked out from anchored comments while
  `thread_count` came from threads, so a project whose ranges could not be
  read reported one thread, none open and none resolved. The Markdown had
  always counted threads, so the two files from one export disagreed. Both
  count threads now, which also stops a thread being counted twice if it ever
  carries two anchors.
- **Two reviewers could end up sharing one report.** `A B`, `A-B`, `A_B` and
  `A.B` all become `a-b`, and the second `by-reviewer` file quietly replaced
  the first. Colliding names get a suffix.
- **Every per-reviewer report claimed the whole project's totals.** Each was
  handed all the threads, so a file headed with one person's name said there
  were 83 threads and four reviewers. Each now sees only its own.
- **A title with a quote in it broke the Markdown front matter.** A paper
  called `A "quoted" paper` ended the YAML scalar early and made the whole
  block unparseable. Escaped properly now, the way the extension always did.
- **The extension returned an out-of-range offset for a stale anchor.** It
  computed the bounded value, used it for the line and column, and returned
  the raw one, so a 16-character document could report offset 10000 beside
  line 1. This is the same bug Python fixed in 0.18.0; only half of it had
  been fixed.
- Extension version said 1.1.0 in two places and 1.0.0 in two others.

### Changed
- **`comments.jsonl` is derived from `comments.json` rather than built a
  second time.** The two had drifted: Python's records carried no
  `schema_version`, no `type`, no `project` and no orphan threads, all of
  which the extension wrote. The parity test now covers JSONL as well, so
  they cannot disagree again.

## [0.19.0] — 2026-08-18

Issues filed from the end-to-end audit, fixed one at a time.

### Fixed
- **The built PDF is only fetched from the site you signed in to** (#8). The
  compile reply names the host to download from, and it was used as given.
  It is the one value in any response that decides where an authenticated
  request goes. Checked against the site now, with anything else ignored and
  logged.

  Compared against the site rather than the exact host, because Overleaf's
  real answer is a sibling of `www` and not a child of it: signed in to
  `www.overleaf.com`, the build comes back on `clsi-a1b2.overleaf.com`. The
  first version compared full hosts and would have broken every real PDF
  download; the test caught it before it shipped.
- **Settings that cannot be saved say so** (#9). It used to fail in silence,
  so every box came back empty next time with no explanation and nothing in
  the log. It still never raises, since an export does not need the settings
  file, but it now logs the reason and says so once in the window. It also
  creates the settings folder if it is missing, which it never did.
- **Closing the window no longer leaves a stray callback.** The queue pump
  rescheduled itself every 80ms and nothing cancelled it, so shutting the
  window fired one more callback against widgets that were gone and Tk
  reported `invalid command name ..._pump_queue`.

### Documented
- Why the root certificate fallback sets an environment variable (#10). The
  call that fails is `websocket.create_connection` inside pyoverleaf, which
  goes through Python's `ssl` module and takes no bundle argument, so
  nothing set on a requests session reaches it. It also only fires when the
  store is empty, meaning nothing in that process was verifying anyway.
  Closed without a code change, with three tests holding the guard.

### Known
- The short-screen window limit (#11) is still open. A second attempt at a
  scroller was reverted. The issue records what was measured and where the
  next attempt should start.

## [0.18.4] — 2026-08-18

From an end-to-end audit of the whole repository.

### Changed
- **Exports do about half the work they used to.** `to_ascii` runs on every
  comment and every line of source that goes into the annotated LaTeX, and it
  did 52 whole-string replaces, a Unicode normalize and two passes over every
  character before discovering the text was plain ASCII, which almost all of
  it is. It now returns immediately in that case. On a 500-comment paper an
  export goes from 0.31s to 0.13s of local work, and from 2.6 million
  function calls to 314 thousand. Output is byte for byte identical, with a
  test for both paths.

### Removed
- Two functions nothing called: `gui._hint_in` and `client.looks_self_hosted`.

### Documentation
- `OVERLEAF_SESSION` was supported and undocumented. It is the safer way to
  pass a session, since `--cookie` puts a live credential into your shell
  history and into the process list. The README now says so and shows it.

## [0.18.3] — 2026-08-18

### Removed
- **The Mac download is gone.** It did not work. macOS blocks apps it has not
  checked, signing one needs a certificate that costs money every year, and
  the way people used to get past the warning, right-clicking and choosing
  Open, was removed in macOS 15. Everybody who downloaded it hit the same
  wall. Shipping something that does not open is worse than not shipping it.

  It has also been taken off the 19 earlier releases that still carried it,
  since every copy was equally broken.

  On a Mac, `pip install "overleaf-comments-export[gui,pdf]"` gives the same
  window, and the browser extension needs nothing installed. Neither is
  gated. Windows and Linux downloads are unchanged.

## [0.18.2] — 2026-08-18

### Fixed
- **A window test measured the window manager instead of the window.** It
  asserted `winfo_height() >= winfo_reqheight()`, and the test window is
  withdrawn, so that reads back whatever geometry was last applied rather
  than anything the code decided. It passed on a developer's machine and
  failed the first time CI ran the window tests headless, which is the new
  job in 0.18.0 doing its job on its first outing. It now asserts what
  `_fit_window` actually decides, which holds on any screen.

### Known
- On a screen shorter than about 890 pixels the window is capped at the
  screen and the bottom of the taller column cannot be reached, because
  there is no scrollbar. A 1366x768 laptop loses about 170 pixels. Tracked
  rather than patched: a canvas-based scroller was tried and removed, since
  the cards use wrapping labels whose height depends on their width, so
  sizing the scroller changed the wrapping, which changed the height, and
  the layout never settled. A hang in the main window is worse than the
  problem it fixes.

## [0.18.1] — 2026-08-18

### Fixed
- **The CI workflow I added in 0.18.0 was not valid YAML**, so it never ran.
  An unparseable workflow does not fail loudly: it shows up in the Actions
  list under its filename instead of its name, with no log, and everything it
  was meant to check silently does not happen. The window smoke check is now
  a file rather than a script inlined into the YAML, which is what broke it,
  and `tests/test_workflows.py` parses every workflow so this cannot ship
  again.
- **The browser extension's own test suite was broken by the 0.18.0 schema
  work.** `occurred_at` was removed as an unread duplicate of `timestamp`,
  which it is in the extension's source, but its test asserted it and both
  READMEs documented it. The test and the docs now say `timestamp`.

## [0.18.0] — 2026-08-18

Everything here came out of an external code review. All of it was live, and
the whole test suite was green over every one of them.

### Fixed
- **Filters did not reach `comments.json`.** `--reviewer` and `--no-resolved`
  dropped comments from the Markdown, and the JSON next to it still carried
  every excluded discussion in full, message by message. The response letter,
  `comments.jsonl` and the per-reviewer reports had the same hole, and
  `summary` counted threads and reviewers nobody had asked to see. A reply on
  a filtered-out thread could also come back as new feedback in
  `whats-new.md`. Everything downstream of the filters now sees only the
  threads that survived them, which is what the browser extension has always
  done.
- **Stopping an export said "Nothing was written" when something had been.**
  The cancel checks inside the annotated-LaTeX and PDF steps fire after the
  comments are already on disk. Both the window and the command line now name
  what landed. (The core files cannot be split from each other: there is no
  cancellation point between them.)
- **Stale comment anchors could carry an offset past the end of the file.**
  `--include-source` promises those offsets index into `source/`, and one
  past the end slices to nothing, so the context read as though there were
  none. The offset is now clamped, as the line and column already were.
- **The remembered session cookie was saved world-readable.** `config.json`
  was written 0644 inside a 0755 folder, so any other account on the machine
  could read a live Overleaf session. Now 0600 in a 0700 folder, where the
  platform supports it.

### Changed
- **The two exports really do share schema 1.3 now.** Both declared it while
  emitting different JSON. The extension was missing the `comment_short_ids`
  and `change_short_ids` its own agent brief promised, and carried an
  `occurred_at` that duplicated `timestamp` and nothing read. Python was
  missing `created_at` and `last_activity_at`. Fixed on both sides.

  `tests/test_schema_parity.py` now runs the extension's real core in node and
  Python's real export over one shared fixture and compares the shapes, so a
  future divergence fails CI. The two remaining differences are listed in the
  test with reasons: `enclosing_float` needs float detection the extension
  does not have, and `report_language` has no meaning in Python.
- Extension version 1.1.0, since its JSON output changed.

### Added
- **CI runs the window tests.** All 16 skip themselves unless `OCE_GUI_TESTS`
  is set, and nothing ever set it, so the interface most people actually use
  was never exercised automatically. A new job runs them on Linux under xvfb
  and on macOS, plus a check that the window comes up at a sane size.

## [0.17.0] — 2026-08-18

### Added
- **`whats-new.md`, what changed since your last export.** Reviews arrive in
  waves, and the second export of a paper is mostly comments you read last
  week. This lists only what moved: new comments, threads that picked up
  replies with just the new replies quoted, comments somebody edited after you
  read them with both versions shown, what was resolved, what was reopened,
  what is gone, and new tracked changes.

  Nothing needs turning on. The previous export is already in the folder and is
  read before this run overwrites it. `--since PATH` compares against a
  different export instead, and `--no-since` skips it.

  The same lists are in `comments.json` under `since` as short ids, and
  `agents.md` explains them, so an assistant can be asked to work through only
  the new feedback.

  The comparison is done on thread ids, never short ids. Short ids are assigned
  in file then line order, so one new comment near the top of a paper shifts
  every id below it, and a diff keyed on them would report a whole paper as
  new on every run.

  Where the filters differ from the previous run, deletions are not reported,
  since a comment hidden by `--no-resolved` has not gone anywhere.

### Changed
- The window's Done line now also says what changed since the last export.
- The roadmap said mapping comments to PDF pages was not planned, which
  `--pdf` has done since 0.10. Removed, and `--pdf` added to what is shipped.

## [0.16.3] — 2026-08-18

### Changed
- **Shorter hints.** Every line under a field said in two or three lines what
  fits in one. The window is 165px narrower for it, and reads faster. The two
  facts worth keeping are still there, said briefly: reading Chrome's cookies
  does not work on Windows, and tracked changes on a self-hosted Overleaf need
  Server Pro.
- The link field is wide enough for a project link, which is the longest thing
  anyone types into this window.

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
