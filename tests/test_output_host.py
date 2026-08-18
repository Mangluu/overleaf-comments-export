"""The compile reply decides which host the built PDF is fetched from.

It is the only value in any response that chooses a host, so it is the only
one that has to be checked. Overleaf genuinely answers with a different host,
because the build stays on the machine that compiled it, and that host is
always part of the same site.
"""

from __future__ import annotations

import pytest

from overleaf_comments_export.client import OverleafClient


def client(base="https://www.overleaf.com"):
    return OverleafClient(base_url=base)


@pytest.mark.parametrize("domain", [
    "https://clsi-a1b2.overleaf.com",           # what Overleaf really sends
    "https://www.overleaf.com",
    "https://deep.nested.sub.www.overleaf.com",
])
def test_a_host_on_the_same_site_is_used(domain):
    url = client()._output_url("/build/x/output.pdf", {"pdfDownloadDomain": domain})
    assert url.startswith(domain)


@pytest.mark.parametrize("domain", [
    "https://evil.example.com",
    "https://www.overleaf.com.evil.example",     # the classic suffix trick
    "https://notoverleaf.com",
    "http://localhost:8080",
])
def test_a_host_somewhere_else_is_ignored(domain):
    url = client()._output_url("/build/x/output.pdf", {"pdfDownloadDomain": domain})
    assert url.startswith("https://www.overleaf.com/"), url
    assert "evil" not in url and "localhost" not in url


def test_an_absolute_url_elsewhere_keeps_only_its_path():
    url = client()._output_url("https://evil.example.com/build/x/output.pdf?v=1", {})
    assert url == "https://www.overleaf.com/build/x/output.pdf?v=1"


def test_an_absolute_url_on_the_same_site_is_left_alone():
    same = "https://clsi-9.overleaf.com/build/x/output.pdf"
    assert client()._output_url(same, {}) == same


def test_a_self_hosted_instance_judges_against_its_own_host():
    c = client("https://overleaf.my-university.edu")
    ok = c._output_url("/p.pdf", {"pdfDownloadDomain": "https://clsi.overleaf.my-university.edu"})
    assert ok.startswith("https://clsi.overleaf.my-university.edu")
    # www.overleaf.com is a stranger to a self-hosted install, not a parent.
    bad = c._output_url("/p.pdf", {"pdfDownloadDomain": "https://www.overleaf.com"})
    assert bad.startswith("https://overleaf.my-university.edu/")


def test_the_server_id_still_gets_appended():
    url = client()._output_url("/build/x/output.pdf",
                               {"pdfDownloadDomain": "https://clsi-7.overleaf.com",
                                "clsiServerId": "srv-42"})
    assert url.endswith("?clsiserverid=srv-42")


def test_nothing_named_falls_back_to_the_site_we_signed_in_to():
    assert client()._output_url("/build/x/output.pdf", {}).startswith(
        "https://www.overleaf.com/")
