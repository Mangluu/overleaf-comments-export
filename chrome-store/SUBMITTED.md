# Submission record

## Update 2, ready to upload

The store is still serving **1.1.0**. Everything from 1.2.0 to 1.7.0 goes up
in one upload, which is why the jump is large.

| | |
|---|---|
| extension version | 1.7.0 |
| replaces | 1.1.0, live since 2026-09-06 |
| package | chrome-store/extension.zip |
| package sha256 | `4d2b8323a4c84e1440ff766d76d14d3fb3ba22e3bee3e729dc606947e0e7a450` |
| package size | 43K |
| screenshots | `chrome-store/screenshots/screenshot-1.png`, `screenshot-2.png` |

What a reviewer will see as new since 1.1.0.

- Reads a paper split across several files the way LaTeX reads it, following
  `\input`, `\include` and `\subfile`
- Says where the export has got to, and can be stopped part way
- Writes a spreadsheet, on three sheets
- Writes one HTML page that can be sent to a co-author
- Reports what changed since the last export
- Copies the Markdown to the clipboard
- Says so plainly when nobody is signed in
- Filters by reviewer and by the file currently open
- Language picker, English first

No new permissions. The manifest asks for the same three it always has.

---

Submitted for review: **2026-09-06 13:39 EEST**
Developer account: shivangzephyr@gmail.com

| | |
|---|---|
| commit | `4eb9b1d73ab4b15bd33bdc44b5a7c7d140ef5f9c` |
| tag at submission | v0.22.1 |
| extension version | 1.1.0 |
| package | chrome-store/extension.zip |
| package sha256 | `138f3cf1fc1ab28b2af98eb20118b9d9e566c8c2186e0477cb88e99ff7ed0e79` |
| package size |  28K |
| store icon sha256 | `2e49b9e6513ca794ff0d95cefb7d3b19921562688504d1af06b39eea70335b51` |

Kept so that a review question weeks later can be answered against the exact
build the reviewer has, rather than whatever main has drifted to.

## If review comes back with questions

Rejections here are nearly always about one permission. The answers are
already written in `LISTING.md` under Permission justifications; the reply is
usually to restate the single purpose in the same plain words rather than to
change anything.

The three permissions and the one-line reason for each:

- **activeTab** — acts only on the Overleaf tab the user clicked the extension on
- **scripting** — the project is read through the endpoints the editor itself
  uses, which must be called from the page's own origin
- **downloads** — writes the exported files to the user's computer

No host permissions are requested at all, there is no remote code, and nothing
is transmitted anywhere.

## Published

https://chromewebstore.google.com/detail/overleaf-comments-export/nbbappjfcankkjnpbaopjhejgdagaglc

## When it is published

- [ ] Put the store URL in README.md, replacing the "load as an unpacked
      extension" instructions
- [ ] Same in browser-extension/README.md
- [ ] Add it to the PyPI description so the two halves point at each other
- [ ] Mention it in the next release notes
