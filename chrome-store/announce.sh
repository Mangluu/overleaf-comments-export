#!/bin/bash
# Point everything at the published listing.
#
#   bash chrome-store/announce.sh https://chromewebstore.google.com/detail/...
#
# Until it is published the docs tell people to load an unpacked folder,
# which is a real barrier: it needs developer mode and it warns on every
# Chrome start. This replaces that with the store link everywhere it appears.
set -eu
URL="${1:?usage: announce.sh <store-url>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python3 - "$URL" <<'PY'
import pathlib, re, sys
url = sys.argv[1]

readme = pathlib.Path("README.md")
s = readme.read_text(encoding="utf-8")
s = s.replace(
    "Load [`browser-extension/`](browser-extension/) as an unpacked extension. The\n"
    "[extension guide](browser-extension/README.md) has the installation steps and\n"
    "explains its deliberately limited permissions.",
    f"Install it from the [Chrome Web Store]({url}). It works in Chrome, Edge,\n"
    "Brave and other Chromium browsers. The\n"
    "[extension guide](browser-extension/README.md) explains its deliberately\n"
    "limited permissions.")
readme.write_text(s, encoding="utf-8")

ext = pathlib.Path("browser-extension/README.md")
t = ext.read_text(encoding="utf-8")
if "chromewebstore" not in t:
    t = t.replace("# ", f"# ", 1)
    lines = t.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("#"):
            lines.insert(i + 1,
                         f"\nInstall from the [Chrome Web Store]({url}).\n")
            break
    ext.write_text("\n".join(lines), encoding="utf-8")

sub = pathlib.Path("chrome-store/SUBMITTED.md")
u = sub.read_text(encoding="utf-8")
u = u.replace("## When it is published", f"## Published\n\n{url}\n\n## When it is published")
sub.write_text(u, encoding="utf-8")
print(f"pointed the docs at {url}")
PY
grep -rn "chromewebstore" README.md browser-extension/README.md | sed 's/^/  /'
