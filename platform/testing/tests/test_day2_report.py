"""ADR-0057 acceptance tests for the shared Day 2 report engine
(platform/testing/day2_report.py). Pure in-memory rendering logic, no
cluster needed - same plain-function/no-pytest style as
platform/supply-chain/tests/test_pin_release.py.

Run from this directory:

    python3 tests/test_day2_report.py
"""
from __future__ import annotations

import csv
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
TESTING_DIR = TESTS_DIR.parent

sys.path.insert(0, str(TESTING_DIR))
import day2_report  # noqa: E402
from day2_report import Day2Result  # noqa: E402


def _sample_results() -> list[Day2Result]:
    return [
        Day2Result("tekos", "scenario", "1", "portal", True, "", 12.5),
        Day2Result("tekos", "scenario", "2", "portal", False, "unexpected 404", 8.1),
        Day2Result("arkos", "security", "sec-1", "identity", True, "", 3.0),
    ]


def test_summarize_counts_pass_fail_total() -> None:
    summary = day2_report.summarize(_sample_results())
    assert summary["total"] == 3
    assert summary["passed"] == 2
    assert summary["failed"] == 1
    assert summary["result"] == "FAIL"


def test_summarize_all_passed_is_pass() -> None:
    results = [Day2Result("tekos", "scenario", "1", "portal", True)]
    summary = day2_report.summarize(results)
    assert summary["result"] == "PASS"


def test_render_text_includes_every_id_and_the_overall_line() -> None:
    text = day2_report.render_text(_sample_results())
    assert "1" in text and "2" in text and "sec-1" in text
    assert "unexpected 404" in text
    assert "2/3 passed overall - FAIL" in text


def test_render_json_round_trips_results_and_summary() -> None:
    results = _sample_results()
    doc = json.loads(day2_report.render_json(results))
    assert len(doc["results"]) == 3
    assert doc["results"][0]["agent"] == "tekos"
    assert doc["results"][1]["passed"] is False
    assert doc["summary"]["total"] == 3
    assert doc["summary"]["result"] == "FAIL"


def test_render_csv_has_one_row_per_result_and_matching_header() -> None:
    results = _sample_results()
    rows = list(csv.DictReader(io.StringIO(day2_report.render_csv(results))))
    assert len(rows) == 3
    assert rows[1]["detail"] == "unexpected 404"
    assert rows[2]["agent"] == "arkos"
    assert set(rows[0].keys()) == {"agent", "layer", "id", "category", "passed", "detail", "duration_ms"}


def test_write_report_returns_none_for_text() -> None:
    results = _sample_results()
    summary = day2_report.summarize(results)
    assert day2_report.write_report(results, summary, "text", "agents") is None


def test_write_report_writes_json_and_csv_artifacts() -> None:
    results = _sample_results()
    summary = day2_report.summarize(results)
    original_reports_dir = day2_report.REPORTS_DIR
    tmpdir = Path(tempfile.mkdtemp())
    try:
        day2_report.REPORTS_DIR = tmpdir
        json_path = day2_report.write_report(results, summary, "json", "agents")
        csv_path = day2_report.write_report(results, summary, "csv", "agents")
        assert json_path is not None and json_path.exists()
        assert csv_path is not None and csv_path.exists()
        assert json.loads(json_path.read_text())["summary"]["total"] == 3
        assert len(list(csv.DictReader(io.StringIO(csv_path.read_text())))) == 3
    finally:
        day2_report.REPORTS_DIR = original_reports_dir
        shutil.rmtree(tmpdir, ignore_errors=True)


TESTS = [
    test_summarize_counts_pass_fail_total,
    test_summarize_all_passed_is_pass,
    test_render_text_includes_every_id_and_the_overall_line,
    test_render_json_round_trips_results_and_summary,
    test_render_csv_has_one_row_per_result_and_matching_header,
    test_write_report_returns_none_for_text,
    test_write_report_writes_json_and_csv_artifacts,
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
