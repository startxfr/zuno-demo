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
    count is printed: each such line carries the whole object. An optimistic-concurrency conflict ("the object has been
    modified") is not counted: the operator retries it at once.

Exit code 1 when a limit is NOT USED, an EnvoyFilter is above --max-bytes (default 1,400,000) or that count is above 0; 2 when `oc`
cannot answer. It only runs `oc get` and `oc logs`; with --in-cluster it makes the same three reads
through the API server with the pod's ServiceAccount (urllib, no `oc`).

    python3 platform/models/check_maas_wasm.py [--max-bytes N] [--log-window 20m] [--in-cluster] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

ENVOYFILTER_NAMESPACE = "openshift-ingress"
ENVOYFILTER_PREFIX = "kuadrant-"
DEFAULT_MAX_BYTES = 1_400_000
LIMITADOR = ("kuadrant-system", "limitador")
OPERATOR = ("openshift-operators", "deploy/kuadrant-operator-controller-manager")
DEFAULT_LOG_WINDOW = "30m"
LOG_MARKER = "failed to update envoyfilter object"
CONFLICT_MARKER = "the object has been modified"
KEY_RE = re.compile(r"limit\.[A-Za-z0-9_]+__[0-9a-f]{8}")

Runner = Callable[[List[str]], str]


class OcError(RuntimeError):
    pass


def run_oc(args: List[str]) -> str:
    try:
        proc = subprocess.run(["oc"] + args, capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OcError(f"oc {args[0]}: {type(exc).__name__}") from exc
    if proc.returncode != 0:
        raise OcError(f"oc {' '.join(args[:3])} ... failed: {proc.stderr.strip()[:200]}")
    return proc.stdout


SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"
API_SERVER = "https://kubernetes.default.svc"
ENVOYFILTER_API = "/apis/networking.istio.io/v1alpha3"
LIMITADOR_API = "/apis/limitador.kuadrant.io/v1alpha1"
Fetch = Callable[[str], str]  # an API path (with its query) -> the response body


def api_fetch(path: str) -> str:
    """GET one API path with the pod's ServiceAccount token and CA (stdlib only)."""
    try:
        with open(f"{SA_DIR}/token") as handle:
            token = handle.read().strip()
        context = ssl.create_default_context(cafile=f"{SA_DIR}/ca.crt")
        request = urllib.request.Request(API_SERVER + path, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
        with urllib.request.urlopen(request, context=context, timeout=60) as response:  # noqa: S310 - fixed https URL
            return response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise OcError(f"api GET {path.split('?')[0]}: HTTP {exc.code}") from exc
    except (OSError, ValueError) as exc:
        raise OcError(f"api GET {path.split('?')[0]}: {type(exc).__name__}") from exc


def duration_seconds(value: str) -> int:
    """'20m', '1h30m', '90s' or a bare number of seconds, as `oc logs --since` takes them."""
    text = value.strip()
    if text.isdigit():
        return int(text)
    parts = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", text)
    if not text or not parts:
        raise ValueError(f"not a duration: {value!r}")
    hours, minutes, seconds = (int(g or 0) for g in parts.groups())
    return hours * 3600 + minutes * 60 + seconds


def in_cluster_runner(fetch: Fetch = api_fetch) -> Runner:
    """A Runner that answers the three `oc` calls of collect() from the API server (the same reads, no `oc`)."""
    def logs(namespace: str, target: str, since: str) -> str:
        kind, name = target.split("/", 1)
        if kind not in ("deploy", "deployment"):
            raise OcError(f"api logs: unsupported target {target}")
        deployment = json.loads(fetch(f"/apis/apps/v1/namespaces/{namespace}/deployments/{name}"))
        labels = ((deployment.get("spec") or {}).get("selector") or {}).get("matchLabels") or {}
        if not labels:
            raise OcError(f"api logs: deployment {name} has no matchLabels selector")
        selector = urllib.parse.quote(",".join(f"{k}={v}" for k, v in sorted(labels.items())))
        pods = json.loads(fetch(f"/api/v1/namespaces/{namespace}/pods?labelSelector={selector}")).get("items") or []
        if not pods:
            raise OcError(f"api logs: no pod for deployment {name}")
        seconds = duration_seconds(since.split("=", 1)[1])
        text = []
        for pod in pods:
            pod_name = pod["metadata"]["name"]
            containers = (pod.get("spec") or {}).get("containers") or []
            default = (pod["metadata"].get("annotations") or {}).get("kubectl.kubernetes.io/default-container")
            container = default or (containers[0]["name"] if containers else "")
            query = f"sinceSeconds={seconds}" + (f"&container={urllib.parse.quote(container)}" if container else "")
            text.append(fetch(f"/api/v1/namespaces/{namespace}/pods/{pod_name}/log?{query}"))
        return "\n".join(text)

    def run(args: List[str]) -> str:
        if args[:2] == ["get", "envoyfilter"] and "-n" in args:
            return fetch(f"{ENVOYFILTER_API}/namespaces/{args[args.index('-n') + 1]}/envoyfilters")
        if args[:2] == ["get", "limitador"] and "-n" in args:
            return fetch(f"{LIMITADOR_API}/namespaces/{args[args.index('-n') + 1]}/limitadors/{args[2]}")
        if "logs" in args and "-n" in args:
            i = args.index("logs")
            return logs(args[args.index("-n") + 1], args[i + 1], next(a for a in args if a.startswith("--since=")))
        raise OcError(f"in-cluster: unsupported call {args}")
    return run


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
    """How many lines of the operator log say the EnvoyFilter update failed. The lines themselves are never kept.

    An optimistic-concurrency conflict ("the object has been modified") is not counted: the operator retries on the
    newest version at once, so it is the normal trace of two reconciles meeting (seen after every MaaS change), not an
    object the API server refuses."""
    return sum(1 for line in log_text.splitlines() if LOG_MARKER in line and CONFLICT_MARKER not in line)


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


def main(argv: Optional[List[str]] = None, run: Optional[Runner] = None, fetch: Fetch = api_fetch) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES, help="an EnvoyFilter above this many bytes is a problem")
    ap.add_argument("--log-window", default=DEFAULT_LOG_WINDOW, metavar="DURATION",
                    help="how far back the operator log is read, an `oc logs --since` value such as 20m (default: %(default)s)")
    ap.add_argument("--in-cluster", action="store_true",
                    help="read through the pod's ServiceAccount and the API server (stdlib only, no `oc`), for the CronJob")
    ap.add_argument("--json", action="store_true", help="machine output")
    args = ap.parse_args(argv)
    if run is None:
        run = in_cluster_runner(fetch) if args.in_cluster else run_oc
    try:
        result = collect(run, args.max_bytes, args.log_window)
    except (OcError, ValueError) as exc:
        print(f"check_maas_wasm: cannot read the cluster: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
