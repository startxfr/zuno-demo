#!/usr/bin/env python3
"""Is the cluster back after a node drain, a reboot or an MCO roll? (WP-248 incident, 2026-11-12). Read-only.

After the zot source was removed from an ImageDigestMirrorSet the MCO drained every node, and the red lasted hours because
each layer hid the next: Quay was not Ready (gateways could not read the OKF release), the Kuadrant operator crash-looped
(its wasm Service had no endpoint, so the MaaS gateway failed closed with 503 on every route), Authorino and the gateway pods
had to be recreated afterwards. This lists those layers in the order they have to recover, with the next step for each.

  nodes      every node Ready and schedulable
  pools      every MachineConfigPool Updated and not Degraded
  operators  no ClusterOperator Degraded or unavailable
  pods       pods stuck (CrashLoopBackOff, Error, ImagePull*, CreateContainerConfigError) in the zuno and platform namespaces
  quay       the Quay application Ready and its route answering 401 without credentials
  kuadrant   the wasm Service of the Kuadrant operator has an endpoint, Authorino is Ready
  maas       a MaaS model route answers 401 without a token (503 = the wasm-shim failed closed)
  layout     ADR-0614 node pools: masters unschedulable, no workload pod left on a master, the infra pool at 3 Ready nodes

    python3 platform/recovery/check_recovery.py [--only quay,maas] [--no-http]

Exit 0 when everything is back, 1 with a finding (each one names the next step), 2 when it could not run.
"""
from __future__ import annotations

import argparse
import json
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Callable, Dict, List, Optional

STUCK = ("CrashLoopBackOff", "Error", "ErrImagePull", "ImagePullBackOff", "CreateContainerConfigError",
         "CreateContainerError", "RunContainerError")
NAMESPACES = ("zuno-", "kuadrant-system", "openshift-ingress", "redhat-ai-gateway-infra", "openshift-lightspeed",
              "openshift-operators", "unifai-operator", "policy-controller-operator")
# Known vendor noise that is not ours and does not block anything we serve (listed on purpose, so a new one shows up).
IGNORED_PODS = ("virt-platform-autopilot", "opendatahub-feast-operator", "spark-operator-module-controller-manager",
                "mcp-gateway-controller")

Oc = Callable[[List[str]], Dict]


def oc_json(args: List[str]) -> Dict:
    out = subprocess.run(["oc", *args, "-o", "json"], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"oc {' '.join(args)}: {out.stderr.strip()[:200]}")
    return json.loads(out.stdout)


def cond(obj: Dict, kind: str) -> str:
    for c in obj.get("status", {}).get("conditions", []) or []:
        if c.get("type") == kind:
            return c.get("status", "")
    return ""


def nodes(oc: Oc) -> List[str]:
    out = []
    for n in oc(["get", "nodes"])["items"]:
        name = n["metadata"]["name"]
        if cond(n, "Ready") != "True":
            out.append(f"node {name} is not Ready")
        if n.get("spec", {}).get("unschedulable"):
            out.append(f"node {name} is cordoned (a drain is running, or one is stuck on a single-replica PodDisruptionBudget: "
                       "ADR-0101 accepts deleting those pods to let it pass)")
    return out


def pools(oc: Oc) -> List[str]:
    out = []
    for p in oc(["get", "machineconfigpools"])["items"]:
        name = p["metadata"]["name"]
        if cond(p, "Updated") != "True":
            out.append(f"MachineConfigPool {name} is still updating ({p['status'].get('readyMachineCount', 0)}/"
                       f"{p['status'].get('machineCount', 0)} ready)")
        if cond(p, "Degraded") == "True":
            out.append(f"MachineConfigPool {name} is Degraded")
    return out


def operators(oc: Oc) -> List[str]:
    out = []
    for c in oc(["get", "clusteroperators"])["items"]:
        if cond(c, "Degraded") == "True" or cond(c, "Available") == "False":
            out.append(f"ClusterOperator {c['metadata']['name']} is Degraded or unavailable (usually follows the master drain)")
    return out


def pod_state(pod: Dict) -> str:
    """The first waiting reason, or the reason of a container that ended in error, else the phase."""
    for cs in (pod["status"].get("initContainerStatuses", []) or []) + (pod["status"].get("containerStatuses", []) or []):
        state = cs.get("state") or {}
        waiting = (state.get("waiting") or {}).get("reason")
        terminated = state.get("terminated") or {}
        if waiting and waiting not in ("PodInitializing", "ContainerCreating"):
            return waiting
        if terminated.get("exitCode"):
            return terminated.get("reason", "Error")
    return pod["status"].get("phase", "")


def pods(oc: Oc) -> List[str]:
    out = []
    for p in oc(["get", "pods", "-A"])["items"]:
        ns, name = p["metadata"]["namespace"], p["metadata"]["name"]
        if not (ns.startswith("zuno-") or ns in NAMESPACES) or any(i in name for i in IGNORED_PODS):
            continue
        if p["status"].get("phase") in ("Succeeded",):
            continue
        state = pod_state(p)
        if state in STUCK:
            out.append(f"{ns}/{name}: {state}")
    return out


def quay(oc: Oc, http: Optional[Callable[[str], int]]) -> List[str]:
    out = []
    pods_ = [p for p in oc(["get", "pods", "-n", "zuno-registry", "-l", "quay-component=quay-app"])["items"]
             if "upgrade" not in p["metadata"]["name"]]
    if not pods_ or cond(pods_[0], "Ready") != "True":
        out.append("the Quay application pod is not Ready (it can stay so for an hour after a move: its liveness probe kills a slow "
                   "start; the gateways then fall back to quay.io, which the zuno-ai-run EgressFirewall denies)")
    elif http:
        host = oc(["get", "route", "-n", "zuno-registry", "quay-quay"])["spec"]["host"]
        code = http(f"https://{host}/v2/")
        if code != 401:
            out.append(f"the Quay route answers {code} instead of 401")
    return out


