#!/usr/bin/env python3
"""ADR-0305 (roadmap WP-40 Part A) benchmark harness: "Every candidate
model or adapter is benchmarked before routing-policy promotion: LM-Eval
task suites (ADR-0108) plus the target agents' acceptance gates
(ADR-0107), producing a versioned, comparable result artifact stored
alongside the Model Registry entry. A candidate without a benchmark
artifact cannot be referenced by a routing-policy change."

This module produces that artifact; it never runs LM-Eval itself (that is
a live-cluster LMEvalJob, gitops/charts/models/templates/lmevaljob.yaml)
and never runs an agent's scenarios/security checks itself (that is
evaluations/<agent>/run_acceptance_gate.py, reused unmodified via
evaluations/quality_gate.py - same "consume the machine-readable output,
never reimplement" discipline that module already established). This is
purely an orchestrator + artifact writer.

LM-Eval results input, two mutually exclusive sources:
  --lm-eval-results-file PATH   a local JSON file shaped exactly like an
                                 LMEvalJob's own `status.results` field
                                 (task name -> {metric: value}) - the
                                 primary, fully repo-testable path (no
                                 live GPU/LMEvalJob exists in this
                                 development environment).
  --lm-eval-job-name NAME (+ --namespace) the live-cluster alternative:
                                 reads a completed LMEvalJob's real results
                                 directly from its `outputs.pvcManaged` PVC
                                 via a short-lived reader pod, not from the
                                 CR's own `status.results` field - a real,
                                 confirmed-live TrustyAI operator bug
                                 (OpenShift AI 3.5.0-ea.2) leaves that field
                                 permanently unset even on a genuinely
                                 succeeded run (ADR-0108's dated note has
                                 the full trace). What an operator runs
                                 against a real completed LMEvalJob.
  (neither)                     lm_eval is recorded as {} in the
                                 artifact - a candidate can still be
                                 benchmarked on agent gates alone if no
                                 LM-Eval task suite applies.

Result artifact schema, written to evaluations/benchmarks/<candidate>.json
(directory created if missing; MODEL REGISTRY LINKAGE is informational
metadata copied from components/mlops's own push-registry stage output,
never re-derived or re-verified against a live registry here):

    {
      "candidate": "comage-lora-run-0001",
      "created_at": "2026-08-15T12:00:00+00:00",
      "registry_model_name": "comage-lora",       # optional
      "registry_model_version": "run-0001",       # optional
      "lm_eval": {"mmlu": {"acc": 0.71}},          # {} if no LM-Eval task ran
      "agent_gates": {
        "comage": {"overall": "PASS", "scenario_rate": 0.85, ...}
      },
      "overall": "PASS" | "FAIL"
    }

`overall` is PASS only if every requested agent gate is PASS (lm_eval has
no pass/fail threshold of its own here - ADR-0304/WP-40 Part B is what
turns raw LM-Eval numbers into a quality signal compared against declared
objectives, not this module).

Usage:

    python3 evaluations/benchmark.py --candidate comage-lora-run-0001 \
        --agent comage \
        --lm-eval-results-file /path/to/lm-eval-results.json \
        --registry-model-name comage-lora --registry-model-version run-0001

    # policy-enforcement mode (ADR-0305's "no artifact, no promotion"
    # rule; wired into .github/workflows/lint.yml's quality-gate job):
    python3 evaluations/benchmark.py --check-policy
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import yaml

EVALUATIONS_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = EVALUATIONS_DIR.parent
BENCHMARKS_DIR = EVALUATIONS_DIR / "benchmarks"
MODEL_ROUTING_POLICY_PATH = REPO_ROOT / "policies" / "model-routing" / "model-routing-policy.yaml"

sys.path.insert(0, str(EVALUATIONS_DIR))
import quality_gate  # noqa: E402


class BenchmarkError(Exception):
    pass


def read_lm_eval_results_from_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


_RESULTS_READER_IMAGE = (
    "image-registry.openshift-image-registry.svc:5000/zuno-ai-build/ubi9-ubi-minimal:9"
)


def read_lm_eval_results_from_cluster(job_name: str, namespace: str = "zuno-ai-run") -> Dict[str, Any]:
    """Operator path: reads a completed LMEvalJob's real results.

    ADR-0108 known operator gap (confirmed live 2026-08-22, reproduced
    cleanly against a healthy predictor after ruling out an earlier false
    lead - a cordoned GPU node that had been contaminating every prior
    observation): the TrustyAI operator (OpenShift AI 3.5.0-ea.2) never
    persists a completed job's real status to the LMEvalJob CR. The
    driver's own log shows it computing and logging a correct
    `state: Complete, reason: Succeeded` update with full results, but the
    CR itself stays at `state: Scheduled` indefinitely afterwards (watched
    for 2+ minutes past the driver's own "job completed" log line, no
    change) - not a reconcile-lag artifact. RBAC is not the blocker
    (`default` SA in the job's namespace can patch `lmevaljobs/status`);
    the actual failure mode is internal to the operator/driver hand-off
    and out of this repo's control.

    Workaround: the job's own `outputs.pvcManaged` PVC (named
    `<job_name>-pvc`, gitops/charts/models/templates/lmevaljob.yaml) holds
    the real results file (`<model>/results_<timestamp>.json`, lm-eval-
    harness's own native output) completely independent of the broken CR
    field.

    Because the CR's `state` also never reaches a value the operator acts
    on to tear the driver pod down, the driver pod (named exactly
    `job_name`, confirmed via `.status.podName`) stays alive indefinitely -
    and since the PVC is `ReadWriteOnce`, a *separate* reader pod cannot
    mount it while that driver pod is still holding it (confirmed live:
    `FailedAttachVolume ... Multi-Attach error ... already used by
    pod(s) <job_name>`). So the primary path execs directly into the
    still-running driver pod (no new volume attach needed); only if that
    pod is already gone (e.g. cleaned up by hand, or a future operator fix
    that actually completes the lifecycle) does this fall back to a
    short-lived reader pod that mounts the now-unclaimed PVC itself. No new
    Python Kubernetes-client dependency either way, consistent with how
    ansible/roles/models/tasks/precheck.yml reads the same CRD via
    kubernetes.core."""
    pvc_name = f"{job_name}-pvc"
    check = subprocess.run(
        ["oc", "get", "pvc", pvc_name, "-n", namespace, "-o", "name"],
        capture_output=True, text=True,
    )
    if check.returncode != 0:
        raise BenchmarkError(
            f"no output PVC {pvc_name!r} for LMEvalJob {job_name!r} in namespace {namespace!r} - "
            f"has it run yet? ({check.stderr.strip()})"
        )

    driver_pod_check = subprocess.run(
        ["oc", "get", "pod", job_name, "-n", namespace, "-o", "name"],
        capture_output=True, text=True,
    )
    if driver_pod_check.returncode == 0:
        return _read_results_via_exec(job_name, namespace)
    return _read_results_from_output_pvc(job_name, pvc_name, namespace)


def _find_latest_results_file_cmd(mount_path: str) -> str:
    return (
        f"f=$(find {mount_path} -name 'results_*.json' | sort | tail -1); "
        f"if [ -z \"$f\" ]; then echo 'no results_*.json found under {mount_path}' >&2; exit 1; fi; "
        "cat \"$f\""
    )


# The LMEvalJob chart (gitops/charts/models/templates/lmevaljob.yaml) does
# not set spec.pod.container.volumeMounts for the operator-managed
# `outputs.pvcManaged` volume - the operator's own driver image mounts it
# at this fixed path (confirmed live via `oc exec ... find /opt/app-root/
# src/output`), not the `/output` mountPath this module chooses for its
# own reader-pod fallback below.
_DRIVER_POD_OUTPUT_MOUNT = "/opt/app-root/src/output"


def _read_results_via_exec(job_name: str, namespace: str) -> Dict[str, Any]:
    proc = subprocess.run(
        [
            "oc", "exec", job_name, "-n", namespace, "-c", "main", "--",
            "sh", "-c", _find_latest_results_file_cmd(_DRIVER_POD_OUTPUT_MOUNT),
        ],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise BenchmarkError(
            f"could not read results from driver pod {job_name!r} in namespace {namespace!r}: {proc.stderr.strip()}"
        )
    if not proc.stdout.strip():
        raise BenchmarkError(f"driver pod {job_name!r} produced no results output")
    raw = json.loads(proc.stdout)
    if isinstance(raw, dict) and "results" in raw:
        return raw["results"]
    return raw


def _read_results_from_output_pvc(job_name: str, pvc_name: str, namespace: str) -> Dict[str, Any]:
    reader_pod = f"{job_name}-results-reader"
    manifest = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": reader_pod,
            "namespace": namespace,
            "labels": {"app.kubernetes.io/component": "benchmark-results-reader"},
        },
        "spec": {
            "restartPolicy": "Never",
            "containers": [
                {
                    "name": "reader",
                    "image": _RESULTS_READER_IMAGE,
                    "command": ["sh", "-c", _find_latest_results_file_cmd("/output")],
                    "volumeMounts": [{"name": "outputs", "mountPath": "/output", "readOnly": True}],
                }
            ],
            "volumes": [
                {"name": "outputs", "persistentVolumeClaim": {"claimName": pvc_name, "readOnly": True}}
            ],
        },
    }
    subprocess.run(
        ["oc", "delete", "pod", reader_pod, "-n", namespace, "--ignore-not-found", "--wait=true"],
        capture_output=True, text=True,
    )
    try:
        apply_proc = subprocess.run(
            ["oc", "apply", "-f", "-"], input=json.dumps(manifest), capture_output=True, text=True,
        )
        if apply_proc.returncode != 0:
            raise BenchmarkError(f"could not create results-reader pod {reader_pod!r}: {apply_proc.stderr.strip()}")

        wait_proc = subprocess.run(
            [
                "oc", "wait", "-n", namespace, f"pod/{reader_pod}",
                "--for=jsonpath={.status.phase}=Succeeded", "--timeout=120s",
            ],
            capture_output=True, text=True,
        )
        logs_proc = subprocess.run(["oc", "logs", reader_pod, "-n", namespace], capture_output=True, text=True)
        if wait_proc.returncode != 0:
            raise BenchmarkError(
                f"results-reader pod {reader_pod!r} did not reach Succeeded: {wait_proc.stderr.strip()} "
                f"(pod logs: {logs_proc.stdout[-500:]!r})"
            )
        if not logs_proc.stdout.strip():
            raise BenchmarkError(f"results-reader pod {reader_pod!r} produced no output")

        raw = json.loads(logs_proc.stdout)
    finally:
        subprocess.run(
            ["oc", "delete", "pod", reader_pod, "-n", namespace, "--ignore-not-found"],
            capture_output=True, text=True,
        )

    if isinstance(raw, dict) and "results" in raw:
        return raw["results"]
    return raw


def run_agent_gates(agents: List[str], candidate: str) -> Dict[str, Dict[str, Any]]:
    gates: Dict[str, Dict[str, Any]] = {}
    for agent in agents:
        gates[agent] = quality_gate.evaluate(agent, candidate=candidate)
    return gates


def build_artifact(
    candidate: str,
    lm_eval: Dict[str, Any],
    agent_gates: Dict[str, Dict[str, Any]],
    registry_model_name: Optional[str] = None,
    registry_model_version: Optional[str] = None,
) -> Dict[str, Any]:
    overall = "PASS" if agent_gates and all(g.get("overall") == "PASS" for g in agent_gates.values()) else "FAIL"
    return {
        "candidate": candidate,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "registry_model_name": registry_model_name,
        "registry_model_version": registry_model_version,
        "lm_eval": lm_eval,
        "agent_gates": agent_gates,
        "overall": overall,
    }


def write_artifact(artifact: Dict[str, Any], out_dir: pathlib.Path = BENCHMARKS_DIR) -> pathlib.Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{artifact['candidate']}.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


def load_benchmark_artifact(candidate: str, benchmarks_dir: pathlib.Path = BENCHMARKS_DIR) -> Optional[Dict[str, Any]]:
    path = benchmarks_dir / f"{candidate}.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def check_policy_artifacts(
    policy_path: pathlib.Path = MODEL_ROUTING_POLICY_PATH, benchmarks_dir: pathlib.Path = BENCHMARKS_DIR
) -> List[str]:
    """ADR-0305's own enforcement bullet: "A candidate without a benchmark
    artifact cannot be referenced by a routing-policy change." Every
    `adapter:` name declared in policies/model-routing/model-routing-policy.yaml
    must have a matching, PASSing evaluations/benchmarks/<adapter>.json.
    Returns a list of violation messages - empty means clean (including
    the common case today: adapters: [] has nothing to check)."""
    def _display(path: pathlib.Path) -> str:
        try:
            return str(path.relative_to(REPO_ROOT))
        except ValueError:
            return str(path)

    violations: List[str] = []
    if not policy_path.exists():
        return violations
    with policy_path.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}
    for entry in config.get("adapters", []) or []:
        adapter = entry.get("adapter")
        if not adapter:
            continue
        artifact = load_benchmark_artifact(adapter, benchmarks_dir)
        if artifact is None:
            violations.append(
                f"adapter {adapter!r} (agent={entry.get('agent')!r}, task={entry.get('task')!r}) is declared in "
                f"{_display(policy_path)} but has no benchmark artifact at "
                f"{_display(benchmarks_dir)}/{adapter}.json (ADR-0305: no artifact, no promotion)"
            )
        elif artifact.get("overall") != "PASS":
            violations.append(
                f"adapter {adapter!r}'s benchmark artifact exists but overall={artifact.get('overall')!r}, not PASS "
                f"(ADR-0305: a candidate must pass its benchmark before its routing-policy declaration is honored)"
            )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-0305 benchmark harness")
    parser.add_argument("--candidate", help="candidate label, e.g. comage-lora-run-0001")
    parser.add_argument("--agent", action="append", default=[], help="target agent to gate (repeatable)")
    parser.add_argument("--lm-eval-results-file", default=None)
    parser.add_argument("--lm-eval-job-name", default=None)
    parser.add_argument("--namespace", default="zuno-ai-run")
    parser.add_argument("--registry-model-name", default=None)
    parser.add_argument("--registry-model-version", default=None)
    parser.add_argument("--out-dir", default=str(BENCHMARKS_DIR))
    parser.add_argument(
        "--check-policy", action="store_true",
        help="ADR-0305 enforcement mode: verify every declared adapter in "
        "policies/model-routing/model-routing-policy.yaml has a passing benchmark artifact, then exit",
    )
    args = parser.parse_args()

    if args.check_policy:
        violations = check_policy_artifacts()
        if violations:
            for v in violations:
                print(f"POLICY VIOLATION: {v}", file=sys.stderr)
            return 1
        print("RESULT: PASS - every declared adapter has a passing benchmark artifact.")
        return 0

    if not args.candidate:
        parser.error("--candidate is required unless --check-policy is given")
    if args.lm_eval_results_file and args.lm_eval_job_name:
        parser.error("--lm-eval-results-file and --lm-eval-job-name are mutually exclusive")

    try:
        if args.lm_eval_results_file:
            lm_eval = read_lm_eval_results_from_file(args.lm_eval_results_file)
        elif args.lm_eval_job_name:
            lm_eval = read_lm_eval_results_from_cluster(args.lm_eval_job_name, args.namespace)
        else:
            lm_eval = {}

        agent_gates = run_agent_gates(args.agent, args.candidate)
    except (BenchmarkError, quality_gate.QualityGateError) as exc:
        print(f"BENCHMARK ERROR: {exc}", file=sys.stderr)
        return 2

    artifact = build_artifact(
        args.candidate, lm_eval, agent_gates, args.registry_model_name, args.registry_model_version
    )
    path = write_artifact(artifact, pathlib.Path(args.out_dir))

    print(f"Benchmark artifact for candidate={args.candidate!r} written to {path}")
    print(f"  lm_eval task suites: {list(lm_eval.keys()) or '(none)'}")
    for agent, gate in agent_gates.items():
        print(f"  agent={agent}: {gate['overall']} (scenario_rate={gate.get('scenario_rate', 0):.0%})")
    print(f"OVERALL: {artifact['overall']}")
    print(json.dumps(artifact))

    return 0 if artifact["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
