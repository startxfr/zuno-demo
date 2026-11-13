#!/usr/bin/env python3
"""ADR-0602 clause 5 / WP-224 (finding C4): every ArgoCD Application in
gitops/apps sits in the narrowest AppProject that can hold what it renders.

Before WP-224 one AppProject `zuno` allowed every destination namespace and
every cluster-scoped kind (`*/*`), so a change to any chart - a workload
chart included - could create a ClusterRoleBinding to cluster-admin through
the cluster-admin ArgoCD controller. The split is:

  zuno-platform   operators and cluster configuration: renders cluster-scoped
                  kinds or OLM objects; clusterResourceWhitelist is the exact
                  list of group/kinds these Applications render (no `*`).
  zuno-apps       workloads: no cluster-scoped kind at all, no
                  operators.coreos.com or argoproj.io kind.
  zuno-bootstrap  the root app-of-apps only: Applications in openshift-gitops.

The split only holds if nothing slides back, so this check renders each
Application in gitops/apps (Helm charts with the Application's own values
plus the values Ansible injects, see check_secret_access.APP_OVERLAYS; raw
manifest directories as they are) and fails when:

  1. an Application's project is not zuno-platform or zuno-apps (or the
     project file it names does not exist), or the root app-of-apps is not
     in zuno-bootstrap with destination openshift-gitops;
  2. a zuno-apps Application renders a cluster-scoped kind or an
     operators.coreos.com / argoproj.io kind, or sets CreateNamespace=true;
  3. a rendered cluster-scoped kind is not in its project's
     clusterResourceWhitelist, or a namespaced kind is refused by the
     project's namespaceResourceBlacklist/Whitelist;
  4. the destination namespace, or the namespace a rendered namespaced
     object lands in, matches none of the project's destinations;
  5. a project's destinations include openshift-gitops (only zuno-bootstrap
     may write there: an Application created by a workload chart would be
     reconciled by the cluster-admin controller under any project);
  6. a project's clusterResourceWhitelist carries a `*` or an entry nothing
     renders (least privilege: an unused allowance is an attacker's), except
     the LIVE_ONLY_KINDS ArgoCD tracks without a render producing them.

Charts are rendered WITH their subcharts when the dependency archives are
present under charts/ (the startx operator/project/cluster-* subcharts
render the Namespaces, Subscriptions and cluster CRs that matter here);
`--strict-dependencies` (CI, after `helm dependency build`) turns a missing
archive into a failure instead of a hermetic fallback.

Which kinds are cluster-scoped comes from platform/gitops/cluster-scoped-
kinds.yaml (live API discovery) plus every CustomResourceDefinition the
repository renders with scope Cluster.

Run from the repository root:

    python3 platform/gitops/check_app_projects.py               # the check
    python3 platform/gitops/check_app_projects.py --inventory   # app -> kinds, namespaces
"""
from __future__ import annotations

import argparse
import fnmatch
import pathlib
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "platform" / "vault"))

import check_secret_access as csa  # noqa: E402  (shared render helpers and Ansible overlays)

PROJECT_DIR = REPO_ROOT / "ansible" / "roles" / "argocd" / "kustomize" / "appproject"
SCOPES_PATH = REPO_ROOT / "platform" / "gitops" / "cluster-scoped-kinds.yaml"

PLATFORM = "zuno-platform"
APPS = "zuno-apps"
BOOTSTRAP = "zuno-bootstrap"
GITOPS_NS = "openshift-gitops"
# Groups a workload chart must never render: an OLM Subscription installs an
# operator with cluster-wide RBAC, an argoproj.io object steers ArgoCD itself.
APPS_FORBIDDEN_GROUPS = ("operators.coreos.com", "argoproj.io")
ALLOWED_APP_PROJECTS = (PLATFORM, APPS)
ROOT_APP = REPO_ROOT / "gitops" / "root-app-of-apps.yaml"
# The pre-split project, kept only until ansible/roles/argocd deletes it on
# the first run where no live Application names it; no gitops/apps
# Application may name it (rule 1), so its `*/*` is not checked here.
LEGACY_PROJECTS = ("zuno",)
# Whitelist entries no render produces but ArgoCD tracks live, with why.
LIVE_ONLY_KINDS: Dict[str, str] = {
    "project.openshift.io/Project": "the startx `project` subchart's PreSync hook Namespace, tracked by ArgoCD "
                                    "as a Project on OpenShift (six *-d0 Applications, 2026-11-06)",
}


