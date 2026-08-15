#!/usr/bin/env python3
"""ADR-0304 (roadmap WP-40 Part B) routing-optimization report: "Routing
policy gains explicit quality/cost/latency objectives per task class; a
reporting job compares live operational metrics (ADR-0029) and benchmark
artifacts (ADR-0305) against those objectives and emits a recommended
policy diff. Applying a recommendation is a normal reviewed GitOps
change. No component changes routing autonomously (that is ADR-0309's
separately governed scope)."

This module only ever READS policies/model-routing/model-routing-policy.yaml
and evaluations/benchmarks/*.json and WRITES a report - it never writes to
the policy file itself. "Task class" here is the same (agent, task) pair
`adapters:`/`objectives:` entries already use. Quality is measured at
agent granularity (evaluations/quality_gate.py's scenario_rate covers an
agent's whole ADR-0027 acceptance suite via its primary task, not a
specific secondary task in isolation) - a benchmark artifact's
`agent_gates[agent].scenario_rate` is therefore compared against every
task-class objective declared for that same agent, a documented
simplification rather than false per-task precision.

Live operational metrics input (D13: file-input default, the primary/
fully repo-testable path - this repo's OTel Collector chart has no
queryable long-term store wired in, see MEMORY.md):

    --metrics-file PATH   a JSON snapshot shaped
                           {agent: {task: {"cost_usd_per_1k": float,
                                            "latency_ms_p95": float}}}
                           - what an operator produces from a PromQL query
                           against zuno.model_cost_usd/zuno.latency_ms
                           (components/ai-gateway/app/telemetry.py).
    --prometheus-url URL  optional live-cluster alternative for an
                           operator with a reachable Prometheus query
                           endpoint (not exercised in this environment).

Usage:

    python3 evaluations/routing_report.py --metrics-file metrics.json \
        [--output routing_report.json]

Recommendation kinds:
  - "downgrade": the CURRENTLY declared adapter (or base model, if none
    declared) for a task class is violating its own cost ceiling or
    latency target per live metrics.
  - "upgrade": a benchmarked candidate NOT currently declared for a task
    class clears that task class's quality floor.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import yaml

EVALUATIONS_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = EVALUATIONS_DIR.parent
BENCHMARKS_DIR = EVALUATIONS_DIR / "benchmarks"
MODEL_ROUTING_POLICY_PATH = REPO_ROOT / "policies" / "model-routing" / "model-routing-policy.yaml"


@dataclass
class Objective:
    agent: str
    task: str
    quality_floor: Optional[float] = None
    cost_ceiling_usd_per_1k: Optional[float] = None
    latency_target_ms_p95: Optional[float] = None


@dataclass
class Recommendation:
    agent: str
    task: str
    kind: str  # "downgrade" | "upgrade"
    reason: str
    candidate: Optional[str] = None


def load_policy(policy_path: pathlib.Path = MODEL_ROUTING_POLICY_PATH) -> Dict[str, Any]:
    if not policy_path.exists():
        return {"adapters": [], "objectives": []}
    with policy_path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {"adapters": [], "objectives": []}


def load_objectives(policy: Dict[str, Any]) -> List[Objective]:
    return [
        Objective(
            agent=o["agent"],
            task=o["task"],
            quality_floor=o.get("quality_floor"),
            cost_ceiling_usd_per_1k=o.get("cost_ceiling_usd_per_1k"),
            latency_target_ms_p95=o.get("latency_target_ms_p95"),
        )
        for o in policy.get("objectives", []) or []
        if o.get("agent") and o.get("task")
    ]


def current_adapters(policy: Dict[str, Any]) -> Dict[tuple, str]:
    return {(a["agent"], a["task"]): a["adapter"] for a in policy.get("adapters", []) or [] if a.get("agent") and a.get("task") and a.get("adapter")}


def load_metrics_snapshot(path: Optional[str]) -> Dict[str, Dict[str, Dict[str, float]]]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_metrics_from_prometheus(url: str) -> Dict[str, Dict[str, Dict[str, float]]]:  # pragma: no cover - live-cluster only
    """Documented seam for an operator with a reachable Prometheus query
    endpoint (D13) - not exercised in this environment (no queryable
    long-term metrics store is wired in this repo's OTel Collector
    chart). Left unimplemented rather than faked: raising here is more
    honest than returning a plausible-looking empty snapshot."""
    raise NotImplementedError(
        f"--prometheus-url is a documented operator seam, not implemented in this repo "
        f"(no reachable Prometheus query endpoint at {url!r} in this environment - use --metrics-file instead)"
    )


def scan_benchmark_artifacts(benchmarks_dir: pathlib.Path = BENCHMARKS_DIR) -> List[Dict[str, Any]]:
    if not benchmarks_dir.exists():
        return []
    artifacts = []
    for path in sorted(benchmarks_dir.glob("*.json")):
        with path.open("r", encoding="utf-8") as fh:
            artifacts.append(json.load(fh))
    return artifacts


def generate_report(
    objectives: List[Objective],
    metrics: Dict[str, Dict[str, Dict[str, float]]],
    artifacts: List[Dict[str, Any]],
    adapters: Dict[tuple, str],
) -> List[Recommendation]:
    recommendations: List[Recommendation] = []

    for obj in objectives:
        key = (obj.agent, obj.task)
        live = metrics.get(obj.agent, {}).get(obj.task)
        incumbent = adapters.get(key, "(base model)")

        if live:
            if obj.cost_ceiling_usd_per_1k is not None and live.get("cost_usd_per_1k", 0.0) > obj.cost_ceiling_usd_per_1k:
                recommendations.append(Recommendation(
                    obj.agent, obj.task, "downgrade",
                    f"{incumbent}: live cost ${live['cost_usd_per_1k']:.5f}/1k tokens exceeds ceiling ${obj.cost_ceiling_usd_per_1k:.5f}/1k",
                    candidate=incumbent,
                ))
            if obj.latency_target_ms_p95 is not None and live.get("latency_ms_p95", 0.0) > obj.latency_target_ms_p95:
                recommendations.append(Recommendation(
                    obj.agent, obj.task, "downgrade",
                    f"{incumbent}: live P95 latency {live['latency_ms_p95']:.0f}ms exceeds target {obj.latency_target_ms_p95:.0f}ms",
                    candidate=incumbent,
                ))

        if obj.quality_floor is None:
            continue
        for artifact in artifacts:
            candidate = artifact.get("candidate")
            if not candidate or candidate == incumbent:
                continue
            gate = artifact.get("agent_gates", {}).get(obj.agent)
            if not gate or gate.get("overall") != "PASS":
                continue
            quality = gate.get("scenario_rate", 0.0)
            if quality >= obj.quality_floor:
                recommendations.append(Recommendation(
                    obj.agent, obj.task, "upgrade",
                    f"candidate {candidate!r} clears quality floor {obj.quality_floor:.0%} "
                    f"(scenario_rate={quality:.0%}) and is not the current {incumbent!r}",
                    candidate=candidate,
                ))

    return recommendations


def build_report(recommendations: List[Recommendation]) -> Dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "recommendation_count": len(recommendations),
        "recommendations": [asdict(r) for r in recommendations],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-0304 routing-optimization report")
    parser.add_argument("--metrics-file", default=None, help="JSON snapshot of live ai-gateway metrics (primary path)")
    parser.add_argument("--prometheus-url", default=None, help="live Prometheus query endpoint (operator-only seam)")
    parser.add_argument("--benchmarks-dir", default=str(BENCHMARKS_DIR))
    parser.add_argument("--policy-path", default=str(MODEL_ROUTING_POLICY_PATH))
    parser.add_argument("--output", default=None, help="write the report JSON here (default: stdout only)")
    args = parser.parse_args()

    if args.metrics_file and args.prometheus_url:
        parser.error("--metrics-file and --prometheus-url are mutually exclusive")

    policy = load_policy(pathlib.Path(args.policy_path))
    objectives = load_objectives(policy)
    adapters = current_adapters(policy)
    artifacts = scan_benchmark_artifacts(pathlib.Path(args.benchmarks_dir))

    if args.prometheus_url:
        metrics = load_metrics_from_prometheus(args.prometheus_url)
    else:
        metrics = load_metrics_snapshot(args.metrics_file)

    recommendations = generate_report(objectives, metrics, artifacts, adapters)
    report = build_report(recommendations)

    print(f"{len(objectives)} objective(s), {len(artifacts)} benchmark artifact(s) scanned.")
    if not recommendations:
        print("No recommendations - every task class is within its declared objectives.")
    for rec in recommendations:
        print(f"  [{rec.kind.upper()}] {rec.agent}/{rec.task}: {rec.reason}")

    if args.output:
        out_path = pathlib.Path(args.output)
        with out_path.open("w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, sort_keys=True)
            fh.write("\n")
        print(f"Report written to {out_path}")
    else:
        print(json.dumps(report))

    return 0


if __name__ == "__main__":
    sys.exit(main())
