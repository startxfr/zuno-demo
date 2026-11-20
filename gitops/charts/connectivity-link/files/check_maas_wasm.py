#!/usr/bin/env python3
"""Read-only live check of the Kuadrant wasm EnvoyFilters in openshift-ingress, through `oc`.

When an EnvoyFilter grows too big the API server refuses its update ("failed to update envoyfilter object"), the object stays
stale, and the limits added since are NOT USED: nothing is counted for them, silently. This check says so:

  - every EnvoyFilter of `openshift-ingress` whose name starts with `kuadrant-` (one per gateway: kuadrant-maas-default-gateway,
    kuadrant-zuno-agent-gateway, ...): generation, size in bytes (the object as compact JSON, managedFields left out) and the number
    of action sets of its wasm configuration (a JSON string at
    spec.configPatches[0].patch.value.typed_config.value.config.configuration.value);
  - the Limitador CR `kuadrant-system/limitador` (spec.limits): one line per limit, COUNTED when every descriptor key of its
    conditions (regex limit\\.[A-Za-z0-9_]+__[0-9a-f]{8}) appears in the configuration of ANY of those EnvoyFilters, else NOT USED;
    a limit that names no key at all is NO-KEY (a warning, not a failure: nothing can be said about it);
  - the number of "failed to update envoyfilter object" lines in the last --log-window (default 30m) of the kuadrant operator log. ONLY the
    count is printed: each such line carries the whole object.

Exit code 1 when a limit is NOT USED, an EnvoyFilter is above --max-bytes (default 1,400,000) or that count is above 0; 2 when `oc`
cannot answer. It only runs `oc get` and `oc logs`.

    python3 platform/models/check_maas_wasm.py [--max-bytes N] [--log-window 20m] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional

ENVOYFILTER_NAMESPACE = "openshift-ingress"
ENVOYFILTER_PREFIX = "kuadrant-"
DEFAULT_MAX_BYTES = 1_400_000
LIMITADOR = ("kuadrant-system", "limitador")
OPERATOR = ("openshift-operators", "deploy/kuadrant-operator-controller-manager")
DEFAULT_LOG_WINDOW = "30m"
LOG_MARKER = "failed to update envoyfilter object"
KEY_RE = re.compile(r"limit\.[A-Za-z0-9_]+__[0-9a-f]{8}")

Runner = Callable[[List[str]], str]


class OcError(RuntimeError):
    pass


def run_oc(args: List[str]) -> str:
    try:
        proc = subprocess.run(["oc"] + args, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OcError(f"oc {args[0]}: {type(exc).__name__}") from exc
    if proc.returncode != 0:
        raise OcError(f"oc {' '.join(args[:3])} ... failed: {proc.stderr.strip()[:200]}")
    return proc.stdout


def wasm_configuration(envoyfilter: Dict[str, Any]) -> str:
    """The wasm plugin configuration string of the first config patch ('' when the path is not there)."""
    try:
        return str(envoyfilter["spec"]["configPatches"][0]["patch"]["value"]["typed_config"]["value"]["config"]["configuration"]["value"])
    except (KeyError, IndexError, TypeError):
        return ""


def action_sets(configuration: str) -> Optional[int]:
    """Number of action sets of the configuration, None when it is not the expected JSON."""
    try:
        sets = json.loads(configuration).get("actionSets")
    except (ValueError, AttributeError):
        return None
    return len(sets) if isinstance(sets, list) else None


def limit_keys(limit: Dict[str, Any]) -> List[str]:
    """The descriptor keys named by a Limitador limit's conditions."""
    return sorted(set(KEY_RE.findall(" ".join(str(c) for c in limit.get("conditions") or []))))


def limit_rows(limitador: Dict[str, Any], configurations: List[str]) -> List[Dict[str, Any]]:
    """One row per Limitador limit. status: COUNTED (all its keys appear in some configuration), NOT USED, or NO-KEY."""
    rows = []
    for limit in (limitador.get("spec") or {}).get("limits") or []:
        keys = limit_keys(limit)
        if not keys:
            status = "NO-KEY"
        elif any(all(key in configuration for key in keys) for configuration in configurations):
            status = "COUNTED"
        else:
            status = "NOT USED"
        rows.append({"namespace": limit.get("namespace", ""), "name": limit.get("name", ""), "max_value": limit.get("max_value"),
                     "seconds": limit.get("seconds"), "keys": len(keys), "status": status})
    return rows