# Toggles Ansible flips through gitops_app_extra_helm_values at apply time,
# on top of check_secret_access.APP_OVERLAYS. Each one switches on objects -
# often cluster-scoped or OLM ones - that the committed values leave off;
# rendering them here keeps what a real install applies inside the check.
# Source: the include of ansible/tasks/apply_gitops_app.yml in each role.
PROJECT_OVERLAYS: Dict[str, Dict[str, Any]] = {
    # ADR-0612 family (c): the redirect of the UnifAI images is committed off; a real install after the owner's flip renders it.
    "zuno-quay-registry-d0": {"redirects": {"enabled": True, "host": "quay.example"}},
    # ansible/roles/cert_manager: both ADR-0211 consumer patches (APIServer, IngressController).
    "zuno-cert-manager-d1": {"acme": {"consumers": {"routerDefaultCert": True, "apiServerNamedCert": True}}},
    # ansible/roles/nvidia_gpu: the ClusterPolicy with the discovered spec.
    "zuno-nvidia-gpu-d1": {"cluster-gpu": {"gpu": {"enabled": True}}},
    # ansible/roles/vault/tasks/apply_vault_app.yml: the KMS key from confidential.yml.
    "zuno-vault-d1": {"vault": {"kms": {"keyId": "placeholder"}}},
    # ansible/roles/aap_config: the AAP Project/Inventory/Credential CRs and installer ClusterRole.
    "zuno-aap-config-d1": {"aapConfig": {"enabled": True}},
    # ansible/roles/openshift_rbac_groups: RoleBindings in every live zuno-managed namespace.
    "zuno-openshift-rbac-groups-d1": {"roleBindings": {"enabled": True}, "zunoManagedNamespaces": ["zuno-ai-run"]},
    # ansible/roles/openclaw: Subscriptions (d0) and the Claw CRs (d1) per persona.
    "zuno-openclaw-d0": {"operator": {"enabled": True}},
    "zuno-openclaw-d1": {"assistants": {"enabled": True}},
    # ansible/roles/unifai: the operator Subscription when this Application owns it.
    "zuno-unifai-d0": {"operator": {"install": True}},
    # ansible/roles/service_mesh.
    "zuno-service-mesh-d0": {"cluster-istio": {"operatorIstio": {"enabled": True}}},
    "zuno-service-mesh-d1": {"clusterIssuer": {"enabled": True}, "istioCsr": {"enabled": True},
                             "istiocni": {"enabled": True}, "istio": {"enabled": True}},
    # ansible/roles/{kueue,jobset,nfs_provisioner,custom_metrics_autoscaler,external_secrets,postgresql,mlflow}.
    "zuno-kueue-d1": {"kueueOperand": {"enabled": True}, "queueResources": {"enabled": True}},
    "zuno-jobset-d1": {"jobsetOperator": {"enabled": True}},
    "zuno-nfs-provisioner-d1": {"nfsProvisioner": {"enabled": True}},
    "zuno-custom-metrics-autoscaler-d1": {"kedaController": {"enabled": True}, "triggerAuthentication": {"enabled": True}},
    "zuno-external-secrets-d1": {"operatorconfig": {"enabled": True}, "secretStores": {"enabled": True}},
    "zuno-postgresql-d1": {"postgresCluster": {"enabled": True}},
    "zuno-mlflow-d1": {"mlflowConfig": {"enabled": True}},
    # ADR-0614: the per-component infra-node switches, committed off and flipped one at a time during the rollout.
    "zuno-machines-d0": {"infraPlacement": {"registry": True, "userWorkloadMonitoring": True, "gitops": True}},
}


def overlay_for(name: str) -> Dict[str, Any]:
    return csa.deep_merge(csa.APP_OVERLAYS.get(name, {}), PROJECT_OVERLAYS.get(name, {}))


@dataclass
class Findings:
    failures: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    passes: int = 0

    def check(self, condition: bool, message: str) -> None:
        if condition:
            self.passes += 1
        elif message not in self.failures:
            self.failures.append(message)


@dataclass
class Rendered:
    """One Application and what it renders."""

    name: str
    origin: str
    project: str
    destination: str
    docs: List[Dict[str, Any]]
    sync_options: List[str] = field(default_factory=list)


# ---------------------------------------------------------------- inputs


def group_kind(doc: Dict[str, Any]) -> str:
    api = doc.get("apiVersion", "") or ""
    group = api.split("/")[0] if "/" in api else ""
    return f"{group}/{doc.get('kind', '')}"


