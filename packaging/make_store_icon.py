"""Build the Chrome Web Store icon, which has its own rules.

The store wants a 128x128 PNG whose artwork is only 96x96, with 16 pixels of
transparent padding on every side. Filling the canvas edge to edge fails the
image guidelines, and the store UI adds its own framing that would collide
with ours.

The toolbar icons are the opposite case: at 16 and 32 pixels they need every
pixel they can get, so those keep the tighter padding and are built by
make_icons.py.
"""
import pathlib
import re

import pymupdf

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / "icons" / "2-highlight.svg"

# The design draws its rounded square at x=92 width=840 in a 1024 box, which
# is 105 of 128 once scaled. The store wants 96 of 128, so the shape is
# redrawn smaller and the padding grows to the 16 per side it asks for.
SIDE = 1024 * 96 / 128          # 768
INSET = (1024 - SIDE) / 2       # 128
RADIUS = 196 * SIDE / 840       # keep the corner curve proportional

svg = SRC.read_text(encoding="utf-8")
svg = re.sub(
    r'<rect x="92" y="92" width="840" height="840" rx="196"',
    f'<rect x="{INSET:.0f}" y="{INSET:.0f}" width="{SIDE:.0f}" '
    f'height="{SIDE:.0f}" rx="{RADIUS:.0f}"',
    svg, count=1)

# Everything inside the square has to shrink and shift with it.
scale = SIDE / 840
shift = INSET - 92 * scale
svg = svg.replace("</svg>", "</svg>")
inner_start = svg.index("/>", svg.index("<rect x=")) + 2
head, inner = svg[:inner_start], svg[inner_start:svg.rindex("</svg>")]
svg = (f'{head}<g transform="translate({shift:.1f} {shift:.1f}) '
       f'scale({scale:.5f})">{inner}</g></svg>')

out_svg = HERE / "icons" / "store-icon.svg"
out_svg.write_text(svg, encoding="utf-8")

doc = pymupdf.open(out_svg)
pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(128 / 1024, 128 / 1024), alpha=True)
for dest in (HERE.parent / "chrome-store" / "store-icon-128.png",
             HERE.parent / "browser-extension" / "icons" / "icon128.png"):
    dest.parent.mkdir(parents=True, exist_ok=True)
    pix.save(dest)
    print(f"wrote {dest.relative_to(HERE.parent)}")
