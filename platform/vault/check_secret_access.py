#!/usr/bin/env python3
"""ADR-0602 clause 2 / WP-223 (finding C2): every ExternalSecret reads Vault
through its own namespace's SecretStore, and only the keys
platform/vault/secret-access.yaml grants that namespace.

The single ClusterSecretStore vault-backend it replaces let an ExternalSecret
in ANY namespace read all of zuno/data/*. Per-namespace stores only help if
nothing slides back: this check renders every ArgoCD Application in
gitops/apps (Helm charts with the Application's own values, raw manifest
directories as they are) plus the ExternalSecrets Ansible applies itself, and
fails when:

  1. an ExternalSecret (or one of its entries) references a ClusterSecretStore,
     or any store other than SecretStore/vault;
  2. an ExternalSecret reads a key (remoteRef.key, dataFrom.extract.key,
     dataFrom.find.path) its namespace is not granted in secret-access.yaml;
  3. a namespace in secret-access.yaml has no rendered SecretStore vault, or
     has more than one (two charts owning one store would fight in ArgoCD);
  4. a rendered SecretStore is not the expected shape (role ns-<namespace>,
     ServiceAccount vault-reader, KV v2 mount zuno, same server everywhere),
     or exists for a namespace the table does not list;
  5. a ClusterSecretStore is rendered at all;
  6. a table entry is unused (least privilege: a grant nothing reads is a
     grant an attacker can use), or a chart with ExternalSecret templates is
     rendered by no Application (its keys would escape the check).

No live cluster needed: `helm template` only. Charts are rendered from a
temporary copy with their `dependencies` removed, so no chart repository is
contacted; every ExternalSecret and SecretStore lives in this repository's
own templates, never in a vendored subchart.

Run from the repository root:

    python3 platform/vault/check_secret_access.py            # the check
    python3 platform/vault/check_secret_access.py --inventory # namespace -> keys read
"""
from __future__ import annotations

import argparse
import copy
import fnmatch
import pathlib
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
TABLE_PATH = REPO_ROOT / "platform" / "vault" / "secret-access.yaml"

STORE_KIND = "SecretStore"
STORE_NAME = "vault"
SERVICE_ACCOUNT = "vault-reader"
KV_MOUNT = "zuno"

# Values every render gets: the ADR-0048 checks.yaml guard of the operator
# charts refuses to render without a discovered channel/catalog/package, which
# Ansible injects at apply time. Placeholders are enough - they only reach the
# Subscription, never an ExternalSecret.
GLOBAL_VALUES: Dict[str, Any] = {
    "operator": {
        "subscription": {
            "name": "placeholder",
            "operator": {"name": "placeholder", "channel": "placeholder", "source": {"name": "placeholder"}},
        }
    }
}

# Values Ansible injects (gitops_app_extra_helm_values) that switch an
# ExternalSecret on in a real install. Rendering them on keeps those keys
# inside the check: a toggle any cluster's inventory can flip must not read
# a key the table does not grant. Toggles nothing in Ansible sets (a chart
# default someone would have to edit, e.g. ai-gateway maasAdapter.apiKeyEnabled,
# lightspeed-config credential.apiKeyEnabled, models lmEval.enabled, mlops
# postgres.enabled) are deliberately NOT rendered: their keys stay ungranted,
# and flipping one fails closed (ESO reports "permission denied") until the
# key is added to secret-access.yaml.
APP_OVERLAYS: Dict[str, Dict[str, Any]] = {
    # ansible/roles/external_secrets/tasks/install.yml discovers it.
    "zuno-external-secrets-d1": {"vaultServiceName": "zuno-vault"},
    # ansible/roles/cert_manager/tasks/install.yml (ADR-0211 ACME track).
    "zuno-cert-manager-d1": {"acme": {"enabled": True}},
    # ansible/roles/keycloak/tasks/install.yml, zuno_keycloak_google_oauth_enabled (default true).
    "zuno-keycloak-d1": {"googleOAuth": {"enabled": True}},
    # _postgresql_backup_s3_enabled / _mariadb_backup_s3_enabled.
    "zuno-postgresql-d1": {"backups": {"s3": {"enabled": True}}},
    "zuno-mariadb-d1": {"backups": {"s3": {"enabled": True}}},
    # ansible/clusters/<cluster>.yml stack.backup.
    "zuno-unifai-d1": {"stack": {"backup": {"enabled": True}}},
    # ansible/roles/rhtas_config resolves the TUF root live.
    "zuno-rhtas-config-d1": {"policyOperand": {"trustRoot": {"rootJsonBase64": "cGxhY2Vob2xkZXI="}}},
    # ansible/roles/dify dify_token_proxy_inbound_auth (WP-225 lot C, default false).
    "zuno-token-proxy-dify-d1": {"inboundAuth": {"enabled": True}},
    "zuno-dify-knowledge-d1": {"proxyAuth": {"enabled": True}},
    # lightspeed_identity_mode=serviceIdentity (inventory).
    "zuno-lightspeed-config-d1": {"mcp": {"enabled": True, "identityMode": "serviceIdentity"}},
}

