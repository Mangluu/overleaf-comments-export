"""The CI workflows have to be readable by GitHub.

An unparseable workflow does not fail loudly. It appears in the Actions list
under its filename instead of its name, with no log to read, and everything it
was supposed to check simply never runs. That is worse than a failing test,
and it is a one-line check to prevent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOWS = sorted((Path(__file__).parent.parent / ".github" / "workflows").glob("*.yml"))


def test_there_are_workflows_to_check():
    assert WORKFLOWS, "no workflow files found, so this test is checking nothing"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_the_workflow_parses(path: Path):
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict), f"{path.name} is not a mapping"
    assert parsed.get("jobs"), f"{path.name} declares no jobs"
    for name, job in parsed["jobs"].items():
        assert job.get("steps") or job.get("uses"), f"{path.name}: {name} does nothing"


def test_the_window_tests_are_actually_switched_on_somewhere():
    """They skip themselves unless OCE_GUI_TESTS is set, and for a long time
    nothing set it, so none of them had ever run in CI."""
    text = "\n".join(p.read_text(encoding="utf-8") for p in WORKFLOWS)
    assert "OCE_GUI_TESTS" in text, (
        "no workflow sets OCE_GUI_TESTS, so every window test skips itself")


# --- what gets installed, and what the apps are built from ------------------

ROOT = Path(__file__).parent.parent


def _extras() -> dict:
    tomllib = pytest.importorskip("tomllib")    # 3.11 and later; 3.10 skips
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["optional-dependencies"]


def test_all_installs_everything_a_person_can_ask_for():
    """[all] left out openpyxl when the spreadsheet arrived, so the extra meant
    to install everything could not write a spreadsheet."""
    extras = _extras()
    wanted = {req for name, reqs in extras.items()
              if name not in ("all", "test") for req in reqs}
    missing = sorted(wanted - set(extras["all"]))
    assert not missing, f"[all] is missing {missing}"


def test_the_apps_are_built_with_everything_the_window_offers():
    """The window offers a spreadsheet. The Windows and Linux apps were built
    from [gui,pdf], so they could not write one, and nobody can pip install
    into a frozen app afterwards to fix it."""
    import re

    workflow = (ROOT / ".github" / "workflows" / "binaries.yml").read_text(encoding="utf-8")
    line = next(l for l in workflow.splitlines() if "pip install" in l and "pyinstaller" in l)
    installed = set(re.search(r"\.\[([^\]]*)\]", line).group(1).split(","))
    assert {"gui", "pdf", "xlsx"} <= installed, line
