"""Build AppIcon.icns from one of the SVGs in packaging/icons.

    python3 packaging/make_icns.py [design-name]

Each size is rendered from the vector rather than downscaled from one large
PNG, so the 16 and 32 pixel versions stay crisp instead of turning to mush.
"""
import pathlib
import subprocess
import sys

import pymupdf

HERE = pathlib.Path(__file__).resolve().parent
DESIGN = sys.argv[1] if len(sys.argv) > 1 else "2-highlight"
SRC = HERE / "icons" / f"{DESIGN}.svg"
if not SRC.is_file():
    sys.exit(f"no such design: {SRC}\nhave: "
             + ", ".join(sorted(p.stem for p in (HERE / 'icons').glob('*.svg'))))

# What iconutil expects. Each logical size also needs a doubled retina copy.
SIZES = [16, 32, 128, 256, 512]

iconset = HERE / "AppIcon.iconset"
for old in iconset.glob("*.png"):
    old.unlink()
iconset.mkdir(exist_ok=True)

for size in SIZES:
    for scale, suffix in ((1, ""), (2, "@2x")):
        px = size * scale
        doc = pymupdf.open(SRC)
        pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(px / 1024, px / 1024), alpha=True)
        pix.save(iconset / f"icon_{size}x{size}{suffix}.png")

out = HERE / "AppIcon.icns"
subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)], check=True)
print(f"built {out.name} from {DESIGN} "
      f"({len(list(iconset.glob('*.png')))} sizes, {out.stat().st_size // 1024} KB)")
