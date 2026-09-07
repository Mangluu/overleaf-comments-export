"""The page you can send to somebody.

Its whole reason to exist is that it opens anywhere with nothing installed, so
the things worth testing are that it is self-contained and that it cannot be
broken by the contents of a comment.
"""

from __future__ import annotations

import json
import re

from overleaf_comments_export.viewer import render_viewer


def payload(**over):
    base = {
        "project": {"id": "p1", "title": "A paper"},
        "pulled_at": "2026-09-06T10:00:00+00:00",
        "summary": {"thread_count": 1},
        "threads": {"t1": {"resolved": False, "messages": [
            {"id": "m1", "content": "Break this up.",
             "timestamp": "2026-08-01T10:00:00+00:00",
             "user": {"name": "Bakhtawar Khan"}}]}},
        "comments": [{"short_id": "C001", "thread_id": "t1",
                      "pathname": "main.tex", "line": 12,
                      "nearest_heading": "Method", "anchored_text": "this bit",
                      "enclosing_float": None}],
        "tracked_changes": [],
    }
    base.update(over)
    return base


def test_nothing_is_fetched_from_anywhere():
    """It has to work on a laptop with no internet, from a USB stick."""
    page = render_viewer(payload())
    assert "<script src" not in page
    assert "<link" not in page
    assert "@import" not in page
    assert "src=" not in page
    # The one external address is a link to the project, which nothing loads.
    externals = re.findall(r'https?://[^"\s)]+', page)
    assert all("github.com/Mangluu" in u for u in externals), externals


def test_the_comment_is_actually_in_the_page():
    page = render_viewer(payload())
    assert "C001" in page and "Break this up." in page
    assert "Bakhtawar Khan" in page


def test_a_comment_cannot_close_the_script_block():
    """A comment really can contain </script>, and if it ends the block the
    page stops working and shows raw data instead."""
    p = payload()
    p["threads"]["t1"]["messages"][0]["content"] = "use </script> carefully <b>x</b>"
    page = render_viewer(p)
    body = page.split("const DATA = ", 1)[1]
    assert "</script>" not in body.split("</script>", 1)[0] or True
    # The sequence must not appear unescaped anywhere in the data blob.
    blob = body.split(";\n", 1)[0]
    assert "</" not in blob, "a comment could end the script block"


def test_a_title_with_html_in_it_is_escaped():
    page = render_viewer(payload(project={"id": "p", "title": "<b>bold</b> paper"}))
    assert "<b>bold</b> paper</title>" not in page
    assert "&lt;b&gt;bold" in page


def test_the_data_is_valid_json():
    page = render_viewer(payload())
    blob = page.split("const DATA = ", 1)[1].split(";\nconst list", 1)[0]
    data = json.loads(blob.replace("<\\/", "</"))
    assert data["comments"][0]["id"] == "C001"


def test_it_carries_only_what_it_draws():
    """The full payload is a couple of hundred kilobytes of offsets and
    context that nothing on screen uses, and this file gets emailed."""
    p = payload()
    p["comments"][0]["context"] = {"before": "x" * 5000, "after": "y" * 5000}
    p["comments"][0]["offset"] = 12345
    page = render_viewer(p)
    assert "x" * 5000 not in page
    assert "12345" not in page


def test_an_empty_project_still_produces_a_page():
    page = render_viewer(payload(comments=[], threads={}))
    assert "<html" in page and "</html>" in page
    assert "0 comments" in page


def test_resolved_state_reaches_the_page():
    p = payload()
    p["threads"]["t1"]["resolved"] = True
    blob = render_viewer(p).split("const DATA = ", 1)[1].split(";\nconst list", 1)[0]
    assert json.loads(blob.replace("<\\/", "</"))["comments"][0]["resolved"] is True
