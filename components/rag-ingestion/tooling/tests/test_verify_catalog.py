#!/usr/bin/env python3
"""ADR-0330 tests for the catalog verification tool
(tooling/verify_catalog.py). Mocks the HTTP layer - this tool is meant to
run from a network that can reach docs.redhat.com, which this environment
cannot (HTTP 403, see ADR-0330's "Follow-up implementation" section) - to
prove the OK/REDIRECT/FAIL classification and report formatting.

Same plain-function/no-pytest style as components/rag-service/tests/
test_search_filters.py, still pytest-collectible (the WP-07 brief's
acceptance check runs `python3 -m pytest components/rag-ingestion/ -q`).

Run directly:

    cd components/rag-ingestion/tooling && python3 tests/test_verify_catalog.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import verify_catalog

import requests  # noqa: E402

from verify_catalog import classify_url, format_report, load_redhat_sources, verify  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code: int, url: str):
        self.status_code = status_code
        self.url = url


class _FakeSession:
    """Stands in for requests.Session: records every call and answers via
    an injected responder callable, so tests never touch the network."""

    def __init__(self, responder):
        self._responder = responder
        self.calls = []

    def request(self, method, url, timeout=None, allow_redirects=None, headers=None):
        self.calls.append(method)
        return self._responder(method, url)


def test_classify_ok_when_status_200_and_no_redirect() -> None:
    session = _FakeSession(lambda method, url: _FakeResponse(200, url))
    status, detail = classify_url("https://docs.redhat.com/x", session)
    assert status == "OK"
    assert detail == "200"


def test_classify_redirect_when_final_url_differs() -> None:
    session = _FakeSession(lambda method, url: _FakeResponse(200, "https://docs.redhat.com/x/new"))
    status, detail = classify_url("https://docs.redhat.com/x", session)
    assert status == "REDIRECT"
    assert detail == "https://docs.redhat.com/x/new"


def test_classify_fail_on_http_error_status() -> None:
    session = _FakeSession(lambda method, url: _FakeResponse(404, url))
    status, detail = classify_url("https://docs.redhat.com/x", session)
    assert status == "FAIL"
    assert "404" in detail


def test_classify_falls_back_to_get_when_head_is_rejected() -> None:
    def responder(method, url):
        if method == "HEAD":
            return _FakeResponse(405, url)
        return _FakeResponse(200, url)

    session = _FakeSession(responder)
    status, detail = classify_url("https://docs.redhat.com/x", session)
    assert status == "OK"
    assert session.calls == ["HEAD", "GET"]


def test_classify_reports_the_real_status_when_get_is_also_rejected() -> None:
    """HEAD's 405/501 triggers a GET fallback (see
    test_classify_falls_back_to_get_when_head_is_rejected), but there is
    no further fallback after GET - its own result (even another
    405/501) is reported directly and accurately, not masked by a
    generic 'both rejected' message."""
    session = _FakeSession(lambda method, url: _FakeResponse(501, url))
    status, detail = classify_url("https://docs.redhat.com/x", session)
    assert status == "FAIL"
    assert detail == "HTTP 501"
    assert session.calls == ["HEAD", "GET"]


def test_classify_fail_on_network_exception() -> None:
    def responder(method, url):
        raise requests.ConnectionError("connection refused")

    session = _FakeSession(responder)
    status, detail = classify_url("https://docs.redhat.com/x", session)
    assert status == "FAIL"
    assert "ConnectionError" in detail


def test_format_report_includes_summary_counts_and_every_entry() -> None:
    results = [
        {"product": "A", "version": "1", "url": "https://a", "status": "OK", "detail": "200"},
        {"product": "B", "version": "2", "url": "https://b", "status": "REDIRECT", "detail": "https://b-new"},
        {"product": "C", "version": "3", "url": "https://c", "status": "FAIL", "detail": "HTTP 404"},
    ]
    report = format_report(results)
    assert "1 OK, 1 REDIRECT, 1 FAIL, 3 total" in report
    assert "https://b-new" in report
    assert "product='A'" in report and "product='B'" in report and "product='C'" in report


def test_load_redhat_sources_reads_the_real_values_file() -> None:
    """Proves the tool actually parses gitops/charts/rag-ingestion/
    values.yaml's real shape, not a synthetic fixture - catches drift if
    the schema ever changes underneath this tool."""
    repo_root = pathlib.Path(__file__).resolve().parents[4]
    values_path = repo_root / "gitops" / "charts" / "rag-ingestion" / "values.yaml"
    sources = load_redhat_sources(values_path)
    assert len(sources) >= 30, "expected the full 17-product catalog (34 entries)"
    assert all("documentationUrl" in s and "product" in s for s in sources)
    satellite = [s for s in sources if s["product"] == "Red Hat Satellite"]
    assert len(satellite) == 2


def test_verify_skips_disabled_entries() -> None:
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write(
            "redhat:\n"
            "  - enabled: true\n"
            "    product: Enabled Product\n"
            "    version: '1'\n"
            "    documentationUrl: https://example.invalid/enabled\n"
            "  - enabled: false\n"
            "    product: Disabled Product\n"
            "    version: '1'\n"
            "    documentationUrl: https://example.invalid/disabled\n"
        )
        temp_path = pathlib.Path(fh.name)

    try:
        import verify_catalog as vc

        original_session = requests.Session
        requests.Session = lambda: _FakeSession(lambda method, url: _FakeResponse(200, url))
        try:
            results = vc.verify(temp_path)
        finally:
            requests.Session = original_session
        assert [r["product"] for r in results] == ["Enabled Product"]
    finally:
        temp_path.unlink()


TESTS = [
    test_classify_ok_when_status_200_and_no_redirect,
    test_classify_redirect_when_final_url_differs,
    test_classify_fail_on_http_error_status,
    test_classify_falls_back_to_get_when_head_is_rejected,
    test_classify_reports_the_real_status_when_get_is_also_rejected,
    test_classify_fail_on_network_exception,
    test_format_report_includes_summary_counts_and_every_entry,
    test_load_redhat_sources_reads_the_real_values_file,
    test_verify_skips_disabled_entries,
]


def main() -> int:
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
