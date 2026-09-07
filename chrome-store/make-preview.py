"""Render the popup outside Chrome, so it can be photographed whole.

The popup is 380 pixels wide and taller than Chrome will show, so in a real
window it scrolls and a screenshot always loses the top or the bottom. This
inlines the extension's own markup, stylesheet, script and icon into one file
that any browser can open at whatever height is needed.

Nothing is mocked. Only the browser APIs are stubbed, and the state is set to
the one worth photographing: a project found, some formats ticked.

    python3 chrome-store/make-preview.py [dark|light]
"""
import base64
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXT = ROOT / "browser-extension"
THEME = sys.argv[1] if len(sys.argv) > 1 else "dark"

html = (EXT / "popup.html").read_text(encoding="utf-8")
css = (EXT / "popup.css").read_text(encoding="utf-8")
js = (EXT / "popup.js").read_text(encoding="utf-8")
icon = base64.b64encode((EXT / "icons" / "icon128.png").read_bytes()).decode()

stub = """<script>
window.chrome = {
  runtime: { onMessage: { addListener() {} }, sendMessage: async () => ({}) },
  tabs: { query: async () => [{ id: 1, url: "https://www.overleaf.com/project/6a7a2841276c76c4bad70940" }] },
  scripting: { executeScript: async () => [{ result: null }] },
  downloads: { download: async () => 1 },
};
</script>
"""

out = html.replace("<head>", "<head>\n" + stub, 1)
out = out.replace('<link rel="stylesheet" href="popup.css">', f"<style>\n{css}\n</style>", 1)
out = out.replace('<script src="popup.js"></script>', f"<script>\n{js}\n</script>", 1)
out = out.replace('src="icons/icon128.png"', f'src="data:image/png;base64,{icon}"')

# The stylesheet follows the reader's theme. A screenshot has to pick one, so
# the choice is forced rather than left to whatever the machine is set to.
forced = ""
if THEME == "dark":
    forced = ("<style>:root{color-scheme:dark}"
              "@media (prefers-color-scheme: light){"
              + css.split("@media (prefers-color-scheme: dark) {", 1)[-1].split("}\n", 1)[0]
              + "}}</style>")

out = out.replace("</body>", """<script>
setTimeout(() => {
  const set = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };
  set("page-state", "Overleaf project detected");
  set("page-detail", "Does Touch Make Interaction Easier?");
  document.getElementById("page-card")?.classList.add("ok");
  document.getElementById("page-indicator")?.classList.add("ok");
  for (const id of ["options", "formats", "export"]) {
    const el = document.getElementById(id); if (el) el.disabled = false;
  }
  for (const id of ["format-md", "format-json", "format-xlsx"]) {
    const box = document.getElementById(id); if (box) box.checked = true;
  }
  // Neither belongs in a still: one only shows mid-export, the other after.
  for (const id of ["stop", "copy", "progress"]) {
    const el = document.getElementById(id); if (el) el.hidden = true;
  }
}, 60);
</script></body>""", 1)

target = EXT / "preview.html"
target.write_text(out, encoding="utf-8")
print(f"wrote {target.relative_to(ROOT)} ({len(out) // 1024} KB, {THEME})")

# ---------------------------------------------------------------------------
# Store-screenshot frame.
#
#   python3 chrome-store/make-preview.py light frame
#
# Chrome Web Store screenshots are 1280x800. The popup is 380x752, so it fits
# upright with room to spare and needs no scaling, which keeps the text crisp.
# It sits on the left on the same ink the padding uses, with the four steps
# beside it, so the picture answers "what do I do with this" on its own.
if "frame" in sys.argv:
    caption = """
<style>
  html {
    width: 1280px; height: 800px; margin: 0; overflow: hidden;
    display: flex; align-items: center; justify-content: center; gap: 74px;
    background: radial-gradient(circle at 18% 12%, #26302a, #14140f 62%);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  body {
    flex: 0 0 auto; border-radius: 18px; overflow: hidden;
    box-shadow: 0 26px 70px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(255, 255, 255, 0.06);
  }
  .oce-caption { flex: 0 0 560px; color: #f2efe6; }
  .oce-caption h2 {
    margin: 0 0 26px; font-size: 40px; line-height: 1.15;
    font-weight: 650; letter-spacing: -0.5px;
  }
  .oce-caption ol { margin: 0; padding: 0; list-style: none; counter-reset: step; }
  .oce-caption li {
    counter-increment: step; position: relative; padding-left: 52px;
    margin-bottom: 20px; font-size: 21px; line-height: 1.35; color: #ded9cc;
  }
  .oce-caption li::before {
    content: counter(step); position: absolute; left: 0; top: -2px;
    width: 34px; height: 34px; border-radius: 50%;
    background: #2f7d4f; color: #fff;
    font-size: 17px; font-weight: 650;
    display: flex; align-items: center; justify-content: center;
  }
  .oce-caption p {
    margin: 30px 0 0; font-size: 17px; line-height: 1.5; color: #9d998e;
  }
</style>
<script>
addEventListener("load", () => {
  const aside = document.createElement("aside");
  aside.className = "oce-caption";
  aside.innerHTML = `
    <h2>Every comment on your paper,<br>saved to your computer.</h2>
    <ol>
      <li>Open your paper on Overleaf.</li>
      <li>Click this icon in the toolbar.</li>
      <li>Tick what you want to keep.</li>
      <li>Press Export current project.</li>
    </ol>
    <p>Markdown, JSON and a spreadsheet land in your downloads folder.
       Nothing is uploaded anywhere.</p>`;
  document.documentElement.appendChild(aside);
});
</script>
"""
    framed = out.replace("</body>", caption + "</body>", 1)
    shot = EXT / "preview-frame.html"
    shot.write_text(framed, encoding="utf-8")
    print(f"wrote {shot.relative_to(ROOT)} ({len(framed) // 1024} KB) - render at 1280x800")
