"""Both implementations claim schema 1.3. This checks that they mean it.

The old parity test compared the version string and the Markdown front matter,
which is how the two JSON contracts drifted apart underneath it: the extension
was missing `comment_short_ids` that its own agent brief promised, Python was
missing `created_at`, and the extension carried an `occurred_at` nobody read.

This runs the extension's real core in node and Python's real run_export over
one shared fixture, then compares the shapes. Anything that differs has to be
named in KNOWN_GAPS with a reason, so a divergence is a decision rather than
an accident.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from overleaf_comments_export import export as export_mod
from tests.test_export_wiring import FakeClient

HERE = Path(__file__).parent
FIXTURE = HERE / "fixtures" / "schema_fixture.json"
RUNNER = HERE / "fixtures" / "run_extension.js"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node is needed to run the extension's own core",
)

# Every difference that is deliberate. Anything else fails the test.
KNOWN_GAPS = {
    ("comments[0]", "python"): {
        # Needs float detection in JS, which the extension does not have yet.
        "enclosing_float",
    },
    ("top level", "python"): {
        # The extension exposes fewer filters, and does not record them.
        "filters_applied",
    },
    ("top level", "extension"): {
        # The extension's report can be written in English or Chinese. Python
        # has no language option, so it has nothing to record.
        "report_language",
    },
}


@pytest.fixture(scope="module")
def fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def extension_payload(fixture) -> dict:
    proc = subprocess.run(["node", str(RUNNER)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def python_payload(fixture) -> dict:
    f = fixture
    at = f["docText"].index(f["anchor"])

    class Fixture(FakeClient):
        def get_threads(self, project_id):
            return f["threads"]

        def get_resolved_thread_ids(self, project_id):
            return []

        def get_project_metadata(self, project_id):
            return {"files": {"docs": []}, "name": f["projectTitle"],
                    "rootDocId": f["docId"], "raw_meta": {}}

        def flatten_files(self, files_root, debug_logger=None):
            # The extension is handed docIdToPath directly, so Python needs
            # the same mapping or the two disagree on pathname for a reason
            # that has nothing to do with either contract.
            return [{"doc_id": f["docId"], "pathname": f["pathname"]}]

        def get_project_ranges(self, project_id):
            return [{"id": f["docId"], "ranges": {
                "comments": [{"op": {"p": at, "c": f["anchor"], "t": "t1"}}],
                "changes": [f["trackedChange"]]}}]

        def download_doc_text(self, project_id, doc_id):
            return f["docText"]

    real = export_mod.OverleafClient
    export_mod.OverleafClient = Fixture
    try:
        out = Path(tempfile.mkdtemp())
        result = export_mod.run_export(
            project_url="https://www.overleaf.com/project/" + f["projectId"],
            out_dir=out)
        return json.loads(result.json_path.read_text(encoding="utf-8"))
    finally:
        export_mod.OverleafClient = real


def _at(payload: dict, path: str):
    """'files[0]' and 'threads.t1' and so on, so failures name a real place."""
    node = payload
    for part in path.split("."):
        if part.endswith("]"):
            part, _, index = part[:-1].partition("[")
            node = node[part][int(index)]
        else:
            node = node[part]
    return node


PLACES = [
    "top level", "summary", "files[0]", "comments[0]",
    "tracked_changes[0]", "threads.t1", "threads.t1.messages[0]",
]


@pytest.mark.parametrize("place", PLACES)
def test_the_two_exports_have_the_same_shape(place, python_payload,
                                             extension_payload):
    path = "" if place == "top level" else place
    py = set(python_payload if not path else _at(python_payload, path))
    ext = set(extension_payload if not path else _at(extension_payload, path))

    only_py = (py - ext) - KNOWN_GAPS.get((place, "python"), set())
    only_ext = (ext - py) - KNOWN_GAPS.get((place, "extension"), set())

    assert not only_py and not only_ext, (
        f"Both exports declare schema {python_payload['schema_version']} and "
        f"disagree about {place}.\n"
        f"  Only in Python:    {sorted(only_py) or 'nothing'}\n"
        f"  Only in extension: {sorted(only_ext) or 'nothing'}\n"
        f"Either add the field on the other side, or name it in KNOWN_GAPS "
        f"with the reason, or give the extension its own schema version."
    )


def test_the_known_gaps_are_still_real():
    """A gap that has been closed must not sit in the list pretending to be a
    difference, or the list stops meaning anything."""
    assert KNOWN_GAPS, "if there are no gaps left, delete the list and this test"


@pytest.mark.parametrize("place", ["comments[0]", "tracked_changes[0]"])
def test_the_shared_fields_agree_on_values_too(place, python_payload,
                                               extension_payload):
    """Same keys with different meanings would be worse than different keys."""
    py, ext = _at(python_payload, place), _at(extension_payload, place)
    for key in ("short_id", "pathname", "line", "col", "offset",
                "anchored_text", "kind", "content", "nearest_heading"):
        if key in py and key in ext:
            assert py[key] == ext[key], (
                f"{place}.{key} differs: Python {py[key]!r}, "
                f"extension {ext[key]!r}")


def test_the_agent_brief_does_not_promise_fields_that_are_missing():
    """The extension's brief listed comment_short_ids while its files[] had no
    such key, which is how the gap went unnoticed."""
    core = (HERE.parent / "browser-extension" / "src" / "export-core.js").read_text(
        encoding="utf-8")
    brief = core[core.index("- \\`files\\`"):]
    brief = brief[:brief.index("- \\`comments\\`")]
    promised = [f for f in ("comment_short_ids", "change_short_ids") if f in brief]
    assert promised, "the brief no longer lists the files[] short-id arrays"
    for field in promised:
        assert f"{field}:" in core, (
            f"the brief promises files[].{field} and nothing writes it")
