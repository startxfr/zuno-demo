#!/usr/bin/env python3
"""What runs on the cluster that the repository does not explain (ADR-0608 clause 6, WP-241).

Read-only. Four checks, each a list of findings:

  subscriptions   an OLM Subscription whose package no file under gitops/ or ansible/ names, and which
                  platform/drift/external-operators.yaml does not list with an owner (clause 1)
  storage         a storage class that a chart's values name and that the cluster does not have (clause 2)
  by-hand         objects labelled zuno.io/applied-by-hand=<WP>, and the security objects in zuno-* namespaces
                  that neither ArgoCD nor the Ansible roles own (clause 3)
  images          a first-party image (built in zuno-ai-build) running in a pod whose build commit is not on any
                  origin branch (clause 4)
  canaries        a canary namespace (zuno.io/canary=true, ADR-0609) whose work package is closed in the tracker

    python3 platform/drift/check_drift.py [--strict] [--oc-context CTX]

Exit 0 when there is nothing to report, or always without --strict (report-only until the first clean run, then
`--strict` in `make d3 check drift`); 1 with --strict and a finding; 2 when it could not run.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from typing import Dict, Iterable, List, Optional, Set

REPO = pathlib.Path(__file__).resolve().parents[2]
EXTERNAL_FILE = REPO / "platform" / "drift" / "external-operators.yaml"
BUILD_NS = "zuno-ai-build"
SECURITY_KINDS = ("peerauthentications.security.istio.io", "authorizationpolicies.security.istio.io",
                  "networkpolicies.networking.k8s.io", "egressfirewalls.k8s.ovn.org")
# Owners that are the repository: ArgoCD's tracking, the Ansible roles' label, and the operators the repository
# installs (their operands carry their own owner references).
_OWNED_LABELS = ("zuno.io/managed-by", "app.kubernetes.io/instance", "argocd.argoproj.io/instance")
_STORAGE_RE = re.compile(r"^\s*(?:sharedStorageClass|storageClassName|storageClass):\s*\"?([A-Za-z0-9.-]+)\"?\s*$", re.M)
_PLACEHOLDER = re.compile(r"mycluster|example|default-storageclass")


class Oc:
    def __init__(self, context: Optional[str] = None) -> None:
        self.base = ["oc"] + (["--context", context] if context else [])

    def json(self, *args: str) -> Dict:
        out = subprocess.run(self.base + list(args) + ["-o", "json"], capture_output=True, text=True, timeout=180)
        if out.returncode != 0:
            raise RuntimeError(f"oc {' '.join(args)}: {out.stderr.strip()[:200]}")
        return json.loads(out.stdout)


def repo_text(dirs: Iterable[str] = ("gitops", "ansible")) -> str:
    chunks = []
    for d in dirs:
        for p in (REPO / d).rglob("*"):
            if p.is_file() and p.suffix in (".yaml", ".yml", ".j2", ".tpl", ".json") and "known-good" not in p.name:
                try:
                    chunks.append(p.read_text(errors="replace"))
                except OSError:
                    continue
    return "\n".join(chunks)


def load_external(path: pathlib.Path = EXTERNAL_FILE) -> Dict[str, Dict]:
    if not path.exists():
        return {}
    import yaml

    doc = yaml.safe_load(path.read_text()) or {}
    return {e["package"]: e for e in doc.get("operators") or [] if e.get("package")}


def undeclared_subscriptions(subs: List[Dict], text: str, external: Dict[str, Dict]) -> List[str]:
    out = []
    for s in subs:
        pkg = (s.get("spec") or {}).get("name") or ""
        ns = s["metadata"]["namespace"]
        if pkg in external:
            continue
        if pkg and pkg not in text:
            out.append(f"Subscription {pkg} [{ns}] is installed, but no file under gitops/ or ansible/ names it and "
                       f"{EXTERNAL_FILE.relative_to(REPO)} does not list it")
    return out


def missing_storage_classes(values_text: str, live: Set[str]) -> List[str]:
    wanted = {m for m in _STORAGE_RE.findall(values_text) if not _PLACEHOLDER.search(m)}
    return [f"storage class {sc} is named by a chart's values but does not exist on the cluster"
            for sc in sorted(wanted - live)]


def unowned(items: List[Dict], kind: str) -> List[str]:
    out = []
    for o in items:
        md = o.get("metadata") or {}
        ns, name = md.get("namespace", ""), md.get("name", "")
        labels, ann = md.get("labels") or {}, md.get("annotations") or {}
        if "zuno.io/applied-by-hand" in labels:
            out.append(f"{kind} {ns}/{name} is labelled applied-by-hand by {labels['zuno.io/applied-by-hand']}")
            continue
        if not ns.startswith("zuno-") or md.get("ownerReferences"):
            continue
        if any(k in labels for k in _OWNED_LABELS) or "argocd.argoproj.io/tracking-id" in ann:
            continue
        out.append(f"{kind} {ns}/{name} is owned by neither ArgoCD nor an Ansible role")
    return out


def wp_states(roadmap: pathlib.Path = REPO / "docs" / "roadmap" / "implementation-roadmap.md") -> Dict[str, str]:
    states = {}
    for line in roadmap.read_text().splitlines():
        if line.startswith("| WP-"):
            cells = [c.strip() for c in line.split("|")]
            if len(cells) >= 7:
                states[cells[1]] = cells[5]
    return states


_CLOSED = ("done", "abandoned", "cancelled", "closed")


def leftover_canaries(namespaces: List[Dict], states: Dict[str, str]) -> List[str]:
    out = []
    for ns in namespaces:
        md = ns.get("metadata") or {}
        labels = md.get("labels") or {}
        if labels.get("zuno.io/canary") != "true":
            continue
        wp = labels.get("zuno.io/work-package", "")
        state = states.get(wp, "")
        if not wp or wp not in states or state.lower().startswith(_CLOSED):
            out.append(f"canary namespace {md.get('name')} is left over: its work package {wp or '(none)'} is "
                       f"{state or 'not in the tracker'}")
    return out


def on_origin(commit: str) -> bool:
    out = subprocess.run(["git", "-C", str(REPO), "branch", "-r", "--contains", commit],
                         capture_output=True, text=True, timeout=60)
    return out.returncode == 0 and any(line.strip().startswith("origin/") for line in out.stdout.splitlines())


def image_findings(pods: List[Dict], commit_of, is_pushed) -> List[str]:
    seen: Dict[str, List[str]] = {}
    for p in pods:
        for cs in (p.get("status") or {}).get("containerStatuses") or []:
            image_id = cs.get("imageID") or ""
            if f"/{BUILD_NS}/" not in image_id or "@sha256:" not in image_id:
                continue
            seen.setdefault(image_id.split("@", 1)[1], []).append(f"{p['metadata']['namespace']}/{p['metadata']['name']}")
    out = []
    for digest, where in sorted(seen.items()):
        commit = commit_of(digest)
        if not commit:
            continue
        if not is_pushed(commit):
            out.append(f"image {digest[:19]}… built from {commit[:10]}, which is on no origin branch, runs in "
                       f"{', '.join(sorted(where)[:3])}{' …' if len(where) > 3 else ''}")
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--strict", action="store_true", help="exit 1 on any finding")
    ap.add_argument("--oc-context")
    args = ap.parse_args(argv)
    oc = Oc(args.oc_context)
    findings: Dict[str, List[str]] = {}
    try:
        subprocess.run(["git", "-C", str(REPO), "fetch", "-q", "origin"], timeout=120, capture_output=True)
        findings["subscriptions"] = undeclared_subscriptions(
            oc.json("get", "subscriptions.operators.coreos.com", "-A")["items"], repo_text(), load_external())
        live_sc = {i["metadata"]["name"] for i in oc.json("get", "storageclass")["items"]}
        values = "\n".join(p.read_text() for p in (REPO / "gitops" / "charts").glob("*/values.yaml"))
        findings["storage"] = missing_storage_classes(values, live_sc)
        by_hand: List[str] = []
        for kind in SECURITY_KINDS:
            try:
                by_hand += unowned(oc.json("get", kind, "-A")["items"], kind.split(".")[0])
            except RuntimeError:
                continue  # the kind is not served on this cluster
        findings["by-hand"] = by_hand

        def commit_of(digest: str) -> str:
            try:
                labels = (oc.json("get", "image", digest).get("dockerImageMetadata") or {}).get("Config", {}).get("Labels") or {}
            except RuntimeError:
                return ""
            return labels.get("io.openshift.build.commit.id", "")

        findings["images"] = image_findings(oc.json("get", "pods", "-A")["items"], commit_of, on_origin)
        findings["canaries"] = leftover_canaries(oc.json("get", "namespaces", "-l", "zuno.io/canary=true")["items"],
                                                 wp_states())
    except (RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return 2
    total = 0
    for check, items in findings.items():
        print(f"{check}: {'clean' if not items else str(len(items)) + ' finding(s)'}")
        for f in items:
            print(f"  - {f}")
        total += len(items)
    print(f"RESULT: {'clean' if not total else str(total) + ' finding(s)'}")
    return 1 if (args.strict and total) else 0


if __name__ == "__main__":
    sys.exit(main())
