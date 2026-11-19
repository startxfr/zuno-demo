#!/usr/bin/env python3
"""The disruptions of a stress campaign: the closed catalogue, its validation, the plan and the provider-cut policy (WP-311).

evaluations/stress/chaos.yaml lists what a campaign may do to the platform while its load runs: delete ONE pod of a named
application, or deny one external provider's addresses to the ai-gateway pods for a bounded time. This module holds the pure
part (no cluster call): it validates the catalogue against an allow-list, orders the disruptions a profile asks for, and builds
the AdminNetworkPolicy of a provider cut. The Ansible tasks (ansible/roles/day3/tasks/stresstest_chaos*.yml) do the deleting and
the applying; they take their plan and their policy from here, so what they can do is what this file lets through.

    python3 platform/testing/stress_chaos.py validate
    python3 platform/testing/stress_chaos.py plan --ids pod-ai-gateway,provider-cut-mistral --start 300 --spacing 150
    python3 platform/testing/stress_chaos.py anp --id provider-cut-mistral --run-id aggressive-20261119-100000

Stdlib and PyYAML. Informational like the rest of the stresstest (ADR-0058): nothing here gates a release.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import socket
import sys
from typing import Any, Callable, Dict, List, Optional

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
CATALOGUE = REPO / "evaluations" / "stress" / "chaos.yaml"

KINDS = ("pod-delete", "provider-cut")
# The applications a disruption may touch, by `app.kubernetes.io/name`, and where they live. Not a model pod, not a node, not a
# whole namespace: a selector outside this list is refused, whatever the catalogue says.
ALLOWED_APPS = {
    "zuno-ai-run": {"ai-gateway", "mcp-gateway", "a2a-gateway"},
    "zuno-ai-gateways": {"praxis"},
    "zuno-openwebui": {"open-webui"},
    "zuno-dify": {"dify-web", "dify-api"},
}
ALLOWED_WORKLOAD_KINDS = ("Deployment", "StatefulSet")
ALLOWED_HOSTS = ("api.mistral.ai", "api.anthropic.com", "api.openai.com", "generativelanguage.googleapis.com")
MAX_DURATION = 300
MAX_RECOVER = 600
ANP_PRIORITY = 90  # the value the repository's earlier negative tests used (docs/roadmap/evidence/wp-292-fallback-live-*.md)
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
HOST_RE = re.compile(r"^[a-z0-9.-]+$")


def load_catalogue(path: pathlib.Path = CATALOGUE) -> Dict[str, Any]:
    data = yaml.safe_load(path.read_text()) or {}
    return data


def _selector_ok(namespace: str, selector: Any) -> Optional[str]:
    if not isinstance(selector, dict) or set(selector) != {"app.kubernetes.io/name"}:
        return "the selector must be exactly {app.kubernetes.io/name: <application>}"
    app = selector["app.kubernetes.io/name"]
    if app not in ALLOWED_APPS.get(namespace, set()):
        return f"{app!r} in {namespace!r} is not an application a disruption may touch (allowed: {sorted(ALLOWED_APPS.get(namespace, set()))})"
    return None


def validate(catalogue: Dict[str, Any]) -> List[str]:
    """The reasons a catalogue is refused (an empty list means it is accepted)."""
    errors: List[str] = []
    seen = set()
    for d in catalogue.get("disruptions") or []:
        ident = str(d.get("id", ""))
        where = f"{ident or '(no id)'}"
        if not NAME_RE.match(ident) or len(ident) > 40:
            errors.append(f"{where}: the id must be a short lower-case name")
        if ident in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(ident)
        kind = d.get("kind")
        if kind not in KINDS:
            errors.append(f"{where}: kind {kind!r} is not one of {KINDS}")
            continue
        if not isinstance(d.get("recover_within"), int) or not 0 < d["recover_within"] <= MAX_RECOVER:
            errors.append(f"{where}: recover_within must be 1..{MAX_RECOVER} seconds")
        if not d.get("description"):
            errors.append(f"{where}: a description is required")
        if kind == "pod-delete":
            problem = _selector_ok(d.get("namespace", ""), d.get("selector"))
            if problem:
                errors.append(f"{where}: {problem}")
            workload = d.get("workload") or {}
            if workload.get("kind") not in ALLOWED_WORKLOAD_KINDS or not NAME_RE.match(str(workload.get("name", ""))):
                errors.append(f"{where}: workload must be a Deployment or a StatefulSet by name")
            if "count" in d:
                errors.append(f"{where}: one pod at a time: `count` is not a setting")
        else:
            subject = d.get("subject") or {}
            problem = _selector_ok(subject.get("namespace", ""), subject.get("selector"))
            if problem:
                errors.append(f"{where}: subject: {problem}")
            if d.get("host") not in ALLOWED_HOSTS:
                errors.append(f"{where}: host {d.get('host')!r} is not an external provider of the platform (allowed: {list(ALLOWED_HOSTS)})")
            if not isinstance(d.get("duration"), int) or not 0 < d["duration"] <= MAX_DURATION:
                errors.append(f"{where}: duration must be 1..{MAX_DURATION} seconds")
    return errors


def plan(catalogue: Dict[str, Any], ids: List[str], start: int = 300, spacing: int = 150) -> List[Dict[str, Any]]:
    """The disruptions of `ids`, in the order asked, each with `at` (seconds after the campaign launch). The next one starts
    `spacing` seconds after the previous one's end (its duration, or its recovery allowance for a pod)."""
    by_id = {d["id"]: d for d in catalogue.get("disruptions") or []}
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        raise ValueError(f"unknown disruption(s): {unknown}; known: {sorted(by_id)}")
    out, at = [], int(start)
    for ident in ids:
        d = dict(by_id[ident])
        d["at"] = at
        out.append(d)
        at += int(d.get("duration", d["recover_within"])) + int(spacing)
    return out


