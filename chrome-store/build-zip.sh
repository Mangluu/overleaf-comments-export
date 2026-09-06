#!/bin/bash
# Build the upload zip for the Chrome Web Store.
#
#   bash chrome-store/build-zip.sh
#
# Only what the extension needs at runtime goes in. Tests, package.json and
# the README stay out: reviewers read what you ship, and shipping less means
# less to explain.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
OUT="$HERE/extension.zip"

rm -f "$OUT"
cd "$ROOT/browser-extension"
zip -r -q -X "$OUT" \
    manifest.json popup.html popup.css popup.js \
    src icons _locales \
    -x '*.DS_Store' '*/node_modules/*'
cd "$ROOT"
echo "Built $OUT ($(du -h "$OUT" | cut -f1))"
unzip -Z1 "$OUT" | sed "s/^/  /"
