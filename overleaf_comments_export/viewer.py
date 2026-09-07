"""One HTML file a co-author can open.

Markdown is fine if you have an editor that renders it. A spreadsheet is fine
if the person opens spreadsheets. Neither is much use for the supervisor who
wants to see what their student did with the feedback, so this is the output
you can attach to an email: one file, no installation, no internet.

Everything is inlined. No stylesheet, no script tag, no font, no image
request. It opens from a USB stick on a machine that has never heard of this
project, and it must, because that is the entire point of it.
"""

from __future__ import annotations

import html
import json
from typing import Any

from . import __version__


def _trim(payload: dict[str, Any]) -> dict[str, Any]:
    """Only what the page draws.

    The whole export is a couple of hundred kilobytes of offsets and context
    windows that nothing on screen uses, and this file gets emailed.
    """
    threads = payload.get("threads") or {}
    comments = []
    for c in payload.get("comments") or []:
        thread = threads.get(c.get("thread_id")) or {}
        messages = [m for m in (thread.get("messages") or []) if isinstance(m, dict)]
        fl = c.get("enclosing_float") or None
        comments.append({
            "id": c.get("short_id") or "",
            "file": c.get("pathname") or "",
            "line": c.get("line") or 0,
            "section": c.get("nearest_heading") or "",
            "float": (f"{str(fl.get('kind') or '').capitalize()} {fl['number']}"
                      if fl and fl.get("number") else
                      (f"{str(fl.get('kind') or '').capitalize()}" if fl else "")),
            "on": c.get("anchored_text") or "",
            "resolved": bool(thread.get("resolved")),
            "messages": [{
                "who": (m.get("user") or {}).get("name")
                       or (m.get("user") or {}).get("email") or "someone",
                "when": (m.get("timestamp") or "")[:16].replace("T", " "),
                "text": m.get("content") or "",
            } for m in messages],
        })
    return {
        "title": (payload.get("project") or {}).get("title") or "",
        "pulled": (payload.get("pulled_at") or "")[:16].replace("T", " "),
        "counts": payload.get("summary") or {},
        "comments": comments,
    }


# Kept as one string rather than a separate file, because a template that
# lives beside the module is one more thing to lose when the package is
# installed as a wheel.
_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Comments — {title}</title>
<style>
  :root {{
    --paper:#f7f5f0; --ink:#1c1b18; --hint:#6e6a61; --rule:#e3dfd5;
    --card:#fff; --green:#2e7d4f; --soft:#e8f1ea;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --paper:#141311; --ink:#ede9e0; --hint:#9c968b; --rule:#2e2a24;
             --card:#232019; --green:#5fb98a; --soft:#1e2a22; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--paper); color:var(--ink);
    font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif; }}
  header {{ padding:28px 22px 14px; max-width:900px; margin:0 auto; }}
  h1 {{ margin:0 0 4px; font-size:23px; }}
  .meta {{ color:var(--hint); font-size:13px; }}
  .controls {{ position:sticky; top:0; z-index:2; background:var(--paper);
    border-bottom:1px solid var(--rule); padding:10px 22px; }}
  .inner {{ max-width:900px; margin:0 auto; display:flex; gap:8px; flex-wrap:wrap; }}
  input[type=search], select {{ font:inherit; font-size:13px; padding:7px 10px;
    border:1px solid var(--rule); border-radius:9px; background:var(--card);
    color:var(--ink); }}
  input[type=search] {{ flex:1; min-width:180px; }}
  main {{ max-width:900px; margin:0 auto; padding:16px 22px 60px; }}
  .c {{ background:var(--card); border:1px solid var(--rule); border-radius:12px;
    padding:14px 16px; margin:0 0 10px; }}
  .c.done {{ opacity:.62; }}
  .top {{ display:flex; gap:8px; align-items:baseline; flex-wrap:wrap;
    font-size:12px; color:var(--hint); }}
  .id {{ font-weight:700; color:var(--green); font-size:13px; }}
  .tag {{ background:var(--soft); color:var(--green); border-radius:20px;
    padding:1px 9px; font-size:11px; font-weight:600; }}
  blockquote {{ margin:9px 0; padding:7px 12px; border-left:3px solid var(--rule);
    color:var(--hint); font-size:13px; }}
  .msg {{ margin-top:9px; }}
  .msg + .msg {{ border-top:1px dashed var(--rule); padding-top:9px; }}
  .who {{ font-weight:650; font-size:13px; }}
  .when {{ color:var(--hint); font-size:12px; }}
  .text {{ white-space:pre-wrap; margin-top:2px; }}
  .reply {{ margin-left:16px; border-left:2px solid var(--rule); padding-left:11px; }}
  .none {{ color:var(--hint); text-align:center; padding:40px 0; }}
  footer {{ max-width:900px; margin:0 auto; padding:0 22px 40px;
    color:var(--hint); font-size:12px; }}
  a {{ color:var(--green); }}
