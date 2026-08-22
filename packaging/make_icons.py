"""Six icon options. Same palette as the window, so the app and its icon agree."""
import pathlib, pymupdf

PAPER, INK, GREEN, DEEP, HINT = "#F7F5F0", "#1C1B18", "#2E7D4F", "#1B5E3A", "#6E6A61"
S = 1024
OUT = pathlib.Path("/tmp/icons"); OUT.mkdir(exist_ok=True)

def squircle(fill, inner=""):
    # macOS icons sit on a rounded square with a little breathing room.
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
<rect x="92" y="92" width="840" height="840" rx="196" fill="{fill}"/>
{inner}</svg>'''

def page(x, y, w, h, fold=90, fill=PAPER):
    return (f'<path d="M{x} {y} h{w-fold} l{fold} {fold} v{h-fold} a24 24 0 0 1 -24 24 '
            f'h{-(w-48)} a24 24 0 0 1 -24 -24 v{-(h-48)} a24 24 0 0 1 24 -24 z" fill="{fill}"/>'
            f'<path d="M{x+w-fold} {y} l{fold} {fold} h{-fold} z" fill="#D8D2C4"/>')

def lines(x, y, widths, gap=46, w=16, colour="#C9C3B4"):
    return "".join(f'<rect x="{x}" y="{y+i*gap}" width="{ww}" height="{w}" rx="{w//2}" fill="{colour}"/>'
                   for i, ww in enumerate(widths))

def bubble(x, y, w, h, fill=PAPER, tail=True):
    t = f'<path d="M{x+64} {y+h} l0 84 l88 -84 z" fill="{fill}"/>' if tail else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h//3}" fill="{fill}"/>{t}'

designs = {}

# 1. A page with a comment bubble over it. The literal reading of the tool.
designs["1-page-and-bubble"] = squircle(GREEN,
    page(232, 210, 430, 560) + lines(292, 330, [230, 300, 260, 300]) +
    bubble(470, 470, 340, 230) +
    lines(520, 540, [200, 240, 160], gap=44, w=18, colour=GREEN))

# 2. Highlighted text. What the commented PDF actually looks like.
designs["2-highlight"] = squircle(GREEN,
    page(272, 190, 480, 640) +
    lines(332, 300, [320, 380, 300]) +
    f'<rect x="332" y="450" width="380" height="52" rx="10" fill="#FFD966"/>' +
    lines(332, 466, [340], gap=0, w=18, colour=INK) +
    lines(332, 560, [300, 360, 250]))

# 3. A bubble leaving the page: the export itself.
designs["3-bubble-exported"] = squircle(GREEN,
    page(212, 250, 400, 520) + lines(266, 350, [200, 270, 230]) +
    bubble(500, 300, 330, 220, tail=False) +
    f'<path d="M600 640 q80 60 190 20" stroke="{PAPER}" stroke-width="22" fill="none" stroke-linecap="round"/>'
    f'<path d="M770 630 l38 30 l-46 26 z" fill="{PAPER}"/>' +
    lines(550, 365, [190, 230, 150], gap=44, w=18, colour=GREEN))

# 4. A conversation: comment and reply, which is what a thread is.
designs["4-thread"] = squircle(GREEN,
    bubble(200, 250, 470, 250) +
    lines(256, 320, [290, 350, 240], gap=46, w=20, colour=GREEN) +
    bubble(370, 570, 450, 220, fill="#CFE6D8", tail=False) +
    lines(424, 630, [270, 330], gap=46, w=20, colour=DEEP))

# 5. A checklist: the review, worked through.
def tick(x, y, s_, colour):
    return (f'<rect x="{x}" y="{y}" width="{s_}" height="{s_}" rx="{s_//4}" fill="{colour}"/>'
            f'<path d="M{x+s_*0.24} {y+s_*0.50} l{s_*0.17} {s_*0.19} l{s_*0.36} {-s_*0.38}" '
            f'stroke="{GREEN}" stroke-width="{s_*0.13}" fill="none" '
            f'stroke-linecap="round" stroke-linejoin="round"/>')

designs["5-checklist"] = squircle(GREEN,
    page(232, 180, 560, 664) +
    tick(300, 290, 96, PAPER) + lines(430, 320, [280], gap=0, w=26, colour="#C9C3B4") +
    tick(300, 452, 96, PAPER) + lines(430, 482, [330], gap=0, w=26, colour="#C9C3B4") +
    f'<rect x="300" y="614" width="96" height="96" rx="24" fill="none" '
    f'stroke="#C9C3B4" stroke-width="16"/>' +
    lines(430, 644, [250], gap=0, w=26, colour="#C9C3B4"))

# 6. Margin marks: how a supervisor actually leaves comments.
designs["6-margin-marks"] = squircle(GREEN,
    page(212, 180, 520, 664) +
    lines(266, 290, [300, 360, 320, 280, 350, 300], gap=62) +
    f'<rect x="560" y="276" width="120" height="120" rx="34" fill="{GREEN}"/>'
    f'<rect x="560" y="462" width="120" height="120" rx="34" fill="#8FC4A8"/>'
    f'<rect x="560" y="648" width="120" height="120" rx="34" fill="#CFE6D8"/>')

for name, svg in designs.items():
    p = OUT / f"{name}.svg"
    p.write_text(svg, encoding="utf-8")
    doc = pymupdf.open(p)
    doc[0].get_pixmap(matrix=pymupdf.Matrix(S / 1024, S / 1024), alpha=True).save(OUT / f"{name}.png")
print("generated:", ", ".join(sorted(designs)))
