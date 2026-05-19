from __future__ import annotations

import pytest

from overleaf_comments_export.client import (
    OverleafClient,
    _decode_meta_content,
    parse_project_id,
)


def test_parse_project_id_basic():
    assert (
        parse_project_id("https://www.overleaf.com/project/507f1f77bcf86cd799439011")
        == "507f1f77bcf86cd799439011"
    )


def test_parse_project_id_with_trailing_path():
    assert (
        parse_project_id(
            "https://www.overleaf.com/project/507f1f77bcf86cd799439011/something"
        )
        == "507f1f77bcf86cd799439011"
    )


def test_parse_project_id_self_hosted():
    assert (
        parse_project_id("https://my-overleaf.example.com/project/507f1f77bcf86cd799439011")
        == "507f1f77bcf86cd799439011"
    )


def test_parse_project_id_rejects_garbage():
    with pytest.raises(ValueError):
        parse_project_id("https://www.overleaf.com/not-a-project")


def test_decode_meta_content_plain_string():
    assert _decode_meta_content("Hello") == "Hello"


def test_decode_meta_content_html_entity():
    assert _decode_meta_content("a &amp; b") == "a & b"


def test_decode_meta_content_url_encoded_json():
    # %7B...%7D encodes {"k":"v"}
    assert _decode_meta_content("%7B%22k%22%3A%22v%22%7D") == {"k": "v"}


def test_supported_browsers_lists_safari_first():
    assert OverleafClient.SUPPORTED_BROWSERS[0] == "safari"
    assert "safari" in OverleafClient.PRIVACY_FRIENDLY_BROWSERS
    assert "firefox" in OverleafClient.PRIVACY_FRIENDLY_BROWSERS


class _FakeProjectFile:
    def __init__(self, id_, name, type_="doc"):
        self.id = id_
        self.name = name
        self.type = type_


class _FakeProjectFolder:
    def __init__(self, id_, name, children):
        self.id = id_
        self.name = name
        self.children = children
        self.type = "folder"


def test_flatten_files_handles_pyoverleaf_dataclass():
    root = _FakeProjectFolder(
        "root",
        "rootFolder",
        [
            _FakeProjectFile("d1", "main.tex"),
            _FakeProjectFile("img1", "cover.png", type_="file"),
            _FakeProjectFolder(
                "sec",
                "sections",
                [
                    _FakeProjectFile("d2", "intro.tex"),
                    _FakeProjectFile("d3", "method.tex"),
                ],
            ),
        ],
    )
    client = OverleafClient()
    result = client.flatten_files(root)
    paths = {r["pathname"] for r in result}
    assert paths == {"main.tex", "sections/intro.tex", "sections/method.tex"}


def test_flatten_files_handles_raw_dict():
    raw = {
        "_id": "root",
        "name": "rootFolder",
        "docs": [
            {"_id": "d1", "name": "main.tex"},
        ],
        "folders": [
            {
                "_id": "f1",
                "name": "sections",
                "docs": [{"_id": "d2", "name": "intro.tex"}],
                "folders": [],
                "fileRefs": [],
            }
        ],
        "fileRefs": [],
    }
    client = OverleafClient()
    paths = {r["pathname"] for r in client.flatten_files(raw)}
    assert paths == {"main.tex", "sections/intro.tex"}


def test_flatten_files_empty_calls_debug_logger():
    captured = []
    OverleafClient().flatten_files({}, debug_logger=lambda *a, **k: captured.append(a))
    assert captured  # should have invoked the logger with a preview
