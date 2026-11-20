#!/usr/bin/env python3
"""Estimate the size of the Kuadrant wasm EnvoyFilter of the MaaS gateway from the rendered charts. No cluster access.

Kuadrant renders ONE EnvoyFilter, `openshift-ingress/kuadrant-maas-default-gateway`, whose wasm plugin configuration lists, for every
HTTPRoute attached to the gateway, one action set per route match, and in each of them one action per token limit of the
route's model (the MaaSSubscriptions that name it). The object grows with matches x limits x listeners, and an object that is too
big is refused by the API server ("failed to update envoyfilter object"): the limits then are NOT USED and nothing is counted.

Model (calibrated on the live object of 2026-11-20, 3.92 MB for today's inputs):

    bytes = 1.06 * sum over routes( listeners * matches * (3609 + 3940 * limits) )

  - a route is the HTTPRoute of an LLMInferenceService attached to `maas-default-gateway` (spec.router.route.http.spec):
    matches = sum over its rules of len(matches); limits = the MaaSSubscriptions whose modelRefs name that model;
  - the vendor routes are constants: 2 ExternalModel routes (4 matches, 1 limit each) and maas-api-route (5 matches, 1 limit:
    the default deny);
  - listeners = 2 when the openshift-ai chart value maasGateway.externalHostnameListener.enabled is true, else 1.

Usage:

    helm template m gitops/charts/models [-f values.yaml] | python3 platform/models/maas_wasm_size.py -
    python3 platform/models/maas_wasm_size.py rendered.yaml --max-bytes 1400000      # exit 1 above the limit
    python3 platform/models/maas_wasm_size.py rendered.yaml --listeners 2

Without --listeners the count is read from gitops/charts/openshift-ai/values.yaml, then from each --openshift-ai-values file
(the later wins), as the chart is rendered with its defaults unless told otherwise.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Dict, Iterable, List, Optional

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
OPENSHIFT_AI_VALUES = REPO / "gitops" / "charts" / "openshift-ai" / "values.yaml"
GATEWAY = "maas-default-gateway"
FIXED_BYTES = 3609      # per match: the action set without its limits
PER_LIMIT_BYTES = 3940  # per match and per limit: one rate-limit action
CALIBRATION = 1.06      # live object of 2026-11-20 over the sum of the terms
# The routes this repository does not render: 2 ExternalModel routes and the MaaS API route (default deny).
VENDOR_ROUTES = (
    {"name": "external-model-route-1", "matches": 4, "limits": 1},
    {"name": "external-model-route-2", "matches": 4, "limits": 1},
    {"name": "maas-api-route", "matches": 5, "limits": 1},
)


def route_bytes(matches: int, limits: int, listeners: int) -> float:
    """Estimated bytes of one route, calibration included."""
    return CALIBRATION * listeners * matches * (FIXED_BYTES + PER_LIMIT_BYTES * limits)


def load_documents(paths: Iterable[str]) -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    for path in paths:
        text = sys.stdin.read() if path == "-" else pathlib.Path(path).read_text()
        docs += [d for d in yaml.safe_load_all(text) if isinstance(d, dict)]
    return docs


def attached_to_gateway(route_spec: Dict[str, Any]) -> bool:
    return any(ref.get("name") == GATEWAY for ref in route_spec.get("parentRefs") or [])


def model_routes(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """[{name, matches, limits}] for every LLMInferenceService route on the MaaS gateway, in document order."""
    subscriptions = [d for d in docs if d.get("kind") == "MaaSSubscription"]
    routes = []
    for doc in docs:
        if doc.get("kind") != "LLMInferenceService":
            continue
        name = (doc.get("metadata") or {}).get("name", "?")
        spec = ((((doc.get("spec") or {}).get("router") or {}).get("route") or {}).get("http") or {}).get("spec") or {}
        if not spec or not attached_to_gateway(spec):
            continue
        matches = sum(len(rule.get("matches") or []) for rule in spec.get("rules") or [])
        limits = sum(1 for sub in subscriptions for ref in (sub.get("spec") or {}).get("modelRefs") or [] if ref.get("name") == name)
        routes.append({"name": name, "matches": matches, "limits": limits})
    return routes


def listeners_from_values(paths: Iterable[pathlib.Path]) -> int:
    """2 when maasGateway.externalHostnameListener.enabled is true in the last file that sets it, else 1."""
    enabled = False
    for path in paths:
        data = yaml.safe_load(path.read_text()) or {}
        value = (((data.get("maasGateway") or {}).get("externalHostnameListener") or {}) or {}).get("enabled")
        if value is not None:
            enabled = str(value).lower() == "true"
    return 2 if enabled else 1


def estimate(docs: List[Dict[str, Any]], listeners: int) -> Dict[str, Any]:
    rows = []
    for route in model_routes(docs) + [dict(r) for r in VENDOR_ROUTES]:
        rows.append(dict(route, bytes=round(route_bytes(route["matches"], route["limits"], listeners))))
    return {"listeners": listeners, "routes": rows, "total_bytes": sum(r["bytes"] for r in rows)}


def render_table(result: Dict[str, Any]) -> str:
    width = max(len(r["name"]) for r in result["routes"])
    lines = [f"{'route':<{width}}  {'matches':>7}  {'limits':>6}  {'bytes':>10}"]
    lines += [f"{r['name']:<{width}}  {r['matches']:>7}  {r['limits']:>6}  {r['bytes']:>10,}" for r in result["routes"]]
    lines.append(f"{'TOTAL':<{width}}  {'':>7}  {'':>6}  {result['total_bytes']:>10,}  "
                 f"({result['total_bytes'] / 1e6:.2f} MB, {result['listeners']} listener(s))")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="+", help="rendered YAML of the models chart ('-' reads stdin)")
    ap.add_argument("--listeners", type=int, choices=(1, 2), help="gateway listeners (default: from the openshift-ai values)")
    ap.add_argument("--openshift-ai-values", action="append", default=[], metavar="FILE",
                    help="values file(s) applied over the chart's defaults to read maasGateway.externalHostnameListener.enabled")
    ap.add_argument("--max-bytes", type=int, help="exit 1 when the estimate is above this many bytes")
    ap.add_argument("--json", action="store_true", help="machine output")
    args = ap.parse_args(argv)

    listeners = args.listeners or listeners_from_values([OPENSHIFT_AI_VALUES] + [pathlib.Path(p) for p in args.openshift_ai_values])
    result = estimate(load_documents(args.files), listeners)
    if args.max_bytes is not None:
        result["max_bytes"] = args.max_bytes
        result["ok"] = result["total_bytes"] <= args.max_bytes
    print(json.dumps(result, indent=2) if args.json else render_table(result))
    if args.max_bytes is not None and not result["ok"]:
        print(f"TOO BIG: {result['total_bytes']:,} bytes is above the {args.max_bytes:,} limit", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