def load_projects(directory: pathlib.Path = PROJECT_DIR) -> Dict[str, Dict[str, Any]]:
    projects: Dict[str, Dict[str, Any]] = {}
    for path in sorted(directory.glob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text()):
            if isinstance(doc, dict) and doc.get("kind") == "AppProject":
                projects[doc["metadata"]["name"]] = doc.get("spec", {}) or {}
    return projects


def load_cluster_scoped(path: pathlib.Path = SCOPES_PATH) -> Set[str]:
    return set((yaml.safe_load(path.read_text()) or {}).get("kinds", []))


def crd_cluster_kinds(docs: Iterable[Dict[str, Any]]) -> Set[str]:
    out: Set[str] = set()
    for doc in docs:
        if doc.get("kind") == "CustomResourceDefinition" and (doc.get("spec") or {}).get("scope") == "Cluster":
            spec = doc["spec"]
            out.add(f"{spec.get('group', '')}/{(spec.get('names') or {}).get('kind', '')}")
    return out


def dependencies_present(chart_dir: pathlib.Path) -> Tuple[bool, List[str]]:
    chart = yaml.safe_load((chart_dir / "Chart.yaml").read_text()) or {}
    missing = [
        dep["name"] for dep in chart.get("dependencies", []) or []
        if not list((chart_dir / "charts").glob(f"{dep['name']}-*.tgz")) and not (chart_dir / "charts" / dep["name"]).is_dir()
    ]
    return not missing, missing


def helm_template_with_dependencies(chart_dir: pathlib.Path, release: str, namespace: str,
                                    values: Dict[str, Any]) -> List[Dict[str, Any]]:
    with tempfile.TemporaryDirectory() as tmp:
        values_file = pathlib.Path(tmp) / "values.yaml"
        values_file.write_text(yaml.safe_dump(values))
        proc = subprocess.run(
            ["helm", "template", release, str(chart_dir), "-f", str(values_file), "--namespace", namespace],
            capture_output=True, text=True,
        )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip().splitlines()[0] if proc.stderr.strip() else "helm template failed")
    return [d for d in yaml.safe_load_all(proc.stdout) if isinstance(d, dict)]


def render_all(findings: Findings, strict_dependencies: bool = False) -> List[Rendered]:
    out: List[Rendered] = []
    for path, app in csa.iter_applications():
        name = app["metadata"]["name"]
        spec = app["spec"]
        src = spec["source"]
        dest_ns = (spec.get("destination") or {}).get("namespace", "") or ""
        target = REPO_ROOT / src["path"]
        if (target / "Chart.yaml").exists():
            values = yaml.safe_load(src.get("helm", {}).get("values", "") or "") or {}
            values = csa.deep_merge(csa.deep_merge(csa.GLOBAL_VALUES, values), overlay_for(name))
            release = src.get("helm", {}).get("releaseName", name)
            ok, missing = dependencies_present(target)
            try:
                if ok:
                    docs = helm_template_with_dependencies(target, release, dest_ns, values)
                else:
                    if strict_dependencies:
                        findings.check(False, f"{name}: chart {src['path']} dependencies not built ({', '.join(missing)}); "
                                              "run `helm dependency build` first")
                        continue
                    note = (f"{src['path']}: subcharts {', '.join(missing)} not built, rendered without them "
                            "(their kinds are not checked)")
                    if note not in findings.notes:
                        findings.notes.append(note)
                    docs = csa.helm_template(target, release, dest_ns, values)
            except RuntimeError as exc:
                findings.check(False, f"{name}: helm template {src['path']} failed: {exc}")
                continue
        elif target.is_dir():
            docs = csa.load_raw_dir(target)
        else:
            findings.check(False, f"{name}: source path {src['path']} does not exist")
            continue
        out.append(Rendered(name, str(path.relative_to(REPO_ROOT)), spec.get("project", ""), dest_ns, docs,
                            list((spec.get("syncPolicy") or {}).get("syncOptions") or [])))
    return out


# ---------------------------------------------------------------- rules


def _gk_listed(gk: str, entries: Iterable[Dict[str, Any]]) -> bool:
    group, kind = gk.split("/", 1)
    return any(fnmatch.fnmatchcase(group, e.get("group", "")) and fnmatch.fnmatchcase(kind, e.get("kind", ""))
               for e in entries or [])


def namespace_allowed(namespace: str, project: Dict[str, Any]) -> bool:
    return any(fnmatch.fnmatchcase(namespace, d.get("namespace", "")) for d in project.get("destinations", []) or [])


def object_namespace(doc: Dict[str, Any], destination: str) -> str:
    return (doc.get("metadata") or {}).get("namespace") or destination