</style></head><body>
<header><h1>{title}</h1>
<p class="meta">{count} comments{pulled}</p></header>
<div class="controls"><div class="inner">
  <input type="search" id="q" placeholder="Search comments, people, files">
  <select id="file"><option value="">Every file</option></select>
  <select id="who"><option value="">Everyone</option></select>
  <select id="state">
    <option value="open">Still open</option>
    <option value="">Open and resolved</option>
    <option value="done">Resolved only</option>
  </select>
</div></div>
<main id="list"></main>
<footer>Made by <a href="https://github.com/Mangluu/overleaf-comments-export">overleaf-comments-export</a> {version}.
This file works offline and contains no tracking.</footer>
<script>
const DATA = {data};
const list = document.getElementById("list");
const q = document.getElementById("q");
const fileSel = document.getElementById("file");
const whoSel = document.getElementById("who");
const stateSel = document.getElementById("state");

for (const f of [...new Set(DATA.comments.map(c => c.file))].sort()) {{
  fileSel.append(new Option(f, f));
}}
const people = new Set();
for (const c of DATA.comments) for (const m of c.messages) people.add(m.who);
for (const p of [...people].sort()) whoSel.append(new Option(p, p));

const esc = s => String(s).replace(/[&<>]/g, ch => ({{"&":"&amp;","<":"&lt;",">":"&gt;"}})[ch]);

function draw() {{
  const term = q.value.trim().toLowerCase();
  const file = fileSel.value, who = whoSel.value, state = stateSel.value;
  const shown = DATA.comments.filter(c => {{
    if (file && c.file !== file) return false;
    if (state === "open" && c.resolved) return false;
    if (state === "done" && !c.resolved) return false;
    if (who && !c.messages.some(m => m.who === who)) return false;
    if (!term) return true;
    const hay = (c.id + " " + c.file + " " + c.section + " " + c.on + " "
      + c.messages.map(m => m.who + " " + m.text).join(" ")).toLowerCase();
    return hay.includes(term);
  }});
  list.innerHTML = shown.length ? shown.map(c => `
    <article class="c ${{c.resolved ? "done" : ""}}">
      <div class="top">
        <span class="id">${{esc(c.id)}}</span>
        <span>${{esc(c.file)}}${{c.line ? " line " + c.line : ""}}</span>
        ${{c.section ? `<span>§ ${{esc(c.section)}}</span>` : ""}}
        ${{c.float ? `<span class="tag">${{esc(c.float)}}</span>` : ""}}
        ${{c.resolved ? `<span class="tag">Resolved</span>` : ""}}
      </div>
      ${{c.on ? `<blockquote>${{esc(c.on)}}</blockquote>` : ""}}
      ${{c.messages.map((m, i) => `
        <div class="msg ${{i ? "reply" : ""}}">
          <span class="who">${{esc(m.who)}}</span>
          <span class="when">${{esc(m.when)}}</span>
          <div class="text">${{esc(m.text)}}</div>
        </div>`).join("")}}
    </article>`).join("")
    : `<p class="none">Nothing matches that.</p>`;
}}

for (const el of [q, fileSel, whoSel, stateSel]) {{
  el.addEventListener("input", draw);
  el.addEventListener("change", draw);
}}
draw();
</script></body></html>
"""


def render_viewer(payload: dict[str, Any]) -> str:
    """The whole viewer, as one self-contained page."""
    data = _trim(payload)
    return _PAGE.format(
        title=html.escape(data["title"] or "Overleaf comments"),
        count=len(data["comments"]),
        pulled=f", pulled {html.escape(data['pulled'])}" if data["pulled"] else "",
        version=html.escape(__version__),
        # </script> inside the data would end the block early, so the one
        # sequence that can escape a script tag is broken up.
        data=json.dumps(data, ensure_ascii=False).replace("</", "<\\/"),
    )
