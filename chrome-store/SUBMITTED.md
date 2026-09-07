# Submission record

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
