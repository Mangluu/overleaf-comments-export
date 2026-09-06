#!/bin/bash
# Fit screenshots to the Chrome Web Store's 1280x800.
#
#   bash chrome-store/make-screenshots.sh shot1.png shot2.png ...
#
# Scales each image to fit inside 1280x800 and centres it on a background
# matching the app, rather than stretching it. A squashed screenshot looks
# careless, and the store rejects anything that is not exactly the right size.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/screenshots"
mkdir -p "$OUT"
W=1280
H=800
BG="1c1b18"          # the same ink as the window, so letterboxing reads as design

n=0
for src in "$@"; do
    n=$((n + 1))
    dst="$OUT/screenshot-$n.png"
    cp "$src" "$dst"
    # Fit inside the box without distorting, then pad out to exactly 1280x800.
    sips -Z $(( W > H ? W : H )) "$dst" >/dev/null 2>&1 || true
    sips --resampleHeightWidthMax 1280 "$dst" >/dev/null 2>&1
    sips -p $H $W --padColor "$BG" "$dst" >/dev/null 2>&1
    got=$(sips -g pixelWidth -g pixelHeight "$dst" | awk '/pixel/{printf "%s", $2" "}')
    echo "  screenshot-$n.png  <- $(basename "$src")   now ${got% }"
done
echo
echo "Wrote $n file(s) to $OUT"
echo "Upload them best-first: the Overleaf editor with the popup open should be number 1."
