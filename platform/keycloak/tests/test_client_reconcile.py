"""ADR-0530/WP-091 acceptance tests for the Keycloak client-reconcile path.

These are the checks that would have caught the two ways this mechanism can
fail silently rather than loudly:

  * the reconcile Job writing the UNSUBSTITUTED `apps.mycluster.example.com`
    placeholder into every live client's redirect URIs - which would break
    every agent login on the first run, with a green Job;
  * the realm file quietly granting `manage-users` to a service account,
    which no rendering error would ever surface.

Standalone script, same convention as platform/testing/tests/ - not pytest.
Run from the repository root:

    python3 platform/keycloak/tests/test_client_reconcile.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHART = REPO_ROOT / "gitops" / "charts" / "keycloak"
REALM_FILE = CHART / "files" / "realm-zuno.json"

TEST_DOMAIN = "apps.test-cluster.example.org"
PLACEHOLDER_DOMAIN = "apps.mycluster.example.com"

# Only these three realm-management roles are defensible for the colleague and
# group lookups (ADR-0213 Security, extended by ADR-0527). Anything that can
# WRITE to the realm is out of bounds by construction, not by review.
ALLOWED_REALM_MANAGEMENT_ROLES = {"view-users", "query-users", "query-groups"}

_rendered: list[dict] | None = None


def _load_realm() -> dict:
    return json.loads(REALM_FILE.read_text())


def _render() -> list[dict]:
    """Render the chart once and cache it. Returns [] when helm is absent, so
    the file-only tests below still run on a machine without it."""
    global _rendered
    if _rendered is not None:
        return _rendered
    if shutil.which("helm") is None:
        print("SKIP: helm not on PATH - rendering tests cannot run")
        _rendered = []
        return _rendered

    import yaml  # imported late: only the rendering tests need it

    out = subprocess.run(
        [
            "helm", "template", str(CHART),
            "--set", "keycloak.enabled=true",
            "--set", f"clusterBaseDomain={TEST_DOMAIN}",
        ],
        capture_output=True, text=True, check=True,
    )
    _rendered = [d for d in yaml.safe_load_all(out.stdout) if d]
    return _rendered


def _by_kind(kind: str, name: str) -> dict | None:
    for d in _render():
        if d.get("kind") == kind and d.get("metadata", {}).get("name") == name:
            return d
    return None


def test_the_realm_file_is_valid_json_and_declares_the_admin_client() -> None:
    realm = _load_realm()
    client = next((c for c in realm["clients"] if c["clientId"] == "zuno-admin-api"), None)
    assert client is not None, "zuno-admin-api is not declared in realm-zuno.json"

    # A client-credentials client that also accepts a browser or password
    # login is a different, much larger, trust boundary than ADR-0213 reviewed.
    assert client["serviceAccountsEnabled"] is True
    assert client["standardFlowEnabled"] is False, "must not be a login client"
    assert client["implicitFlowEnabled"] is False
    assert client["directAccessGrantsEnabled"] is False, "must not accept a password grant"
    assert client["publicClient"] is False
    assert client.get("redirectUris") == []


def test_client_text_fields_fit_keycloak_s_columns() -> None:
    """Keycloak stores CLIENT.DESCRIPTION and CLIENT.NAME as varchar(255).
    Overrun it and the Admin API answers a bare `[unknown_error]`, with the
    real cause - "value too long for type character varying(255)" - visible
    only in the Keycloak server log.

    Not hypothetical. On 2026-08-27 at 23:30Z the first live reconcile
    updated all ten existing clients, then failed creating zuno-admin-api on a
    283-character description. The Job burned its whole backoffLimit while the
    diagnosis sat in a log nobody was tailing. Cheap to assert here, expensive
    to find there.
    """
    realm = _load_realm()
    over = []
    for c in realm["clients"]:
        for field in ("description", "name"):
            value = c.get(field) or ""
            if len(value) > 255:
                over.append(f"{c['clientId']}.{field} is {len(value)} chars")
    assert not over, "Keycloak stores these as varchar(255): " + "; ".join(over)


def test_no_service_account_may_write_to_the_realm() -> None:
    """The check that matters most here, and the one a rendering error would
    never reveal: least privilege on every service account, not just today's."""
    realm = _load_realm()
    offenders = []
    for user in realm.get("users", []):
        if not user.get("serviceAccountClientId"):
            continue
        for container, roles in (user.get("clientRoles") or {}).items():
            if container != "realm-management":
                continue
            for role in roles:
                if role not in ALLOWED_REALM_MANAGEMENT_ROLES:
                    offenders.append(f"{user['username']} -> realm-management/{role}")
    assert not offenders, (
        "service account granted a realm-management role beyond read-only lookup: "
        + ", ".join(offenders)
    )


