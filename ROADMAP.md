# Roadmap

Rough, and deliberately so. Anything here can move if someone says they need
it — [say so in an issue](https://github.com/Mangluu/overleaf-comments-export/issues/new/choose)
and it moves up. Items marked **help wanted** are self-contained and a good
place to start if you would like to contribute.

## Shipped

- Comment threads, replies, and tracked changes → Markdown + JSON + JSONL
- Stable short IDs (`C001`, `T001`) so you can cite a comment to an AI
- Source context around every anchor, with stale-anchor relocation
- Section detection, including abstract and title
- Filters: open, resolved, tracked changes, by reviewer; per-reviewer reports
- Paste-your-own-cookie auth, so it works on every OS and browser
- Plain-English errors and automatic retries
- Response letter scaffold (`--response-letter`)
- Git friendly output that does not churn between runs (`--stable`)
- Comments embedded in the LaTeX, so the compiled PDF carries them (`--annotated-tex`)
- The text of every commented file, so an assistant can read the paragraph (`--include-source`)
- A checklist of what is left to address, ticked from Overleaf's own resolved flag
- Figure and table detection, so a comment on a caption says which figure
- Downloadable apps for macOS, Windows and Linux, so Python is not needed
- A window written for people who do not use a terminal, with dark mode
- A read-only Chrome/Edge extension that exports the project in the current tab
  without reading or storing browser cookies

## Next

Things I think are worth doing, roughly in order.

- **Diff two exports** (`--since`) — reviews arrive in waves. `--stable` already
  lets git show you this. `--since` would say it in words, without needing a
  repository.
- **`--doctor`** — one command that says whether your login works and what it
  can see, so "it doesn't work" becomes answerable without a conversation.

## Later

- Offline re-render from a saved `comments.json`, for when the API breaks
- Resolving `\input` and `\include` so multi-file projects get correct sections
- Deep links back to the right place in Overleaf
- A single-file interactive HTML viewer for co-authors who will never install
  anything

## Not planned

Saying no is part of a roadmap.

- **Writing back to Overleaf** — posting replies, marking threads resolved, or
  applying edits. This tool reads. Writing needs endpoints this project does
  not use, and it turns a safe utility into something that can damage your
  project.
- **Mapping comments to PDF page numbers** — it needs compile output that is
  not reachable from the endpoints this tool uses, and would break constantly.
- **Telemetry of any kind.** This tool handles your session cookie. It will
  never phone home. Downloads and issues are the only feedback it gets, which
  is exactly why filing an issue matters.
