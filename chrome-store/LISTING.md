# Chrome Web Store listing

Everything below is the exact text to paste into each field. Nothing here has
been submitted. Build the upload file with `bash chrome-store/build-zip.sh`,
which writes `chrome-store/extension.zip`.

Developer account: **shivangzephyr@gmail.com**
One-time registration fee: **5 USD**, paid once for the account, not per item.
Console: https://chrome.google.com/webstore/devconsole

---

## Package

Upload `chrome-store/extension.zip` (about 28 KB). It contains only what the
extension runs: manifest, popup, `src/`, `icons/`, `_locales/`, `assets/`.
Tests, `package.json` and the README are deliberately left out — reviewers
read what you ship, and shipping less means less to explain.

---

## Graphic assets

### Store icon — 128 x 128

Upload `chrome-store/store-icon-128.png`.

Google's image guidelines are specific here and the obvious icon fails them:
the canvas is 128x128 but **the artwork must be 96x96, with 16 pixels of
transparent padding on every side**. An icon that fills the canvas edge to
edge is rejected, because the store adds its own framing around it.

This file is measured to that spec: 96x96 of artwork, 16 pixels of padding on
each of the four sides, PNG with an alpha channel. Rebuild it with

```bash
.venv/bin/python packaging/make_store_icon.py
```

which also refreshes the 128 pixel icon inside the extension, since the same
rule applies to the one in the ZIP.

The 16, 32 and 48 pixel icons are toolbar icons and keep tighter padding, as
at those sizes every pixel counts.

---

## Store listing tab

### Item name

```
Overleaf Comments Export
```

### Summary

Shown under the name in search results. 132 characters maximum; this is 109.

```
Export the review comments and tracked changes from your Overleaf project to Markdown and JSON, in one click.
```

### Description

```
Open your paper in Overleaf. Click this extension's icon in the toolbar. Tick the files you want, then press Export current project. Everything is saved straight to your Downloads folder. That is the whole thing: no account, no setup, no copying and pasting.

Overleaf keeps review comments inside the editor. They are not in the source download and they are not in the Git sync, so the only way to work through feedback from co-authors and supervisors has been to scroll the document and handle them one at a time.

WHAT YOU GET

• Markdown, grouped by file and section, with every thread and its replies, and a short stable id on each comment
• A spreadsheet, with the comments, their replies and the tracked changes on three sheets, so you can sort by file, filter to one reviewer and tick things off
• JSON and JSONL, the same data structured, for anything else you want to do with it
• A response letter, pre-filled with every open comment and a blank space under each for your answer
• agents.md, a brief that tells an AI assistant how to read the rest, so you can say "draft a reply to C014" and it knows which passage that is

Tracked changes come through as well, as insertions and deletions with the surrounding text.

WHAT CHANGED SINCE LAST TIME

Reviews arrive in waves. Export the same paper again and you also get whats-new.md, listing only what moved: comments that are new, threads that picked up replies, comments somebody edited after you read them, what was resolved, what was reopened, and what is gone.

PAPERS SPLIT ACROSS FILES

Most real papers are. The project is read in the order LaTeX reads it, following \input and \include from the root document, so a comment gets the section it is actually under even when the \section is in main.tex and the prose is somewhere else. Figure and table numbers run through the whole paper rather than restarting in every file.

NOTHING LEAVES YOUR COMPUTER

There is no backend, no account, no analytics and no telemetry. It works inside the Overleaf tab you already have open and writes the files straight to your downloads folder.

It never reads or stores your session cookie. It uses the session already in the tab, which is why it needs no password and no permanent access to any site.

WHAT IT ASKS FOR, AND WHY

activeTab, so it can act on the Overleaf tab you clicked it on, and no other.
scripting, so it can read the project through the same requests the editor itself makes.
downloads, so it can save the exported files to your computer.

It requests no permanent host permissions at all.

THERE IS ALSO A COMMAND LINE VERSION

The same project ships a Python tool that does more, including writing the comments into your compiled PDF as highlights and producing a single self-contained web page you can email to a co-author.

    pip install "overleaf-comments-export[gui,pdf]"

OPEN SOURCE

MIT licensed. The whole thing is readable at
https://github.com/Mangluu/overleaf-comments-export

The interface is available in English and Chinese.
```

