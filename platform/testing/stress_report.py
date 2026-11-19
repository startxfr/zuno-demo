#!/usr/bin/env python3
"""The report of a stress campaign: per-driver table, saturation, counters, guard, trend, evidence (WP-312, ADR-0624).

Reads the rows a campaign printed (JSON arrays, one per line, as `stress_runner.py` writes them and the collector
gathers them) and builds ONE report from them:

  drivers      n, ok, err, error rate, 429, 5xx, p50/p95/p99, shards, the guard that stopped it (merged over the shards
               by `stress_runner.merge_summaries`)
  failures     the first failing rows, so a red driver says why
  guards       a driver stopped by the budget guard, or the run stopped at its token cap
  saturation   the rows of the sampler (vLLM queue, KV-cache, gateway p95, Postgres backends)
  counters     the Limitador counters that moved during the run, per identity
  trend        the same campaign (same profile) compared with the previous one: p95 and error rate per driver

Informational (ADR-0058): the exit code is 0 whatever the report says. Stdlib only, so it runs in the AAP execution
environment as well as on a workstation. Files are written only when asked:

    --trend-dir DIR      reads the previous run of the same profile from DIR and writes this one as stress-<run id>.json
    --evidence-dir DIR   writes stress-<run id>.md (docs/roadmap/evidence/ in the repository: a file for a person to
                         review and commit, never committed by the tool)

    python3 platform/testing/stress_report.py --rows rows.json --run-id smoke-20261119-143000 --profile smoke \\
        --trend-dir evaluations/day2-reports/stress --format text
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import stress_runner as sr  # noqa: E402

FAILURE_LIMIT = 20
P95_REGRESSION = 1.5      # a p95 above this multiple of the previous run's is flagged
ERROR_REGRESSION = 0.05   # an error rate this much higher (absolute) is flagged
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SAMPLER_LAYERS = ("saturation", "counters", "chaos")
WINDOW_RE = re.compile(r"window=(\d+)-(\d+)")
BEFORE_SECONDS = 120   # the load before a disruption that counts as its baseline
GRACE_SECONDS = 60     # the load after a disruption's end that still counts as its effect
QUIET_BUCKETS = 2      # consecutive error-free buckets that mean the load has recovered


def parse_rows(text: str) -> List[Dict[str, Any]]:
    """The rows of a collected log: every line that is a JSON array is a batch of rows; anything else is ignored."""
    rows: List[Dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            try:
                rows += [r for r in json.loads(line) if isinstance(r, dict)]
            except ValueError:
                continue
    if not rows and text.strip().startswith("["):
        rows = [r for r in json.loads(text) if isinstance(r, dict)]
    return rows


def combined_timeline(drivers: List[Dict[str, Any]]) -> Dict[int, List[int]]:
    """{bucket: [iterations, failed]} over every driver of the run."""
    out: Dict[int, List[int]] = {}
    for d in drivers:
        for bucket, n, err in d.get("timeline", []):
            cell = out.setdefault(int(bucket), [0, 0])
            cell[0] += int(n)
            cell[1] += int(err)
    return out


def chaos_effects(timeline: Dict[int, List[int]], start: int, end: int) -> Dict[str, Any]:
    """What the load saw around one disruption window [start, end] (epoch seconds): failures before, during and the time the
    load took to run clean again after it ended. None for a part with no iteration in it."""
    step = sr.TIMELINE_BUCKET

    def totals(lo: int, hi: int) -> List[int]:
        n = err = 0
        for bucket, (count, failed) in timeline.items():
            if lo <= bucket + step and bucket <= hi:
                n += count
                err += failed
        return [n, err]

    before = totals(start - BEFORE_SECONDS, start - 1)
    during = totals(start, end + GRACE_SECONDS)
    recovered = None
    clean = 0
    for bucket in sorted(b for b in timeline if b + step > end):
        count, failed = timeline[bucket]
        clean = clean + 1 if (count and not failed) else 0
        if clean >= QUIET_BUCKETS:
            recovered = max(0, bucket - step * (QUIET_BUCKETS - 1) - end)
            break
    return {"before": before, "during": during, "recovered_after_s": recovered}


def truthy(value: Any) -> bool:
    """A row's `passed` as a bool: an execution environment may hand the report the string "False"."""
    return value is True or str(value).strip().lower() == "true"


