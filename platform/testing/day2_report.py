"""ADR-0057: the shared report engine every Day 2 command (`make d2
test`/`make d2 stresstest`) renders its results through - one `Day2Result`
shape, three renderers. `render_text` is always printed by the caller
regardless of `report_format` ("by default display a raw of the report" -
ADR-0057 decision 4); `render_json`/`render_csv` back the additional
artifact `write_report` files under `evaluations/day2-reports/` when
`report_format` selects one.

Used by `platform/testing/day2_stresstest.py` (ADR-0058) and the Day 2
Ansible task files (`ansible/roles/day2/`, `ansible/tasks/
day2_availability_check.yml`) via each Job's Python entrypoint printing
this module's text/json/csv output to stdout, fetched by `k8s_log` the
same way `evaluations/tekos/run_acceptance_gate.py`'s output already is.
"""
from __future__ import annotations

import csv
import io
import json
import pathlib
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "evaluations" / "day2-reports"

_FORMAT_EXTENSIONS = {"json": "json", "csv": "csv"}
_HTTP_STATUS_RE = re.compile(r"status[=_ ](\d{3})")


@dataclass
class Day2Result:
    agent: str
    layer: str
    id: str
    category: str
    passed: bool
    detail: str = ""
    duration_ms: float = 0.0


def log_test_line(agent: str, layer: str, test_id: str, description: str, passed: bool, detail: str) -> None:
    """One line per test, printed to stderr as each test completes (unlike
    the single aggregated JSON array day2_stresstest.py/day2_bulk.py print
    to stdout at the very end) - so `oc logs -f` on a running stresstest
    Job shows live progress instead of nothing until the whole run exits.
    HTTP status is extracted best-effort from `detail` (most checks already
    embed "status=NNN"); "-" when a check has no HTTP call to report.
    """
    now = time.strftime("%H:%M:%S") + f".{int((time.time() % 1) * 1000):03d}"
    match = _HTTP_STATUS_RE.search(detail)
    http_code = match.group(1) if match else "-"
    mark = "PASS" if passed else "FAIL"
    print(f"{now} [{agent}] {layer}#{test_id} http={http_code} {mark} {description}", file=sys.stderr)


def summarize(results: List[Day2Result]) -> Dict[str, object]:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "result": "PASS" if passed == total else "FAIL",
    }


def render_text(results: List[Day2Result]) -> str:
    # A literal separator (not just fixed-width padding) between columns -
    # id values can be arbitrarily long (e.g. contract-test suite paths
    # like "contract/test_bundle_self_consistency.py"), and padding alone
    # would let a long id run straight into the next column with no
    # visible boundary.
    lines = [f"{'AGENT':<14} {'LAYER':<12} {'PASS':<6} {'CATEGORY':<14} ID"]
    for r in results:
        lines.append(f"{r.agent:<14} {r.layer:<12} {'PASS' if r.passed else 'FAIL':<6} {r.category:<14} {r.id}")
        if not r.passed and r.detail:
            lines.append(f"      -> {r.detail}")

    lines.append("")
    groups = sorted({(r.agent, r.category) for r in results})
    for agent, category in groups:
        subset = [r for r in results if r.agent == agent and r.category == category]
        passed = sum(1 for r in subset if r.passed)
        lines.append(f"{agent}/{category}: {passed}/{len(subset)} passed")

    summary = summarize(results)
    lines.append("")
    lines.append(f"{summary['passed']}/{summary['total']} passed overall - {summary['result']}")
    return "\n".join(lines)


def render_json(results: List[Day2Result], summary: Optional[Dict[str, object]] = None) -> str:
    summary = summary if summary is not None else summarize(results)
    return json.dumps({"results": [asdict(r) for r in results], "summary": summary}, indent=2)


def render_csv(results: List[Day2Result]) -> str:
    buf = io.StringIO()
    fieldnames = ["agent", "layer", "id", "category", "passed", "detail", "duration_ms"]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for r in results:
        writer.writerow(asdict(r))
    return buf.getvalue()


def write_report(
    results: List[Day2Result],
    summary: Dict[str, object],
    report_format: str,
    component: str,
) -> Optional[pathlib.Path]:
    """Writes the json/csv artifact selected by report_format; returns None
    for "text" (or any other value) - the text table is only ever printed
    by the caller, never filed, so the default output stays exactly
    "raw text on stdout" with no extra artifact.
    """
    if report_format not in _FORMAT_EXTENSIONS:
        return None
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = REPORTS_DIR / f"{timestamp}-{component}.{_FORMAT_EXTENSIONS[report_format]}"
    if report_format == "json":
        path.write_text(render_json(results, summary))
    else:
        path.write_text(render_csv(results))
    return path


def _cli(argv: Optional[List[str]] = None) -> int:
    """Thin CLI over this module, for callers that build results in a
    non-Python context (Ansible/Jinja) rather than importing this module
    directly: reads a JSON array of Day2Result-shaped objects from stdin,
    always prints the text table (ADR-0057 decision 4: raw text is the
    default, always-visible output), and additionally writes a json/csv
    artifact when --format selects one.

        python3 day2_report.py --format json --component agents < results.json
    """
    import argparse

    parser = argparse.ArgumentParser(description=_cli.__doc__)
    parser.add_argument("--format", dest="report_format", default="text", choices=["text", "json", "csv"])
    parser.add_argument("--component", default="agents")
    args = parser.parse_args(argv)

    raw = json.load(sys.stdin)
    results = [Day2Result(**row) for row in raw]
    summary = summarize(results)

    print(render_text(results))

    path = write_report(results, summary, args.report_format, args.component)
    if path is not None:
        print(f"\nReport written: {path}")

    return 0 if summary["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(_cli())