def test_every_service_account_entry_matches_a_real_client() -> None:
    """A service-account user whose client does not exist, or whose client has
    serviceAccountsEnabled false, makes the reconcile Job fail at `add-roles`
    with a message that points at the role rather than the cause."""
    realm = _load_realm()
    clients = {c["clientId"]: c for c in realm["clients"]}
    for user in realm.get("users", []):
        cid = user.get("serviceAccountClientId")
        if not cid:
            continue
        assert cid in clients, f"service account for unknown client {cid!r}"
        assert clients[cid].get("serviceAccountsEnabled") is True, (
            f"client {cid!r} has a service-account role mapping but serviceAccountsEnabled is not true"
        )
        assert user["username"] == f"service-account-{cid}", (
            "kcadm resolves the account by the username Keycloak generates; "
            f"{user['username']!r} would not be found"
        )


def test_the_reconcile_configmap_substitutes_the_cluster_domain() -> None:
    """The bug this guards against is silent and total: realmimport.yaml does
    this substitution, so a configmap that forgot it would hand the Job a
    placeholder hostname and rewrite every client's redirect URIs with it."""
    cm = _by_kind("ConfigMap", "zuno-keycloak-clients")
    if cm is None:
        return  # helm absent; already reported
    blob = json.dumps(cm["data"])
    assert PLACEHOLDER_DOMAIN not in blob, (
        "the client ConfigMap still carries the placeholder domain - the reconcile "
        "Job would write it into live redirect URIs"
    )
    assert TEST_DOMAIN in blob, "the cluster domain was never substituted in"


def test_one_configmap_entry_per_declared_client() -> None:
    cm = _by_kind("ConfigMap", "zuno-keycloak-clients")
    if cm is None:
        return
    realm = _load_realm()
    for c in realm["clients"]:
        assert f"client-{c['clientId']}.json" in cm["data"], (
            f"client {c['clientId']} declared in the realm but not published to the Job"
        )


def test_the_job_mounts_what_the_configmap_publishes() -> None:
    job = _by_kind("Job", "zuno-keycloak-client-reconcile")
    if job is None:
        return
    spec = job["spec"]["template"]["spec"]
    names = {v["name"]: v for v in spec["volumes"]}
    assert names["realm"]["configMap"]["name"] == "zuno-keycloak-clients"

    ann = job["metadata"]["annotations"]
    assert ann["argocd.argoproj.io/hook"] == "Sync", (
        "must be a Sync hook, not PreSync - see ADR-0313's 2026-08-14 deadlock"
    )
    assert ann["argocd.argoproj.io/hook-delete-policy"] == "BeforeHookCreation"
    assert job["spec"]["activeDeadlineSeconds"] > 0, (
        "an unbounded hook Job hangs the sync forever on CreateContainerConfigError"
    )


def test_the_admin_client_secret_reaches_both_sides() -> None:
    """Keycloak validates the secret it resolves through KC_VAULT; agent-bff
    presents the one it reads from Vault. Two paths, one value - if the
    projected-volume file name and the ExternalSecret ever disagree, the
    failure is a 401 that reads like a permissions problem."""
    es = _by_kind("ExternalSecret", "zuno-admin-api-client-secret")
    if es is None:
        return
    assert es["spec"]["data"][0]["remoteRef"]["key"] == "keycloak/zuno-admin-api-client"

    kc = _by_kind("Keycloak", "zuno")
    assert kc is not None
    sources = kc["spec"]["unsupported"]["podTemplate"]["spec"]["volumes"]
    projected = [v for v in sources if v["name"] == "vault-secrets"][0]["projected"]["sources"]
    entries = [
        item["path"]
        for src in projected
        if src.get("secret", {}).get("name") == "zuno-admin-api-client-secret"
        for item in src["secret"]["items"]
    ]
    # Single underscores silently fail every runtime lookup - the file vault
    # provider escapes each underscore of the KEY as "__".
    assert entries == ["zuno_admin__api__client__secret"], (
        f"KC_VAULT file name is wrong or missing: {entries}"
    )

    realm = _load_realm()
    client = next(c for c in realm["clients"] if c["clientId"] == "zuno-admin-api")
    assert client["secret"] == "${vault.admin_api_client_secret}", (
        "the realm reference and the KC_VAULT file name must describe the same key"
    )