SHARED_SA_FAMILIES = ("experiences", "unifai", "guardrails")  # real client paths: they ride the shared ai-gateway ServiceAccount on purpose
STRESS_SA_FAMILIES = ("load", "models")                        # the dedicated stress ServiceAccount


def shared_path_attribution(drivers: List[Dict[str, Any]]) -> str:
    """What moved the shared ai-gateway ServiceAccount's counter, by iterations of the drivers whose path rides it (not by tokens:
    the Limitador counter does not say who spent them), next to the iterations of the drivers on the stress ServiceAccount."""
    def total(families):
        by_family: Dict[str, int] = {}
        for d in drivers:
            if d.get("family") in families:
                by_family[d["family"]] = by_family.get(d["family"], 0) + d["n"]
        return by_family
    shared, stress = total(SHARED_SA_FAMILIES), total(STRESS_SA_FAMILIES)
    if not shared and not stress:
        return ""
    fmt = lambda m: ", ".join(f"{k} {v}" for k, v in sorted(m.items())) or "none"
    return (f"iterations that ride the shared ServiceAccount by design (real client paths): {fmt(shared)}; "
            f"on the stress ServiceAccount: {fmt(stress)}; the per-agent Jobs of the agents family also use the shared one")


def build_report(rows: List[Dict[str, Any]], meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The report of a run. `meta`: run_id, profile, started, job_state (all optional)."""
    meta = dict(meta or {})
    drivers = sr.merge_summaries(rows)
    for d in drivers:
        d["err_rate"] = round(d["err"] / d["n"], 4) if d["n"] else 0.0
    failures = [
        {"driver": r.get("agent", "?"), "id": r.get("id", "?"), "detail": str(r.get("detail", ""))[:240]}
        for r in rows
        if not truthy(r.get("passed")) and r.get("layer") not in SAMPLER_LAYERS and r.get("layer") != sr.SUMMARY_LAYER
        and r.get("category") != "guard"
    ]
    guards = [{"driver": r.get("agent", "?"), "detail": str(r.get("detail", ""))[:240]} for r in rows if r.get("category") == "guard"]
    saturation = [{"signal": r.get("id", "?"), "passed": truthy(r.get("passed")), "detail": str(r.get("detail", ""))} for r in rows if r.get("layer") == "saturation"]
    counters = [{"id": r.get("id", "?"), "passed": truthy(r.get("passed")), "detail": str(r.get("detail", ""))} for r in rows if r.get("layer") == "counters"]
    attribution = shared_path_attribution(drivers)
    if attribution and any(c["id"] == "isolation" for c in counters):
        counters.append({"id": "isolation-attribution", "passed": True, "detail": attribution})
    saturated = [s for s in saturation if not s["passed"]]
    timeline = combined_timeline(drivers)
    chaos = []
    for r in rows:
        if r.get("layer") != "chaos":
            continue
        window = WINDOW_RE.search(str(r.get("detail", "")))
        chaos.append({"id": r.get("id", "?"), "passed": truthy(r.get("passed")), "detail": str(r.get("detail", "")),
                      "effects": chaos_effects(timeline, int(window.group(1)), int(window.group(2))) if window and timeline else None})
    attention = bool(failures or guards or saturated or any(d["err"] for d in drivers) or any(not c["passed"] for c in counters)
                     or any(not c["passed"] for c in chaos))
    return {
        "run_id": meta.get("run_id", ""), "profile": meta.get("profile", ""), "started": meta.get("started", ""),
        "job_state": meta.get("job_state", ""), "rows": len(rows), "drivers": drivers,
        "failures": failures[:FAILURE_LIMIT], "failure_count": len(failures), "guards": guards,
        "saturation": saturation, "counters": counters, "chaos": chaos,
        "verdict": "ATTENTION" if attention else "CLEAN",
    }


def compare(report: Dict[str, Any], previous: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per driver present in both runs: p95 and error-rate deltas, and whether either regressed."""
    if not previous:
        return []
    before = {d["driver"]: d for d in previous.get("drivers", [])}
    out = []
    for d in report["drivers"]:
        b = before.get(d["driver"])
        if not b:
            continue
        p95_ratio = (d["p95"] / b["p95"]) if b.get("p95") else None
        err_delta = d["err_rate"] - b.get("err_rate", 0.0)
        out.append({"driver": d["driver"], "p95": d["p95"], "p95_before": b.get("p95", 0.0), "p95_ratio": p95_ratio,
                    "err_rate": d["err_rate"], "err_rate_before": b.get("err_rate", 0.0),
                    "regressed": bool((p95_ratio and p95_ratio > P95_REGRESSION) or err_delta >= ERROR_REGRESSION)})
    return out


def save_trend(report: Dict[str, Any], directory: pathlib.Path) -> pathlib.Path:
    directory.mkdir(parents=True, exist_ok=True)
    if not RUN_ID_RE.match(report["run_id"] or ""):
        raise ValueError(f"run id {report['run_id']!r} is not a name")
    path = directory / f"stress-{report['run_id']}.json"
    path.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    return path


def load_previous(directory: pathlib.Path, profile: str, run_id: str) -> Optional[Dict[str, Any]]:
    """The newest saved report of the same profile that is not `run_id` (run ids end with a UTC stamp, so names sort by time)."""
    if not directory.is_dir():
        return None
    for path in sorted(directory.glob("stress-*.json"), reverse=True):
        try:
            data = json.loads(path.read_text())
        except ValueError:
            continue
        if data.get("profile") == profile and data.get("run_id") != run_id:
            return data
    return None


def _ms(value: float) -> str:
    return f"{value:.0f}ms"


def effects_text(effects: Optional[Dict[str, Any]]) -> str:
    """The load's view of a disruption, one clause: failures before and during, and the time to run clean again."""
    if not effects:
        return "no load timeline to correlate"

    def rate(pair: List[int]) -> str:
        return f"{pair[1]}/{pair[0]}" if pair[0] else "no iteration"

    recovered = effects["recovered_after_s"]
    tail = ("not clean again before the end of the run" if recovered is None
            else "clean again " + (f"{recovered}s after the end" if recovered else "at once"))
    return f"load failures {rate(effects['before'])} before, {rate(effects['during'])} during and the minute after; {tail}"


def render_text(report: Dict[str, Any], diff: Optional[List[Dict[str, Any]]] = None) -> str:
    lines = [f"STRESS REPORT run={report['run_id'] or '-'} profile={report['profile'] or '-'} job={report['job_state'] or '-'} "
             f"rows={report['rows']} verdict={report['verdict']} (informational, ADR-0058)"]
    lines.append(sr.render_table([{**d, "guard": d["guard"]} for d in report["drivers"]]))
    if report["guards"]:
        lines += ["", "BUDGET GUARD"] + [f"  {g['driver']}: {g['detail']}" for g in report["guards"]]
    if report["failures"]:
        more = report["failure_count"] - len(report["failures"])
        lines += ["", f"FAILURES ({report['failure_count']})"] + [f"  {f['driver']} {f['id']}: {f['detail']}" for f in report["failures"]]
        if more > 0:
            lines.append(f"  ... and {more} more")
    if report["saturation"]:
        lines += ["", "SATURATION"] + [f"  {'ok       ' if s['passed'] else 'SATURATED'} {s['signal']}: {s['detail']}" for s in report["saturation"]]
    if report["counters"]:
        lines += ["", "LIMITADOR COUNTERS"] + [f"  {c['id']}: {c['detail']}" for c in report["counters"]]
    if report.get("chaos"):
        lines += ["", "CHAOS"]
        for c in report["chaos"]:
            lines.append(f"  {'recovered' if c['passed'] else 'DID NOT RECOVER'} {c['id']}: {c['detail']}")
            lines.append(f"      {effects_text(c['effects'])}")
    if diff:
        lines += ["", "TREND (against the previous run of this profile)"]
        for d in diff:
            ratio = f"x{d['p95_ratio']:.2f}" if d["p95_ratio"] else "n/a"
            lines.append(f"  {'REGRESSED' if d['regressed'] else 'ok       '} {d['driver']}: p95 {_ms(d['p95_before'])} -> {_ms(d['p95'])} ({ratio}), "
                         f"errors {d['err_rate_before']:.1%} -> {d['err_rate']:.1%}")
    return "\n".join(lines)


def render_markdown(report: Dict[str, Any], diff: Optional[List[Dict[str, Any]]] = None) -> str:
    """An evidence file for docs/roadmap/evidence/: facts of one campaign, to be reviewed and committed by a person."""
    out = [f"# Stress campaign {report['run_id']}", "",
           f"- **Profile:** {report['profile'] or '-'}", f"- **Started:** {report['started'] or '-'}",
           f"- **Job:** {report['job_state'] or '-'}", f"- **Rows:** {report['rows']}", f"- **Verdict:** {report['verdict']} (informational, ADR-0058)", ""]
    out += ["## Drivers", "", "| driver | n | ok | err | 429 | 5xx | p50 | p95 | p99 | guard |", "|---|---|---|---|---|---|---|---|---|---|"]
    for d in report["drivers"]:
        out.append(f"| {d['driver']} | {d['n']} | {d['ok']} | {d['err']} | {d['c429']} | {d['c5xx']} | {_ms(d['p50'])} | {_ms(d['p95'])} | {_ms(d['p99'])} | {'; '.join(d['guard']) or '-'} |")
    for title, items, fmt in (
        ("Budget guard", report["guards"], lambda g: f"- {g['driver']}: {g['detail']}"),
        ("Failures", report["failures"], lambda f: f"- {f['driver']} `{f['id']}`: {f['detail']}"),
        ("Saturation", report["saturation"], lambda s: f"- {'ok' if s['passed'] else '**SATURATED**'} {s['signal']}: {s['detail']}"),
        ("Limitador counters", report["counters"], lambda c: f"- {c['id']}: {c['detail']}"),
        ("Chaos", report.get("chaos", []), lambda c: f"- {'recovered' if c['passed'] else '**DID NOT RECOVER**'} {c['id']}: {c['detail']} ({effects_text(c['effects'])})"),
    ):
        if items:
            out += ["", f"## {title}", ""] + [fmt(i) for i in items]
    if diff:
        out += ["", "## Trend", ""] + [f"- {'**REGRESSED** ' if d['regressed'] else ''}{d['driver']}: p95 {_ms(d['p95_before'])} -> {_ms(d['p95'])}, errors {d['err_rate_before']:.1%} -> {d['err_rate']:.1%}" for d in diff]
    return "\n".join(out) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--rows", default="-", help="file of collected rows, '-' = stdin")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--profile", default="")
    ap.add_argument("--started", default="")
    ap.add_argument("--job-state", default="")
    ap.add_argument("--trend-dir", help="read the previous run of this profile here and save this one")
    ap.add_argument("--evidence-dir", help="write stress-<run id>.md here")
    ap.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    args = ap.parse_args(argv)
    text = sys.stdin.read() if args.rows == "-" else pathlib.Path(args.rows).read_text()
    report = build_report(parse_rows(text), {"run_id": args.run_id, "profile": args.profile, "started": args.started, "job_state": args.job_state})
    previous = load_previous(pathlib.Path(args.trend_dir), args.profile, args.run_id) if args.trend_dir else None
    diff = compare(report, previous)
    notes = []
    try:
        if args.trend_dir and args.run_id:
            notes.append(f"trend saved: {save_trend(report, pathlib.Path(args.trend_dir))}")
        if args.evidence_dir and args.run_id:
            target = pathlib.Path(args.evidence_dir)
            target.mkdir(parents=True, exist_ok=True)
            path = target / f"stress-{args.run_id}.md"
            path.write_text(render_markdown(report, diff))
            notes.append(f"evidence written: {path} (review it, then commit it)")
    except (OSError, ValueError) as exc:  # a read-only checkout (AAP) or a bad run id never loses the report itself
        notes.append(f"not saved: {exc}")
    if args.format == "json":
        print(json.dumps({"report": report, "trend": diff}, indent=1, sort_keys=True))
    elif args.format == "markdown":
        print(render_markdown(report, diff), end="")
    else:
        print(render_text(report, diff))
    for note in notes:
        print(note, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