def failed_updates(log_text: str) -> int:
    """How many lines of the operator log say the EnvoyFilter update failed. The lines themselves are never kept."""
    return sum(1 for line in log_text.splitlines() if LOG_MARKER in line)


def object_size(obj: Dict[str, Any]) -> int:
    slim = json.loads(json.dumps(obj))
    (slim.get("metadata") or {}).pop("managedFields", None)
    return len(json.dumps(slim, separators=(",", ":")).encode())


def envoyfilters(run: Runner) -> List[Dict[str, Any]]:
    """The kuadrant-* EnvoyFilters of openshift-ingress, sorted by name."""
    items = json.loads(run(["get", "envoyfilter", "-n", ENVOYFILTER_NAMESPACE, "-o", "json"])).get("items") or []
    return sorted((i for i in items if str((i.get("metadata") or {}).get("name", "")).startswith(ENVOYFILTER_PREFIX)),
                  key=lambda i: i["metadata"]["name"])


def collect(run: Runner = run_oc, max_bytes: int = DEFAULT_MAX_BYTES, log_window: str = DEFAULT_LOG_WINDOW) -> Dict[str, Any]:
    filters = envoyfilters(run)
    limitador = json.loads(run(["get", "limitador", LIMITADOR[1], "-n", LIMITADOR[0], "-o", "json"]))
    configurations = [wasm_configuration(f) for f in filters]
    try:
        failures: Optional[int] = failed_updates(run(["-n", OPERATOR[0], "logs", OPERATOR[1], f"--since={log_window}"]))
    except OcError:
        failures = None  # the log could not be read: said as such, not counted as zero
    objects = []
    for envoy, configuration in zip(filters, configurations):
        size = object_size(envoy)
        objects.append({"name": envoy["metadata"]["name"], "generation": envoy["metadata"].get("generation"), "bytes": size,
                        "configuration_bytes": len(configuration.encode()), "action_sets": action_sets(configuration),
                        "too_big": size > max_bytes})
    rows = limit_rows(limitador, configurations)
    result = {"envoyfilters": objects, "max_bytes": max_bytes, "limits": rows, "log_window": log_window, "failed_update_lines": failures}
    result["ok"] = (bool(objects) and not any(o["too_big"] for o in objects) and all(r["status"] != "NOT USED" for r in rows)
                    and failures == 0)
    return result


def render(result: Dict[str, Any]) -> str:
    lines = []
    for o in result["envoyfilters"]:
        sets = "unreadable" if o["action_sets"] is None else o["action_sets"]
        lines.append(f"EnvoyFilter {ENVOYFILTER_NAMESPACE}/{o['name']}: generation {o['generation']}, {o['bytes']:,} bytes "
                     f"(configuration {o['configuration_bytes']:,}), action sets {sets}" + (f"  TOO BIG (> {result['max_bytes']:,})" if o["too_big"] else ""))
    if not result["envoyfilters"]:
        lines.append(f"no EnvoyFilter named {ENVOYFILTER_PREFIX}* in {ENVOYFILTER_NAMESPACE}")
    for row in result["limits"]:
        lines.append(f"  {row['namespace']:<40} {row['max_value']}/{row['seconds']}s  {row['status']}"
                     + (f"  [{row['name']}]" if row["name"] else ""))
    failures = result["failed_update_lines"]
    lines.append(f"'{LOG_MARKER}' in the last {result['log_window']} of the kuadrant operator log: "
                 + ("log not readable" if failures is None else str(failures)))
    count = {k: sum(1 for r in result["limits"] if r["status"] == k) for k in ("COUNTED", "NOT USED", "NO-KEY")}
    why = " (the operator log could not be read)" if failures is None else ""
    lines.append(f"RESULT: {'OK' if result['ok'] else 'PROBLEM'} - {count['COUNTED']} counted, {count['NOT USED']} not used, "
                 f"{count['NO-KEY']} without a key (warning){why}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None, run: Runner = run_oc) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES, help="an EnvoyFilter above this many bytes is a problem")
    ap.add_argument("--log-window", default=DEFAULT_LOG_WINDOW, metavar="DURATION",
                    help="how far back the operator log is read, an `oc logs --since` value such as 20m (default: %(default)s)")
    ap.add_argument("--json", action="store_true", help="machine output")
    args = ap.parse_args(argv)
    try:
        result = collect(run, args.max_bytes, args.log_window)
    except (OcError, ValueError) as exc:
        print(f"check_maas_wasm: cannot read the cluster: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
