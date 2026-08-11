# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added
- Unexpected crashes now print where to report them, with the version number.
- Issue templates, a contributing guide, and a roadmap.

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

[Unreleased]: https://github.com/Mangluu/overleaf-comments-export/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.3.0
[0.2.0]: https://github.com/Mangluu/overleaf-comments-export/releases/tag/v0.2.0