def kuadrant(oc: Oc) -> List[str]:
    out = []
    ep = oc(["get", "endpoints", "-n", "openshift-operators", "kuadrant-operator-wasm"])
    if not any(s.get("addresses") for s in ep.get("subsets", []) or []):
        out.append("Service kuadrant-operator-wasm has no endpoint: the Kuadrant operator is down (crash loop on its CRD "
                   "bootstrap); every gateway that loads the wasm-shim fails closed until it is back")
    for p in oc(["get", "pods", "-n", "kuadrant-system"])["items"]:
        if p["metadata"]["name"].startswith("authorino-") and "operator" not in p["metadata"]["name"] \
                and cond(p, "Ready") != "True":
            out.append(f"Authorino pod {p['metadata']['name']} is not Ready")
    return out


def maas(oc: Oc, http: Optional[Callable[[str], int]]) -> List[str]:
    if not http:
        return []
    domain = oc(["get", "ingresses.config.openshift.io", "cluster"])["spec"]["domain"]
    code = http(f"https://maas.{domain}/zuno-ai-run/gpt-oss-20b/v1/models")
    if code == 401:
        return []
    if code == 503:
        return ["a MaaS route answers 503 without a token: the Kuadrant wasm-shim failed closed in the MaaS gateway. When the "
                "operator and its wasm Service are back, delete the maas-default-gateway pod (a wasm fetch that ran out of "
                "retries is never retried), then Authorino if it answers UNAVAILABLE"]
    return [f"a MaaS route answers {code} instead of 401 without a token"]


MASTER = "node-role.kubernetes.io/master"
INFRA = "node-role.kubernetes.io/infra"


def tolerates_master(pod: Dict) -> bool:
    """Pinned to a master (nodeSelector or required affinity) or tolerating the master taint: it may run there."""
    spec = pod.get("spec", {})
    if MASTER in (spec.get("nodeSelector") or {}) or "node-role.kubernetes.io/control-plane" in (spec.get("nodeSelector") or {}):
        return True
    if MASTER in json.dumps((spec.get("affinity") or {}).get("nodeAffinity", {})):
        return True
    return any(t.get("operator") == "Exists" and t.get("key") in (None, "", MASTER) for t in spec.get("tolerations", []) or [])


def layout(oc: Oc) -> List[str]:
    """ADR-0614 / WP-260: the control plane runs no workload, and the infra pool is whole."""
    out = []
    sched = oc(["get", "schedulers.config.openshift.io", "cluster"])
    if (sched.get("spec") or {}).get("mastersSchedulable"):
        out.append("the masters are schedulable again (Scheduler mastersSchedulable: true): run `make d0 install machines`, "
                   "which sets it back to false once the general workers are up")
    node_items = oc(["get", "nodes"])["items"]
    masters = {n["metadata"]["name"] for n in node_items if MASTER in n["metadata"].get("labels", {})}
    infra = [n for n in node_items if INFRA in n["metadata"].get("labels", {})]
    if infra and sum(1 for n in infra if cond(n, "Ready") == "True") < 3:
        out.append(f"the infra pool has {sum(1 for n in infra if cond(n, 'Ready') == 'True')} Ready node(s) of 3: router, "
                   "registry, monitoring, GitOps and Quay lose their zone spread")
    stray = []
    for p in oc(["get", "pods", "-A"])["items"]:
        if p.get("spec", {}).get("nodeName") not in masters or p["status"].get("phase") != "Running":
            continue
        owner = ((p["metadata"].get("ownerReferences") or [{}])[0]).get("kind")
        if owner in ("DaemonSet", "Node") or tolerates_master(p):
            continue
        stray.append(f"{p['metadata']['namespace']}/{p['metadata']['name']}")
    if stray:
        out.append(f"{len(stray)} workload pod(s) still on a master, placed before the masters became unschedulable "
                   f"(delete them to move them): {', '.join(stray[:5])}")
    return out


def http_status(url: str) -> int:
    ctx = ssl.create_default_context()
    try:
        return urllib.request.urlopen(url, timeout=15, context=ctx).status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:  # noqa: BLE001 - unreachable is reported as 0
        return 0


def run(only: List[str], http: Optional[Callable[[str], int]], oc: Oc = oc_json) -> Dict[str, List[str]]:
    checks = {"nodes": lambda: nodes(oc), "pools": lambda: pools(oc), "operators": lambda: operators(oc),
              "pods": lambda: pods(oc), "quay": lambda: quay(oc, http), "kuadrant": lambda: kuadrant(oc),
              "maas": lambda: maas(oc, http), "layout": lambda: layout(oc)}
    return {name: fn() for name, fn in checks.items() if not only or name in only}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", default="", help="comma-separated checks to run")
    parser.add_argument("--no-http", action="store_true", help="do not call the Quay and MaaS routes")
    args = parser.parse_args(argv)
    try:
        result = run([x for x in args.only.split(",") if x], None if args.no_http else http_status)
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        print(f"recovery check could not run: {exc}", file=sys.stderr)
        return 2
    bad = 0
    for name, findings in result.items():
        print(f"{'FAIL' if findings else 'ok  '} {name}")
        for f in findings:
            print(f"       - {f}")
        bad += len(findings)
    print(f"\n{'RESULT: the cluster is back' if not bad else f'RESULT: {bad} finding(s), in the order the layers have to recover'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
