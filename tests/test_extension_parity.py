"""The extension and the Python export must not drift apart.

Both write `schema_version`, and that number is a promise about the shape of
the output. Anything reading the folder, an assistant above all, is entitled to
find the same fields whichever tool produced it. Two shapes under one version
is the kind of breakage nobody notices until someone's script quietly reads the
wrong thing.

These tests read the extension's JavaScript as text. That is crude, and it is
the point: they cost nothing, they run in the existing suite, and they fail the
moment somebody edits one side without the other.

Every read names its encoding. The extension ships a Chinese interface, and on
Windows a read without one uses cp1252 and dies on the first Chinese character.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from overleaf_comments_export.export import SCHEMA_VERSION
from overleaf_comments_export.model import AnchoredComment, Message, SourceContext, Thread
from overleaf_comments_export.render import render_markdown

EXTENSION = Path(__file__).resolve().parent.parent / "browser-extension"
CORE = EXTENSION / "src" / "export-core.js"

pytestmark = pytest.mark.skipif(
    not CORE.exists(), reason="the browser extension is not part of this checkout"
)


def _python_front_matter() -> list[str]:
    """The keys the Python export actually writes, taken from real output."""
    thread = Thread(id="t1", messages=[Message(
        id="m1", content="Needs a citation.", timestamp_ms=1_700_000_000_000,
        user_id="u1", user_name="A. Reviewer")])
    comment = AnchoredComment(
        thread_id="t1", short_id="C001", doc_id="d1", pathname="main.tex",
        offset=0, anchored_text="a novel framework", line_no=1, col=1,
        nearest_heading="Method", stale=False,
        context=SourceContext(anchor="a novel framework"))
    text = render_markdown(
        project_title="Demo", project_id="a" * 24, threads={"t1": thread},
        anchored=[comment], orphan_threads=[], changes=[],
    )
    body = text.split("---")[1]
    return [line.split(":", 1)[0].strip() for line in body.strip().splitlines() if ":" in line]


def _extension_front_matter() -> list[str]:
    """The keys the extension writes, read out of its Markdown template."""
    source = CORE.read_text(encoding="utf-8")
    block = source.split("const lines = [", 1)[1].split('"---",', 2)[1]
    keys = []
    for line in block.splitlines():
        line = line.strip().strip(",")
        m = re.match(r'^[`"]([a-z_]+):', line)
        if m:
            keys.append(m.group(1))
    return keys


def test_both_declare_the_same_schema_version():
    declared = re.search(r'SCHEMA_VERSION\s*=\s*"([^"]+)"', CORE.read_text(encoding="utf-8"))
    assert declared, "the extension no longer declares a SCHEMA_VERSION"
    assert declared.group(1) == SCHEMA_VERSION, (
        f"the extension says schema {declared.group(1)} and Python says "
        f"{SCHEMA_VERSION}. Either bring the output back into line or give the "
        f"extension its own version marker."
    )


def test_the_markdown_front_matter_matches():
    python_keys = _python_front_matter()
    extension_keys = _extension_front_matter()
    assert extension_keys, "could not read the extension's front matter template"
    missing = [k for k in python_keys if k not in extension_keys]
    extra = [k for k in extension_keys if k not in python_keys]
    assert not missing and not extra, (
        f"the two exports promise the same schema and write different front "
        f"matter. Missing from the extension: {missing or 'nothing'}. Only in "
        f"the extension: {extra or 'nothing'}."
    )


def test_the_extension_writes_the_file_its_front_matter_names():
    """`companion_agents: agents.md` has to be true, or an assistant told to
    read the brief will not find one."""
    client = (EXTENSION / "src" / "page-client.js").read_text(encoding="utf-8")
    assert '"agents.md"' in client, "the front matter names agents.md but nothing writes it"


def test_the_extension_never_asks_for_the_cookie_permission():
    """The whole reason the extension exists is that it does not touch the
    session cookie. If that ever changes it must be a deliberate decision."""
    import json

    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    assert "cookies" not in manifest.get("permissions", [])
    assert not manifest.get("host_permissions"), "activeTab is meant to be the whole story"


def test_the_extension_injects_into_the_isolated_world():
    """The main world is the page's, and the page can define our globals before
    we do. Injecting there let a hostile page decide what got written to disk."""
    popup = (EXTENSION / "popup.js").read_text(encoding="utf-8")
    assert '"MAIN"' not in popup, "injection must stay in the isolated world"


def test_nothing_reads_or_writes_text_without_naming_an_encoding():
    """Windows defaults to cp1252, and this export is full of characters it has
    no idea about. Three separate rounds of Windows-only CI failures came from
    exactly this, so it is cheaper to assert it than to keep rediscovering it.

    Parsed rather than grepped, so a call split over several lines counts as
    encoded and the pattern in this test does not flag itself."""
    import ast

    root = Path(__file__).resolve().parent.parent
    offenders = []
    for path in sorted((root / "overleaf_comments_export").glob("*.py")) + \
            sorted((root / "tests").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("read_text", "write_text")
                    and not any(k.arg == "encoding" for k in node.keywords)):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, (
        "these read or write text without naming an encoding, which breaks on "
        f"Windows: {', '.join(offenders)}"
    )


def test_no_subprocess_decodes_with_the_locale_encoding():
    """`text=True` decodes a child process's output with the locale encoding,
    which is cp1252 on Windows. Every CI failure this project has had on
    Windows has been some version of that, so it is worth a rule rather than
    another round trip through CI."""
    import ast

    offenders = []
    for path in sorted((Path(__file__).resolve().parent.parent).rglob("*.py")):
        if ".venv" in path.parts or "node_modules" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            if name not in ("run", "check_output", "Popen"):
                continue
            kwargs = {k.arg for k in node.keywords}
            if "text" in kwargs and "encoding" not in kwargs:
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, (
        "these decode a child process with the locale encoding; name "
        f"encoding='utf-8' instead of text=True: {offenders}")
