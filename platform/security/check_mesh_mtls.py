#!/usr/bin/env python3
"""ADR-0602 / WP-224: targeted mesh mTLS and egress firewalls stay as decided.

Renders every ArgoCD Application in gitops/apps (Helm charts with the
Application's own values, raw manifest directories as they are; the same
hermetic rendering as platform/vault/check_secret_access.py) and fails when:

  1. a PeerAuthentication is rendered in a namespace other than zuno-data,
     zuno-auth and zuno-ai-run (mTLS is targeted, not mesh-wide, and never in
     redhat-ods-*), or Ansible applies one outside the charts;
  2. one of those three namespaces has no namespace-wide PeerAuthentication
     `default` (no selector) in mode PERMISSIVE or STRICT, or has several;
  3. a portLevelMtls entry is not PERMISSIVE, or a PeerAuthentication that has
     one carries no selector or no zuno.io/permissive-reason annotation (the
     values field `reason:` naming the non-mesh caller);
  4. a workload-scoped PeerAuthentication sets its own mtls mode (it must
     inherit the namespace mode, or a STRICT flip would silently skip it), or
     two of them in one namespace use the same selector (Istio applies the
     oldest one only);
  5. zuno-ai-run or zuno-unifai has no EgressFirewall, or one whose last rule is
     not Deny 0.0.0.0/0, or that allows 0.0.0.0/0 (or ::/0), or that allows
     nothing;
  6. any EgressFirewall is not named `default` or is not alone in its namespace
     (OVN honours only one, named default);
  7. a chart with PeerAuthentication/EgressFirewall templates is rendered by no
     Application (its objects would escape the check).

No live cluster needed: `helm template` only. Run from the repository root:

    python3 platform/security/check_mesh_mtls.py
"""
from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Set

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "vault"))

import check_secret_access as csa  # noqa: E402  (shared hermetic rendering)

REPO_ROOT = csa.REPO_ROOT

# ADR-0602 / WP-224 decision 1: the only namespaces with a PeerAuthentication.
MTLS_NAMESPACES = {"zuno-data", "zuno-auth", "zuno-ai-run"}
# ADR-0602 / WP-224 decision 2: the namespaces that must have a deny-all egress.
EGRESS_NAMESPACES = {"zuno-ai-run", "zuno-unifai"}
# A namespace whose firewall is switched off on purpose, pending its rehearsal:
# accepted only with `egress.enabled: false` AND a non-empty
# `egress.disabledReason` in the chart's values (printed on every run).
EGRESS_DEFERRABLE = {"zuno-unifai": "gitops/charts/unifai/values.yaml"}


def egress_deferred(ns: str) -> str:
    """The recorded reason when `ns`'s firewall is deliberately off, else ''."""
    path = EGRESS_DEFERRABLE.get(ns)
    if not path:
        return ""
    import yaml  # local: the rest of the check only needs it through csa
    with open(path, "r", encoding="utf-8") as fh:
        egress = (yaml.safe_load(fh) or {}).get("egress") or {}
    if egress.get("enabled") is False:
        return str(egress.get("disabledReason") or "").strip()
    return ""
NAMESPACE_MODES = {"PERMISSIVE", "STRICT"}
REASON_ANNOTATION = "zuno.io/permissive-reason"
KINDS = {"PeerAuthentication", "EgressFirewall"}
OPEN_CIDRS = {"0.0.0.0/0", "::/0"}


@dataclass
class Rendered:
    origin: str
    namespace: str
    doc: Dict[str, Any]


def charts_with_kinds() -> Set[str]:
    out: Set[str] = set()
    for tpl in (REPO_ROOT / "gitops" / "charts").glob("*/templates/**/*"):
        if tpl.is_file():
            text = tpl.read_text()
            if any(f"kind: {kind}" in text for kind in KINDS):
                out.add(tpl.relative_to(REPO_ROOT / "gitops" / "charts").parts[0])
    return out


def render_all(findings: csa.Findings) -> List[Rendered]:
    objects: List[Rendered] = []
    rendered: Set[str] = set()
    for path, app in csa.iter_applications():
        name = app["metadata"]["name"]
        src = app["spec"]["source"]
        dest_ns = app["spec"].get("destination", {}).get("namespace", "default")
        target = REPO_ROOT / src["path"]
        if (target / "Chart.yaml").exists():
            values = yaml.safe_load(src.get("helm", {}).get("values", "") or "") or {}
            values = csa.deep_merge(csa.deep_merge(csa.GLOBAL_VALUES, values), csa.APP_OVERLAYS.get(name, {}))
            try:
                docs = csa.helm_template(target, src.get("helm", {}).get("releaseName", name), dest_ns, values)
            except RuntimeError as exc:
                findings.check(False, f"{name}: helm template {src['path']} failed: {exc}")
                continue
            rendered.add(target.name)
        elif target.is_dir():
            docs = csa.load_raw_dir(target)
        else:
            continue
        for doc in docs:
            if doc.get("kind") in KINDS:
                ns = doc.get("metadata", {}).get("namespace") or dest_ns
                objects.append(Rendered(f"{name} ({path.relative_to(REPO_ROOT)})", ns, doc))
    for chart in sorted(charts_with_kinds() - rendered):
        findings.check(False, f"chart {chart} has PeerAuthentication/EgressFirewall templates but no gitops/apps Application renders it")
    for pattern in csa.ANSIBLE_GLOBS:
        for path in sorted(REPO_ROOT.glob(pattern)):
            text = path.read_text(errors="ignore")
            findings.check(
                "kind: PeerAuthentication" not in text,
                f"{path.relative_to(REPO_ROOT)}: Ansible applies a PeerAuthentication (render it from gitops/charts/namespaces)",
            )
    return objects