def check_projects(projects: Dict[str, Dict[str, Any]], findings: Findings) -> None:
    for name in (PLATFORM, APPS, BOOTSTRAP):
        findings.check(name in projects, f"AppProject {name} is missing from {PROJECT_DIR.relative_to(REPO_ROOT)}")
    for name, spec in projects.items():
        if name in LEGACY_PROJECTS:
            continue
        for entry in spec.get("clusterResourceWhitelist", []) or []:
            findings.check("*" not in (entry.get("group", ""), entry.get("kind", "")),
                           f"AppProject {name}: clusterResourceWhitelist entry {entry} uses a wildcard")
        if name == BOOTSTRAP:
            continue
        for dest in spec.get("destinations", []) or []:
            findings.check(not fnmatch.fnmatchcase(GITOPS_NS, dest.get("namespace", "")),
                           f"AppProject {name}: destination {dest.get('namespace')!r} admits {GITOPS_NS} "
                           f"(only {BOOTSTRAP} may write Applications there)")
    if BOOTSTRAP in projects:
        boot = projects[BOOTSTRAP]
        findings.check(not boot.get("clusterResourceWhitelist"),
                       f"AppProject {BOOTSTRAP}: clusterResourceWhitelist must be empty")
        findings.check(boot.get("namespaceResourceWhitelist") == [{"group": "argoproj.io", "kind": "Application"}],
                       f"AppProject {BOOTSTRAP}: namespaceResourceWhitelist must be exactly argoproj.io/Application")
        findings.check([d.get("namespace") for d in boot.get("destinations", []) or []] == [GITOPS_NS],
                       f"AppProject {BOOTSTRAP}: the only destination must be {GITOPS_NS}")
    if APPS in projects:
        findings.check(not projects[APPS].get("clusterResourceWhitelist"),
                       f"AppProject {APPS}: clusterResourceWhitelist must be empty")
        for group in APPS_FORBIDDEN_GROUPS:
            findings.check(_gk_listed(f"{group}/Anything", projects[APPS].get("namespaceResourceBlacklist", [])),
                           f"AppProject {APPS}: namespaceResourceBlacklist must refuse {group}/*")


def check_apps(rendered: List[Rendered], projects: Dict[str, Dict[str, Any]], cluster_scoped: Set[str],
               findings: Findings) -> Dict[str, Set[str]]:
    """Returns project -> cluster-scoped group/kinds actually rendered."""
    used: Dict[str, Set[str]] = {}
    for app in rendered:
        allowed = ALLOWED_APP_PROJECTS
        findings.check(app.project in allowed,
                       f"{app.name}: project {app.project!r} is not one of {', '.join(allowed)}")
        project = projects.get(app.project)
        if project is None:
            findings.check(False, f"{app.name}: project {app.project!r} has no manifest in "
                                  f"{PROJECT_DIR.relative_to(REPO_ROOT)}")
            continue
        # CreateNamespace=true makes ArgoCD create a Namespace - a
        # cluster-scoped kind zuno-apps does not allow; zuno-namespaces-d0
        # creates workload namespaces instead.
        sync_options = app.sync_options
        findings.check(app.project != APPS or "CreateNamespace=true" not in sync_options,
                       f"{app.name}: zuno-apps Application uses CreateNamespace=true (Namespace is cluster-scoped)")
        findings.check(namespace_allowed(app.destination, project),
                       f"{app.name}: destination namespace {app.destination!r} not in AppProject {app.project} destinations")
        for doc in app.docs:
            gk = group_kind(doc)
            ref = f"{gk} {(doc.get('metadata') or {}).get('name', '?')}"
            if gk in cluster_scoped:
                used.setdefault(app.project, set()).add(gk)
                findings.check(app.project != APPS,
                               f"{app.name}: zuno-apps Application renders cluster-scoped {ref}")
                findings.check(_gk_listed(gk, project.get("clusterResourceWhitelist", [])),
                               f"{app.name}: cluster-scoped {gk} not in AppProject {app.project} clusterResourceWhitelist")
                continue
            group = gk.split("/", 1)[0]
            if app.project == APPS:
                findings.check(group not in APPS_FORBIDDEN_GROUPS,
                               f"{app.name}: zuno-apps Application renders {ref} (OLM/ArgoCD kinds belong to {PLATFORM})")
            if project.get("namespaceResourceWhitelist"):
                findings.check(_gk_listed(gk, project["namespaceResourceWhitelist"]),
                               f"{app.name}: {gk} not in AppProject {app.project} namespaceResourceWhitelist")
            findings.check(not _gk_listed(gk, project.get("namespaceResourceBlacklist", [])),
                           f"{app.name}: {gk} refused by AppProject {app.project} namespaceResourceBlacklist")
            ns = object_namespace(doc, app.destination)
            findings.check(namespace_allowed(ns, project),
                           f"{app.name}: {ref} lands in namespace {ns!r}, not in AppProject {app.project} destinations")
    return used