def test_the_reconcile_script_is_valid_bash() -> None:
    job = _by_kind("Job", "zuno-keycloak-client-reconcile")
    if job is None:
        return
    if shutil.which("bash") is None:
        print("SKIP: bash not on PATH")
        return
    script = job["spec"]["template"]["spec"]["containers"][0]["command"][2]
    proc = subprocess.run(["bash", "-n"], input=script, capture_output=True, text=True)
    assert proc.returncode == 0, f"reconcile script is not valid bash:\n{proc.stderr}"
    assert "set -euo pipefail" in script, "the Job must fail loudly (ADR-0530 clause 7)"

    # kcadm: "Merge is automatically enabled unless --file is specified". A
    # bare `-f` on update PUTs the file as the entire representation, dropping
    # the protocolMapper ids and the server-managed `realm_client` attribute
    # Keycloak maintains itself - measured against the live realm on
    # 2026-08-28, this would have hit all ten existing clients.
    update_line = next(
        (ln for ln in script.splitlines() if "update " in ln and "clients/$id" in ln), None
    )
    assert update_line is not None, "no client update call found in the reconcile script"
    assert " -m" in update_line or " --merge" in update_line, (
        "the update path must merge, not replace: " + update_line.strip()
    )


def test_agent_charts_reference_the_admin_secret_optionally() -> None:
    """The sequencing trap. ansible/roles/vault seeds the Vault path; ArgoCD
    syncs these charts. Nothing orders the two, so every agent chart WILL sync
    before the Secret exists at least once. A non-optional secretKeyRef makes
    that a CreateContainerConfigError and takes the whole BFF down - chat
    included - to enable a feature that is meant to fail closed on its own."""
    if shutil.which("helm") is None:
        print("SKIP: helm not on PATH")
        return

    import yaml

    for agent in ("tekos", "comage", "advantage", "finage"):
        chart = REPO_ROOT / "gitops" / "charts" / agent
        out = subprocess.run(
            ["helm", "template", str(chart)], capture_output=True, text=True, check=True
        )
        found = False
        for doc in yaml.safe_load_all(out.stdout):
            if not doc or doc.get("kind") != "Deployment":
                continue
            for container in doc["spec"]["template"]["spec"]["containers"]:
                for env in container.get("env") or []:
                    ref = (env.get("valueFrom") or {}).get("secretKeyRef")
                    if not ref or env["name"] != "KEYCLOAK_ADMIN_CLIENT_SECRET":
                        continue
                    found = True
                    assert ref.get("optional") is True, (
                        f"{agent}: KEYCLOAK_ADMIN_CLIENT_SECRET must be optional, "
                        "or the BFF cannot start before the Vault seed exists"
                    )
        assert found, f"{agent} chart does not wire KEYCLOAK_ADMIN_CLIENT_SECRET at all"


TESTS = [
    test_the_realm_file_is_valid_json_and_declares_the_admin_client,
    test_client_text_fields_fit_keycloak_s_columns,
    test_no_service_account_may_write_to_the_realm,
    test_every_service_account_entry_matches_a_real_client,
    test_the_reconcile_configmap_substitutes_the_cluster_domain,
    test_one_configmap_entry_per_declared_client,
    test_the_job_mounts_what_the_configmap_publishes,
    test_the_admin_client_secret_reaches_both_sides,
    test_the_reconcile_script_is_valid_bash,
    test_agent_charts_reference_the_admin_secret_optionally,
]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"ERROR {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