# ExternalSecrets Ansible applies with kubernetes.core.k8s (no chart).
ANSIBLE_GLOBS = ["ansible/**/*.yml", "ansible/**/*.yaml"]


@dataclass
class Source:
    """One rendered object and where it came from (for messages)."""

    origin: str
    namespace: str
    doc: Dict[str, Any]


@dataclass
class Findings:
    failures: List[str] = field(default_factory=list)
    passes: int = 0

    def check(self, condition: bool, message: str) -> None:
        if condition:
            self.passes += 1
        elif message not in self.failures:  # one ExternalSecret reads a key per property
            self.failures.append(message)


# ---------------------------------------------------------------- rendering


def deep_merge(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def helm_template(chart_dir: pathlib.Path, release: str, namespace: str, values: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Renders a copy of the chart without its dependencies (hermetic)."""
    with tempfile.TemporaryDirectory() as tmp:
        dst = pathlib.Path(tmp) / chart_dir.name
        shutil.copytree(chart_dir, dst, ignore=shutil.ignore_patterns("charts", "Chart.lock", "requirements.lock"))
        chart_yaml = yaml.safe_load((dst / "Chart.yaml").read_text())
        chart_yaml.pop("dependencies", None)
        (dst / "Chart.yaml").write_text(yaml.safe_dump(chart_yaml))
        values_file = pathlib.Path(tmp) / "values.yaml"
        values_file.write_text(yaml.safe_dump(values))
        proc = subprocess.run(
            ["helm", "template", release, str(dst), "-f", str(values_file), "--namespace", namespace],
            capture_output=True,
            text=True,
        )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip().splitlines()[0] if proc.stderr.strip() else "helm template failed")
    return [d for d in yaml.safe_load_all(proc.stdout) if isinstance(d, dict)]


def load_raw_dir(directory: pathlib.Path) -> List[Dict[str, Any]]:
    """A raw manifest Application path: the kustomization's resources, or every YAML file."""
    kustomization = directory / "kustomization.yaml"
    files: List[pathlib.Path]
    if kustomization.exists():
        resources = (yaml.safe_load(kustomization.read_text()) or {}).get("resources", [])
        files = [directory / r for r in resources if (directory / r).is_file()]
    else:
        files = sorted(p for p in directory.glob("*.yaml"))
    docs: List[Dict[str, Any]] = []
    for path in files:
        docs.extend(d for d in yaml.safe_load_all(path.read_text()) if isinstance(d, dict))
    return docs


def iter_applications() -> Iterable[Tuple[pathlib.Path, Dict[str, Any]]]:
    for path in sorted((REPO_ROOT / "gitops" / "apps").glob("*/application-*.yaml")):
        for doc in yaml.safe_load_all(path.read_text()):
            if isinstance(doc, dict) and doc.get("kind") == "Application":
                yield path, doc


def charts_with_store_objects() -> Set[str]:
    out: Set[str] = set()
    for tpl in (REPO_ROOT / "gitops" / "charts").glob("*/templates/**/*"):
        if tpl.is_file() and ("kind: ExternalSecret" in tpl.read_text() or "kind: SecretStore" in tpl.read_text()):
            out.add(tpl.relative_to(REPO_ROOT / "gitops" / "charts").parts[0])
    return out


def render_all(findings: Findings) -> List[Source]:
    sources: List[Source] = []
    rendered_charts: Set[str] = set()
    for path, app in iter_applications():
        name = app["metadata"]["name"]
        src = app["spec"]["source"]
        dest_ns = app["spec"].get("destination", {}).get("namespace", "default")
        target = REPO_ROOT / src["path"]
        if (target / "Chart.yaml").exists():
            values = yaml.safe_load(src.get("helm", {}).get("values", "") or "") or {}
            values = deep_merge(deep_merge(GLOBAL_VALUES, values), APP_OVERLAYS.get(name, {}))
            try:
                docs = helm_template(target, src.get("helm", {}).get("releaseName", name), dest_ns, values)
            except RuntimeError as exc:
                findings.check(False, f"{name}: helm template {src['path']} failed: {exc}")
                continue
            rendered_charts.add(target.name)
        elif target.is_dir():
            docs = load_raw_dir(target)
        else:
            findings.check(False, f"{name}: source path {src['path']} does not exist")
            continue
        for doc in docs:
            ns = doc.get("metadata", {}).get("namespace") or dest_ns
            sources.append(Source(f"{name} ({path.relative_to(REPO_ROOT)})", ns, doc))
    for chart in sorted(charts_with_store_objects() - rendered_charts):
        findings.check(False, f"chart {chart} has ExternalSecret/SecretStore templates but no gitops/apps Application renders it")
    for doc, origin in iter_ansible_externalsecrets():
        sources.append(Source(origin, doc.get("metadata", {}).get("namespace", ""), doc))
    return sources


def _walk(node: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def iter_ansible_externalsecrets() -> Iterable[Tuple[Dict[str, Any], str]]:
    seen: Set[pathlib.Path] = set()
    for pattern in ANSIBLE_GLOBS:
        for path in REPO_ROOT.glob(pattern):
            if path in seen or "ExternalSecret" not in path.read_text():
                continue
            seen.add(path)
            try:
                tree = list(yaml.safe_load_all(path.read_text()))
            except yaml.YAMLError:
                continue
            for node in _walk(tree):
                definition = node.get("definition")
                if isinstance(definition, dict) and definition.get("kind") == "ExternalSecret" and "spec" in definition:
                    yield definition, str(path.relative_to(REPO_ROOT))


# ---------------------------------------------------------------- the rules


def load_table(path: pathlib.Path = TABLE_PATH) -> Dict[str, List[str]]:
    data = yaml.safe_load(path.read_text()) or {}
    return {ns: list((entry or {}).get("keys") or []) for ns, entry in (data.get("namespaces") or {}).items()}


def key_allowed(key: str, grants: List[str]) -> Optional[str]:
    """The grant that covers `key`, or None. `prefix/*` covers prefix/<anything>."""
    for grant in grants:
        if grant == key:
            return grant
        if grant.endswith("/*") and key.startswith(grant[:-1]):
            return grant
    return None


def _store_ref_ok(ref: Optional[Dict[str, Any]]) -> bool:
    return bool(ref) and ref.get("kind", "SecretStore") == STORE_KIND and ref.get("name") == STORE_NAME


def externalsecret_reads(doc: Dict[str, Any]) -> List[Tuple[str, Optional[Dict[str, Any]]]]:
    """(key, store ref used) for every Vault read; generator entries read no store."""
    spec = doc.get("spec", {}) or {}
    default_ref = spec.get("secretStoreRef")
    reads: List[Tuple[str, Optional[Dict[str, Any]]]] = []
    for entry in spec.get("data", []) or []:
        source = entry.get("sourceRef") or {}
        if source.get("generatorRef"):
            continue
        reads.append((str(entry.get("remoteRef", {}).get("key", "")), source.get("storeRef") or default_ref))
    for entry in spec.get("dataFrom", []) or []:
        source = entry.get("sourceRef") or {}
        if source.get("generatorRef"):
            continue
        ref = source.get("storeRef") or default_ref
        if "extract" in entry:
            reads.append((str(entry["extract"].get("key", "")), ref))
        if "find" in entry:
            # A find lists keys under a path: only a prefix grant can cover it.
            path = str(entry["find"].get("path", "")).rstrip("/")
            reads.append((f"{path}/*" if path else "*", ref))
    return reads


def check_sources(sources: List[Source], table: Dict[str, List[str]], findings: Findings) -> Dict[str, Set[str]]:
    used: Dict[str, Set[str]] = {ns: set() for ns in table}
    stores: Dict[str, List[Source]] = {}
    servers: Set[str] = set()
    for src in sources:
        kind = src.doc.get("kind")
        name = src.doc.get("metadata", {}).get("name", "?")
        where = f"{src.namespace}/{name} [{src.origin}]"
        if kind == "ClusterSecretStore":
            findings.check(False, f"ClusterSecretStore {name} rendered [{src.origin}]: ADR-0602 allows only per-namespace SecretStores")
        elif kind == "SecretStore":
            stores.setdefault(src.namespace, []).append(src)
            findings.check(name == STORE_NAME, f"SecretStore {where}: must be named {STORE_NAME!r}")
            vault = src.doc.get("spec", {}).get("provider", {}).get("vault", {}) or {}
            k8s = vault.get("auth", {}).get("kubernetes", {}) or {}
            servers.add(str(vault.get("server")))
            findings.check(src.namespace in table, f"SecretStore {where}: namespace not in {TABLE_PATH.name}")
            findings.check(k8s.get("role") == f"ns-{src.namespace}", f"SecretStore {where}: Vault role must be ns-{src.namespace}, got {k8s.get('role')!r}")
            findings.check((k8s.get("serviceAccountRef") or {}).get("name") == SERVICE_ACCOUNT, f"SecretStore {where}: serviceAccountRef must be {SERVICE_ACCOUNT!r}")
            findings.check((k8s.get("serviceAccountRef") or {}).get("namespace") in (None, src.namespace), f"SecretStore {where}: serviceAccountRef must stay in its own namespace")
            findings.check(vault.get("path") == KV_MOUNT and vault.get("version") == "v2", f"SecretStore {where}: must use KV v2 mount {KV_MOUNT!r}")
        elif kind == "ExternalSecret":
            for key, ref in externalsecret_reads(src.doc):
                findings.check(
                    _store_ref_ok(ref),
                    f"ExternalSecret {where}: store ref {ref!r} - must be {{kind: {STORE_KIND}, name: {STORE_NAME}}}",
                )
                grants = table.get(src.namespace)
                if grants is None:
                    findings.check(False, f"ExternalSecret {where}: namespace has no entry in {TABLE_PATH.name} (reads {key})")
                    continue
                if key.startswith(f"{KV_MOUNT}/"):
                    findings.check(False, f"ExternalSecret {where}: key {key!r} repeats the mount; keys are relative to {KV_MOUNT}/")
                grant = key_allowed(key, grants)
                findings.check(grant is not None, f"ExternalSecret {where}: key {key!r} not granted to {src.namespace} in {TABLE_PATH.name}")
                if grant:
                    used[src.namespace].add(grant)
    findings.check(len(servers) <= 1, f"SecretStores disagree on the Vault server: {sorted(servers)}")
    for ns in sorted(table):
        count = len(stores.get(ns, []))
        findings.check(count == 1, f"{ns}: expected exactly one rendered SecretStore {STORE_NAME!r}, found {count}")
        findings.check(bool(table[ns]), f"{ns}: no keys listed - drop the namespace from {TABLE_PATH.name}")
        for grant in table[ns]:
            findings.check(grant in used[ns], f"{ns}: grant {grant!r} is read by no ExternalSecret - remove it (least privilege)")
    return used


def inventory(sources: List[Source]) -> Dict[str, Set[str]]:
    out: Dict[str, Set[str]] = {}
    for src in sources:
        if src.doc.get("kind") == "ExternalSecret":
            for key, _ in externalsecret_reads(src.doc):
                out.setdefault(src.namespace, set()).add(key)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--inventory", action="store_true", help="print namespace -> keys read and exit")
    args = parser.parse_args(argv)

    findings = Findings()
    sources = render_all(findings)
    if args.inventory:
        for ns, keys in sorted(inventory(sources).items()):
            print(f"{ns}:")
            for key in sorted(keys):
                print(f"  - {key}")
        return 0
    table = load_table()
    check_sources(sources, table, findings)
    es_count = sum(1 for s in sources if s.doc.get("kind") == "ExternalSecret")
    store_count = sum(1 for s in sources if s.doc.get("kind") == "SecretStore")
    print(f"Rendered {es_count} ExternalSecrets and {store_count} SecretStores; table: {len(table)} namespaces, "
          f"{sum(len(v) for v in table.values())} grants.")
    for failure in findings.failures:
        print(f"FAIL {failure}")
    print(f"{findings.passes} checks passed, {len(findings.failures)} failed")
    print("RESULT: " + ("PASS" if not findings.failures else "FAIL"))
    return 0 if not findings.failures else 1


if __name__ == "__main__":
    sys.exit(main())