def check_unused_whitelist(projects: Dict[str, Dict[str, Any]], used: Dict[str, Set[str]], findings: Findings,
                           unproven: bool = False) -> None:
    """A whitelist entry no Application renders is a permission nobody uses. When some chart's subcharts are not built
    (a workstation without `helm dependency build`), the kinds those subcharts render are invisible, so an entry that looks
    unused cannot be proven so: it is reported as a note, not a failure. CI builds the dependencies and passes
    --strict-dependencies, where every chart is rendered whole and the entry fails."""
    for name in (PLATFORM,):
        for entry in (projects.get(name) or {}).get("clusterResourceWhitelist", []) or []:
            gk = f"{entry.get('group', '')}/{entry.get('kind', '')}"
            if gk in used.get(name, set()) or gk in LIVE_ONLY_KINDS:
                findings.passes += 1
            elif unproven:
                findings.notes.append(f"AppProject {name}: clusterResourceWhitelist entry {gk} is rendered by no Application "
                                      "that could be rendered whole (some subcharts are not built); not proven unused")
            else:
                findings.check(False, f"AppProject {name}: clusterResourceWhitelist entry {gk} is rendered by no Application")


def check_root_app(findings: Findings, path: pathlib.Path = ROOT_APP) -> None:
    """The root app-of-apps is the only Application in zuno-bootstrap."""
    docs = [d for d in yaml.safe_load_all(path.read_text()) if isinstance(d, dict)]
    for doc in docs:
        spec = doc.get("spec", {}) or {}
        findings.check(spec.get("project") == BOOTSTRAP,
                       f"{path.relative_to(REPO_ROOT)}: project must be {BOOTSTRAP}, found {spec.get('project')!r}")
        findings.check((spec.get("destination") or {}).get("namespace") == GITOPS_NS,
                       f"{path.relative_to(REPO_ROOT)}: destination namespace must be {GITOPS_NS}")


def inventory(rendered: List[Rendered], cluster_scoped: Set[str]) -> None:
    for app in sorted(rendered, key=lambda r: r.name):
        cluster = sorted({group_kind(d) for d in app.docs if group_kind(d) in cluster_scoped})
        olm = sorted({group_kind(d) for d in app.docs if group_kind(d).split("/")[0] in APPS_FORBIDDEN_GROUPS})
        namespaces = sorted({object_namespace(d, app.destination) for d in app.docs
                             if group_kind(d) not in cluster_scoped})
        print(f"{app.name} [{app.project}] dest={app.destination}")
        print(f"  cluster: {cluster}")
        print(f"  olm/argo: {olm}")
        print(f"  namespaces: {namespaces}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--inventory", action="store_true", help="print app -> kinds and namespaces, then exit")
    parser.add_argument("--strict-dependencies", action="store_true",
                        help="fail when a chart's subchart archives are not built (CI, after helm dependency build)")
    args = parser.parse_args(argv)

    findings = Findings()
    rendered = render_all(findings, strict_dependencies=args.strict_dependencies)
    cluster_scoped = load_cluster_scoped() | crd_cluster_kinds(d for r in rendered for d in r.docs)
    if args.inventory:
        inventory(rendered, cluster_scoped)
        return 0
    projects = load_projects()
    check_projects(projects, findings)
    check_root_app(findings)
    used = check_apps(rendered, projects, cluster_scoped, findings)
    check_unused_whitelist(projects, used, findings,
                           unproven=any('not built, rendered without them' in n for n in findings.notes))
    counts: Dict[str, int] = {}
    for app in rendered:
        counts[app.project] = counts.get(app.project, 0) + 1
    print(f"Rendered {len(rendered)} Applications: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    for note in findings.notes:
        print(f"NOTE {note}")
    for failure in findings.failures:
        print(f"FAIL {failure}")
    print(f"{findings.passes} checks passed, {len(findings.failures)} failed")
    print("RESULT: " + ("PASS" if not findings.failures else "FAIL"))
    return 0 if not findings.failures else 1


if __name__ == "__main__":
    sys.exit(main())
