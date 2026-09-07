#!/bin/bash
# Fit screenshots to the Chrome Web Store's 1280x800.
#
#   bash chrome-store/make-screenshots.sh shot1.png shot2.png ...
#
# Scales each image down until it fits *inside* 1280x800, then centres it on a
# background. It never crops.
#
# The previous version did crop, which is how the published listing lost the
# top and bottom of the popup. `sips --resampleHeightWidthMax 1280` sets the
# LARGER side to 1280, so a tall popup became 1280 tall, and `sips -p 800 1280`
# then cut 480 pixels off it rather than shrinking it. Both dimensions have to
# be considered together.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/screenshots"
mkdir -p "$OUT"
W=1280
H=800
BG="1c1b18"          # the same ink as the window, so the margins read as design

n=0
for src in "$@"; do
    n=$((n + 1))
    dst="$OUT/screenshot-$n.png"
    cp "$src" "$dst"

    sw=$(sips -g pixelWidth  "$dst" | awk '/pixelWidth/{print $2}')
    sh=$(sips -g pixelHeight "$dst" | awk '/pixelHeight/{print $2}')

    # Whichever side runs out of room first decides the scale, so the whole
    # image survives. Never scaled up: enlarging a screenshot looks soft.
    read -r nw nh <<EOF
$(python3 -c "
sw, sh = $sw, $sh
scale = min($W / sw, $H / sh, 1.0)
print(max(1, round(sw * scale)), max(1, round(sh * scale)))")
EOF

    sips -z "$nh" "$nw" "$dst" >/dev/null
    sips -p "$H" "$W" --padColor "$BG" "$dst" >/dev/null

    got=$(sips -g pixelWidth -g pixelHeight "$dst" | awk '/pixel/{printf "%s ", $2}')
    echo "  screenshot-$n.png  <- $(basename "$src")  ${sw}x${sh} -> ${nw}x${nh}, padded to ${got% }"
done
echo
echo "Wrote $n file(s) to $OUT"
echo "Upload them best-first: the Overleaf editor with the popup open should be number 1."