### Category

```
Workflow & Planning
```

### Language

```
English (United States)
```

---

## Privacy tab

### Single purpose

```
Exports the review comments, replies and tracked changes from the Overleaf project in the currently open tab, and saves them to the user's computer as Markdown and JSON files.
```

### Permission justifications

**activeTab**

```
The export runs against the Overleaf project the user clicked the extension on. activeTab grants access to that one tab, and only after that click, which is exactly the scope needed and nothing wider. No permanent host permission is requested.
```

**scripting**

```
The project's comments, tracked changes and document text are read through the same endpoints the Overleaf editor itself uses. Those must be called from the page's own origin, with the session already present in the tab. A script is injected into the active tab to make those requests and return the result to the extension.
```

**downloads**

```
The exported Markdown, JSON, JSONL and response-letter files are saved to the user's computer. The downloads permission is what writes them.
```

**Remote code**

```
No remote code is used. All JavaScript is included in the package. Nothing is fetched or evaluated at runtime.
```

### Data usage

Tick **Website content** only, and nothing else. When asked what it is used for:

```
The project's comments, replies, tracked changes and document text are read from the active Overleaf tab and written to files on the user's own computer. Nothing is transmitted anywhere, stored remotely, or shared with any third party.
```

Then tick all three certifications:

- I do not sell or transfer user data to third parties, outside of the approved use cases
- I do not use or transfer user data for purposes that are unrelated to my item's single purpose
- I do not use or transfer user data to determine creditworthiness or for lending purposes

### Privacy policy URL

```
https://github.com/Mangluu/overleaf-comments-export/blob/main/PRIVACY.md
```

---

## Screenshots

At least one is required. Up to five are allowed. Either **1280x800** or
**640x400**, PNG or JPEG. These have to be taken by hand because they must
show the extension actually running.

Take them on a real project with real comments. A project with a handful of
threads from more than one person looks far more convincing than an empty one.

1. **The popup open over an Overleaf project.** The Overleaf editor behind,
   with the review panel visible so the comments are on screen, and the
   extension popup open in front showing the options. This is the one that
   sells it, so make it the first.
2. **The popup after a successful export**, showing the summary line with the
   counts.
3. **The exported Markdown open in an editor**, showing comments grouped by
   section with their `C001` ids. This shows what you actually get.
4. **Optional: the downloads folder** with the exported files in it.
5. **Optional: the response letter**, showing the blank slots under each
   comment.

How to get the size exactly right on a Mac: take the shot with Shift-Command-4,
then

```bash
sips -z 800 1280 shot.png --out screenshot-1.png
```

That forces the dimensions. Crop rather than stretch if the aspect is wrong,
since a squashed screenshot looks careless.

Google prefers screenshots without added text overlays, so do not annotate
them.

---

## Optional promotional images

Not required, and the listing works without them. If you want them later:

- Small promo tile: 440x280
- Marquee promo tile: 1400x560

`packaging/icons/2-highlight.svg` is the source for the icon if you want to
build a tile from it.

---

## After you submit

The first review usually takes a few days and can take longer. Reviewers look
hardest at the three permissions, which is why each justification above says
what it is for in one plain sentence.

Two things to expect:

- A review can come back asking for clarification rather than rejecting. That
  is normal, and the answer is almost always to restate the single purpose.
- The listing is per-item, but the 5 USD fee is per-account and one-time, so
  publishing updates later costs nothing.

When it is published, the README and the in-app message should point people at
the store listing rather than at loading an unpacked folder.