def resolve_cidrs(host: str, resolver: Callable[..., Any] = socket.getaddrinfo) -> List[str]:
    """The IPv4 addresses of `host` as /32 networks, sorted. Raises when none resolves: a provider cut with no address is nothing."""
    if not HOST_RE.match(host):
        raise ValueError(f"{host!r} is not a host name")
    addresses = sorted({info[4][0] for info in resolver(host, 443, family=socket.AF_INET, type=socket.SOCK_STREAM)})
    if not addresses:
        raise ValueError(f"{host} resolves to no IPv4 address")
    return [f"{a}/32" for a in addresses]


def anp_name(disruption_id: str) -> str:
    return f"zuno-stress-chaos-{disruption_id}"[:63].rstrip("-")


def anp_manifest(d: Dict[str, Any], run_id: str, cidrs: List[str]) -> Dict[str, Any]:
    """The AdminNetworkPolicy of a provider cut: Deny egress of the subject pods to the provider's addresses, nothing else.
    Labelled so a reaper can find a left-over one (`zuno.io/stress-chaos=true`)."""
    if d.get("kind") != "provider-cut":
        raise ValueError("only a provider-cut has a policy")
    if not NAME_RE.match(run_id):
        raise ValueError(f"run id {run_id!r} is not a name")
    subject = d["subject"]
    return {
        "apiVersion": "policy.networking.k8s.io/v1alpha1",
        "kind": "AdminNetworkPolicy",
        "metadata": {"name": anp_name(d["id"]), "labels": {"zuno.io/stress-chaos": "true", "zuno.io/stresstest-run": run_id}},
        "spec": {
            "priority": ANP_PRIORITY,
            "subject": {"pods": {
                "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": subject["namespace"]}},
                "podSelector": {"matchLabels": dict(subject["selector"])}}},
            "egress": [{"name": f"deny-{d['host'].replace('.', '-')}"[:100], "action": "Deny", "to": [{"networks": list(cidrs)}]}],
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate", help="check the catalogue against the allow-list")
    pl = sub.add_parser("plan", help="print the ordered disruptions of a profile as JSON")
    pl.add_argument("--ids", required=True)
    pl.add_argument("--start", type=int, default=300)
    pl.add_argument("--spacing", type=int, default=150)
    an = sub.add_parser("anp", help="print the AdminNetworkPolicy of a provider cut (resolves the host now)")
    an.add_argument("--id", required=True)
    an.add_argument("--run-id", required=True)
    args = ap.parse_args(argv)
    catalogue = load_catalogue()
    errors = validate(catalogue)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    if args.cmd == "validate":
        print(f"{len(catalogue.get('disruptions') or [])} disruption(s), all within the allow-list")
        return 0
    try:
        if args.cmd == "plan":
            print(json.dumps(plan(catalogue, [i for i in args.ids.split(",") if i], args.start, args.spacing)))
        else:
            d = next((x for x in catalogue["disruptions"] if x["id"] == args.id), None)
            if d is None:
                raise ValueError(f"unknown disruption {args.id!r}")
            print(json.dumps(anp_manifest(d, args.run_id, resolve_cidrs(d["host"]))))
    except (ValueError, OSError) as exc:
        print(f"stress_chaos: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
