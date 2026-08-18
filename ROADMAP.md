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
- `commented.pdf` (`--pdf`), your paper as Overleaf builds it with every comment
  highlighted on the text it belongs to, needing no LaTeX on your machine
- The text of every commented file, so an assistant can read the paragraph (`--include-source`)
- A checklist of what is left to address, ticked from Overleaf's own resolved flag
- `--doctor`, which says what is wrong with a setup in plain words
- Figure and table detection, so a comment on a caption says which figure
- Downloadable apps for Windows and Linux, so Python is not needed
- A window written for people who do not use a terminal, with dark mode
- A read-only Chrome/Edge extension that exports the project in the current tab
  without reading or storing browser cookies
- `whats-new.md`, which says what changed since the previous export into the
  same folder, so a second wave of review does not mean rereading the first

## Next

Things I think are worth doing, roughly in order.

- **Resolving `\input` and `\include`** so a multi-file project gets the right
  section for every comment. Right now a comment in a file that is included
  from the main document is anchored correctly but attributed to the nearest
  heading inside that file alone. **help wanted**
- **Offline re-render from a saved `comments.json`**, so a folder you already
  exported stays usable when the API changes underneath it, and so you can try
  a different `--render-mode` without hitting Overleaf again.

## Later

- Deep links back to the right place in Overleaf
- A single-file interactive HTML viewer for co-authors who will never install
  anything

## Not planned

Saying no is part of a roadmap.

- **A downloadable Mac app.** There was one. macOS blocks apps it has not
  checked, signing costs money every year, and the right-click workaround was
  removed in macOS 15, so everybody who downloaded it hit a wall. On a Mac,
  `pip install` or the browser extension both work and neither is gated.
- **Writing back to Overleaf** — posting replies, marking threads resolved, or
  applying edits. This tool reads. Writing needs endpoints this project does
  not use, and it turns a safe utility into something that can damage your
  project.
- **Telemetry of any kind.** This tool handles your session cookie. It will
  never phone home. Downloads and issues are the only feedback it gets, which
  is exactly why filing an issue matters.