# ------------------------------------------------------------------ rules


def check_peer_authentications(objects: List[Rendered], findings: csa.Findings) -> None:
    pas = [o for o in objects if o.doc.get("kind") == "PeerAuthentication"]
    for ns in sorted(MTLS_NAMESPACES):
        defaults = [o for o in pas if o.namespace == ns and not (o.doc.get("spec") or {}).get("selector")]
        findings.check(len(defaults) == 1, f"{ns}: expected one namespace-wide PeerAuthentication, found {len(defaults)}")
        for o in defaults:
            mode = ((o.doc.get("spec") or {}).get("mtls") or {}).get("mode")
            findings.check(o.doc["metadata"].get("name") == "default",
                           f"{ns}: the namespace-wide PeerAuthentication must be named default ({o.origin})")
            findings.check(mode in NAMESPACE_MODES, f"{ns}: namespace-wide PeerAuthentication mode {mode!r} is not PERMISSIVE or STRICT ({o.origin})")
            findings.check(not (o.doc.get("spec") or {}).get("portLevelMtls"),
                           f"{ns}: portLevelMtls on the namespace-wide PeerAuthentication has no effect (Istio needs a selector)")
    seen_selectors: Dict[str, Dict[str, str]] = {}
    for o in pas:
        name = o.doc.get("metadata", {}).get("name", "?")
        label = f"{o.namespace}/{name}"
        findings.check(o.namespace in MTLS_NAMESPACES,
                       f"{label}: PeerAuthentication outside {sorted(MTLS_NAMESPACES)} ({o.origin}); mTLS is targeted (ADR-0602 / WP-224)")
        spec = o.doc.get("spec") or {}
        selector = (spec.get("selector") or {}).get("matchLabels")
        port_level = spec.get("portLevelMtls") or {}
        if selector:
            mode = (spec.get("mtls") or {}).get("mode")
            findings.check(mode in (None, "UNSET"),
                           f"{label}: a workload PeerAuthentication sets mtls.mode {mode!r}; it must inherit the namespace mode")
            key = yaml.safe_dump(selector, sort_keys=True)
            other = seen_selectors.setdefault(o.namespace, {}).setdefault(key, name)
            findings.check(other == name, f"{label}: same selector as {o.namespace}/{other} (Istio applies only the oldest)")
        if port_level:
            reason = str((o.doc.get("metadata", {}).get("annotations") or {}).get(REASON_ANNOTATION, "")).strip()
            findings.check(bool(selector), f"{label}: portLevelMtls without a selector")
            findings.check(bool(reason), f"{label}: portLevelMtls exception without a {REASON_ANNOTATION} annotation (values field reason:)")
            for port, setting in port_level.items():
                pmode = (setting or {}).get("mode")
                findings.check(pmode == "PERMISSIVE", f"{label}: port {port} mode {pmode!r}; exceptions may only be PERMISSIVE")


def check_egress_firewalls(objects: List[Rendered], findings: csa.Findings) -> None:
    efs = [o for o in objects if o.doc.get("kind") == "EgressFirewall"]
    per_ns: Dict[str, List[Rendered]] = {}
    for o in efs:
        per_ns.setdefault(o.namespace, []).append(o)
        findings.check(o.doc.get("metadata", {}).get("name") == "default",
                       f"{o.namespace}: EgressFirewall {o.doc.get('metadata', {}).get('name')!r} is ignored by OVN (must be named default)")
    for ns, items in sorted(per_ns.items()):
        findings.check(len(items) == 1, f"{ns}: {len(items)} EgressFirewalls rendered ({', '.join(i.origin for i in items)}); OVN allows one")
    for ns in sorted(EGRESS_NAMESPACES):
        items = per_ns.get(ns, [])
        deferred = egress_deferred(ns) if not items else ""
        if deferred:
            print(f"NOTE {ns}: EgressFirewall deliberately off: {deferred}")
            continue
        findings.check(bool(items), f"{ns}: no EgressFirewall rendered (ADR-0602 / WP-224 decision 2; for zuno-ai-run "
                                    "the zuno-namespaces-d1 Application must pass clusterBaseDomain)")
        for o in items:
            rules = (o.doc.get("spec") or {}).get("egress") or []
            last = rules[-1] if rules else {}
            findings.check(last.get("type") == "Deny" and (last.get("to") or {}).get("cidrSelector") == "0.0.0.0/0",
                           f"{ns}: EgressFirewall does not end with Deny 0.0.0.0/0 ({o.origin})")
            allows = [r for r in rules if r.get("type") == "Allow"]
            findings.check(bool(allows), f"{ns}: EgressFirewall allows nothing ({o.origin})")
            for rule in allows:
                cidr = (rule.get("to") or {}).get("cidrSelector")
                findings.check(cidr not in OPEN_CIDRS, f"{ns}: EgressFirewall allows {cidr} ({o.origin})")


def main() -> int:
    findings = csa.Findings()
    objects = render_all(findings)
    check_peer_authentications(objects, findings)
    check_egress_firewalls(objects, findings)
    pas = sum(1 for o in objects if o.doc.get("kind") == "PeerAuthentication")
    efs = sorted(o.namespace for o in objects if o.doc.get("kind") == "EgressFirewall")
    print(f"Rendered {pas} PeerAuthentications and {len(efs)} EgressFirewalls ({', '.join(efs)}).")
    for failure in findings.failures:
        print(f"FAIL {failure}")
    print(f"{findings.passes} checks passed, {len(findings.failures)} failed")
    print("RESULT: " + ("PASS" if not findings.failures else "FAIL"))
    return 0 if not findings.failures else 1


if __name__ == "__main__":
    sys.exit(main())
