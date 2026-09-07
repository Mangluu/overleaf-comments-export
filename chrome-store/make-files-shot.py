"""Render the second store screenshot, the files an export leaves behind.

The first screenshot shows the popup. This one answers the next question a
shopper has, which is what they actually get. It reads a real export folder,
so the names and sizes are whatever the extension really wrote, not a mockup.

    python3 chrome-store/make-files-shot.py "~/Downloads/overleaf-comments/Paper/2026-...Z"

Then photograph it at 1280x800, the size the store asks for:

    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless \
      --window-size=1280,800 --screenshot=out.png file:///...preview-files.html
"""
import html
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
folder = pathlib.Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else None
if not folder or not folder.is_dir():
    sys.exit("give me the path to an export folder")

# What each file is for, in the order a person meets them. Anything the export
# writes that is not listed still shows, just without a line of explanation.
BLURB = {
    ".md": "Every comment, grouped by file and section, ready to read",
    ".json": "The same data, structured, for scripts and other tools",
    ".jsonl": "One comment per line, for streaming into a pipeline",
    ".xlsx": "Three sheets, comments and replies and tracked changes",
    "response-letter.md": "A reply template with every point already listed",
    "agents.md": "A brief that tells an AI assistant how to read the rest",
}
# The comment data leads. The two written-for-you extras come after it,
# because they are the bonus, not the reason anyone installs this.
ORDER = [".md", ".json", ".jsonl", ".xlsx"]
LAST = ["response-letter.md", "agents.md"]


def blurb(p):
    return BLURB.get(p.name, BLURB.get(p.suffix, ""))


def size(n):
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1048576:.1f} MB"


files = sorted(
    (p for p in folder.iterdir() if p.is_file() and not p.name.startswith(".")),
    key=lambda p: (
        LAST.index(p.name) + 1 if p.name in LAST else 0,
        ORDER.index(p.suffix) if p.suffix in ORDER else 9,
        p.name,
    ),
)

rows = "\n".join(
    f"""<li>
      <span class="ext">{html.escape(p.suffix.lstrip('.').upper() or 'FILE')}</span>
      <span class="meta"><strong>{html.escape(p.name)}</strong>
        <small>{html.escape(blurb(p))}</small></span>
      <span class="size">{size(p.stat().st_size)}</span>
    </li>"""
    for p in files
)

page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Export output</title><style>
  html, body {{ width: 1280px; height: 800px; margin: 0; overflow: hidden; }}
  body {{
    box-sizing: border-box; padding: 0 96px;
    display: flex; flex-direction: column; justify-content: center;
    background: radial-gradient(circle at 18% 12%, #26302a, #14140f 62%);
    color: #f2efe6;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }}
  h2 {{ margin: 0 0 10px; font-size: 40px; font-weight: 650; letter-spacing: -0.5px; }}
  .sub {{ margin: 0 0 38px; font-size: 19px; color: #9d998e; }}
  ul {{ margin: 0; padding: 0; list-style: none; }}
  li {{
    display: flex; align-items: center; gap: 22px;
    padding: 17px 24px; margin-bottom: 12px;
    border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 14px;
    background: rgba(255, 255, 255, 0.035);
  }}
  .ext {{
    flex: 0 0 76px; padding: 7px 0; border-radius: 8px;
    background: #2f7d4f; color: #fff; text-align: center;
    font-size: 12px; font-weight: 700; letter-spacing: 0.6px;
  }}
  .meta {{ flex: 1; }}
  .meta strong {{ display: block; font-size: 19px; font-weight: 620; }}
  .meta small {{ display: block; margin-top: 3px; font-size: 15px; color: #9d998e; }}
  .size {{ flex: 0 0 auto; font-size: 15px; color: #7e7a71; font-variant-numeric: tabular-nums; }}
</style></head><body>
  <h2>One click, and this is what you get.</h2>
  <p class="sub">Saved straight to your downloads folder. Nothing is uploaded anywhere.</p>
  <ul>
{rows}
  </ul>
</body></html>"""

target = ROOT / "browser-extension" / "preview-files.html"
target.write_text(page, encoding="utf-8")
print(f"wrote {target.relative_to(ROOT)} - {len(files)} files from {folder.name}")
