#!/usr/bin/env python3
"""ADR-0534/WP-109 (Phase 3): PEFT/LoRA regression comparison.

Compares a customized model's LM-Eval results against its base model's,
task by task, and produces a versioned regression-report artifact. The
objective is ADR-0534's Phase 3 rule: a fine-tuned candidate "must also
demonstrate that critical existing capabilities have not significantly
regressed" - it is not adopted just because its fine-tuned task improved.

This module deliberately mirrors evaluations/benchmark.py's discipline:
it never runs an evaluation itself (those are live LMEvalJobs,
gitops/charts/models/templates/lmevaljob.yaml), it only consumes their
machine-readable output and writes a comparable artifact.

Results input, per side (base and candidate), mutually exclusive:
  --base-file / --candidate-file PATH
      a local JSON file shaped like an LMEvalJob's `status.results` field
      (either the raw string-wrapped form the CR carries or the parsed
      {"results": {task: {metric: value}}} object) - the repo-testable
      path.
  --base-job / --candidate-job NAME (+ --namespace)
      the live-cluster path: reads the completed LMEvalJob's
      `status.results` via `oc`. Requires state=Complete AND
      reason=Succeeded (ADR-0108: Complete alone also covers a lost run).

Verdict rule, per task present in the BASE results: the candidate must
carry the same task, and for every numeric metric that is not a stderr,
candidate >= base - max_regression (default 0.05 absolute). A task
missing from the candidate is a failure (a capability was not even
re-measured). Tasks only the candidate has are reported informationally -
typically the fine-tuned target task.

Artifact: evaluations/benchmarks/peft-regression-<candidate-label>.json

Run directly; tests: cd evaluations && python3 tests/test_peft_regression.py
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import subprocess
import sys

DEFAULT_OUT_DIR = pathlib.Path(__file__).resolve().parent / "benchmarks"
DEFAULT_MAX_REGRESSION = 0.05
# Metric-name fragments that are uncertainty estimates, not capabilities.
STDERR_MARKERS = ("stderr",)


def _parse_results_payload(payload) -> dict:
    """Normalize any accepted input shape to {task: {metric: value}}.

    Accepts the CR's string-wrapped JSON, the {"results": {...}} object,
    or the bare {task: {...}} mapping.
    """
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("results payload is not a JSON object")
    if "results" in payload and isinstance(payload["results"], dict):
        payload = payload["results"]
    for task, metrics in payload.items():
        if not isinstance(metrics, dict):
            raise ValueError(f"task {task!r} does not map to a metrics object")
    return payload


def load_results_file(path: str) -> dict:
    return _parse_results_payload(json.loads(pathlib.Path(path).read_text()))


def load_results_live(job_name: str, namespace: str) -> dict:
    """Read a completed LMEvalJob's status.results via oc.

    Fails loudly unless state=Complete AND reason=Succeeded - the pair
    ADR-0108 established as the only trustworthy-result signal.
    """
    raw = subprocess.run(
        ["oc", "get", "lmevaljob", job_name, "-n", namespace, "-o", "json"],
        check=True, capture_output=True, text=True,
    ).stdout
    status = json.loads(raw).get("status", {})
    state, reason = status.get("state"), status.get("reason")
    if not (state == "Complete" and reason == "Succeeded"):
        raise RuntimeError(
            f"LMEvalJob {job_name}: state={state} reason={reason} - results "
            "are only trustworthy on Complete+Succeeded (ADR-0108)"
        )
    results = status.get("results")
    if not results:
        raise RuntimeError(
            f"LMEvalJob {job_name}: status.results is empty despite "
            "Complete+Succeeded - see benchmark.py's PVC reader for the "
            "operator-bug fallback path"
        )
    return _parse_results_payload(results)


def compare(base: dict, candidate: dict, max_regression: float) -> dict:
    """Task-by-task regression verdicts. Pure function, fully testable."""
    tasks = {}
    overall_ok = True
    for task, base_metrics in sorted(base.items()):
        cand_metrics = candidate.get(task)
        if cand_metrics is None:
            tasks[task] = {"status": "MISSING_IN_CANDIDATE", "ok": False}
            overall_ok = False
            continue
        metrics = {}
        task_ok = True
        for name, base_val in sorted(base_metrics.items()):
            if any(m in name for m in STDERR_MARKERS):
                continue
            if not isinstance(base_val, (int, float)):
                continue
            cand_val = cand_metrics.get(name)
            if not isinstance(cand_val, (int, float)):
                metrics[name] = {"base": base_val, "candidate": None, "ok": False}
                task_ok = False
                continue
            delta = cand_val - base_val
            ok = delta >= -max_regression
            metrics[name] = {
                "base": base_val, "candidate": cand_val,
                "delta": round(delta, 6), "ok": ok,
            }
            task_ok = task_ok and ok
        tasks[task] = {"status": "COMPARED", "ok": task_ok, "metrics": metrics}
        overall_ok = overall_ok and task_ok
    for task in sorted(set(candidate) - set(base)):
        tasks[task] = {"status": "CANDIDATE_ONLY", "ok": True,
                       "metrics": {k: {"candidate": v} for k, v in
                                   candidate[task].items()
                                   if isinstance(v, (int, float))
                                   and not any(m in k for m in STDERR_MARKERS)}}
    return {"tasks": tasks, "overall": "PASS" if overall_ok else "FAIL",
            "max_regression": max_regression}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="ADR-0534 Phase 3 PEFT/LoRA regression gate")
    p.add_argument("--candidate-label", required=True,
                   help="artifact label, e.g. qwen35-9b-wesh")
    src_b = p.add_mutually_exclusive_group(required=True)
    src_b.add_argument("--base-file")
    src_b.add_argument("--base-job")
    src_c = p.add_mutually_exclusive_group(required=True)
    src_c.add_argument("--candidate-file")
    src_c.add_argument("--candidate-job")
    p.add_argument("--namespace", default="zuno-ai-run")
    p.add_argument("--max-regression", type=float, default=DEFAULT_MAX_REGRESSION)
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = p.parse_args(argv)

    base = (load_results_file(args.base_file) if args.base_file
            else load_results_live(args.base_job, args.namespace))
    candidate = (load_results_file(args.candidate_file) if args.candidate_file
                 else load_results_live(args.candidate_job, args.namespace))

    report = compare(base, candidate, args.max_regression)
    report.update({
        "candidate": args.candidate_label,
        "base_source": args.base_file or f"lmevaljob/{args.base_job}",
        "candidate_source": args.candidate_file or f"lmevaljob/{args.candidate_job}",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"peft-regression-{args.candidate_label}.json"
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print(f"peft-regression: {report['overall']} -> {out_path}")
    for task, verdict in report["tasks"].items():
        print(f"  {task}: {verdict['status']} ok={verdict['ok']}")
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
