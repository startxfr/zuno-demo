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
    """Keycloak validates the secret it resolves through KC_VAULT from the
    ExternalSecret's Vault path (its BFF consumer was retired in WP-156; the
    client stays for MaaS). If the projected-volume file name and the
    ExternalSecret ever disagree, the failure is a 401 that reads like a
    permissions problem."""
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


def test_the_jobs_sign_in_as_the_automation_account_and_create_the_admins() -> None:
    """ADR-0595: no helm needed, the templates are read as text.

    The bootstrap admin is flagged temporary by Keycloak and must be disableable
    without breaking anything: both Jobs prefer the permanent automation account
    (optional Secret, so a cluster whose Vault is not seeded yet still runs on the
    bootstrap account), and the reconcile Job creates the two permanent users.
    """
    templates = CHART / "templates"
    reconcile = (templates / "job-client-reconcile.yaml").read_text()
    personas = (templates / "job-eval-personas.yaml").read_text()
    for name, text in (("client-reconcile", reconcile), ("eval-personas", personas)):
        assert ".Values.automationSecretName" in text, f"{name} does not read the automation Secret"
        assert "optional: true" in text, f"{name}: the automation Secret must be optional (first run)"
        assert "kc_login()" in text, f"{name} has no automation-first login"
        assert text.index("KC_AUTOMATION_USER") < text.index("KC_ADMIN_USER", text.index("kc_login()")), (
            f"{name}: the automation account must be tried before the bootstrap admin"
        )
    assert "ensure_master_admin" in reconcile and "--rolename admin" in reconcile
    assert ".Values.consoleSecretName" in reconcile
    for es, path in (("externalsecret-automation.yaml", "keycloak/automation"),
                     ("externalsecret-console.yaml", "keycloak/console")):
        assert path in (templates / es).read_text(), f"{es} does not read Vault {path}"


# --- ADR-0602 clause 3 / ADR-0603 M5, M6 / WP-223: realm settings ------------

BRUTE_FORCE_KEYS = {
    "bruteForceProtected": True,
    "permanentLockout": False,
    "failureFactor": 30,
    "waitIncrementSeconds": 60,
    "maxFailureWaitSeconds": 900,
    "quickLoginCheckMilliSeconds": 1000,
    "minimumQuickLoginWaitSeconds": 60,
    "maxDeltaTimeSeconds": 43200,
}
_profile_renders: dict[str, list[dict]] = {}


def _render_profile(profile: str) -> list[dict]:
    """Render with securityProfile=<profile>; [] when helm is absent."""
    if profile not in _profile_renders:
        if shutil.which("helm") is None:
            print("SKIP: helm not on PATH - profile rendering tests cannot run")
            _profile_renders[profile] = []
        else:
            import yaml

            out = subprocess.run(
                ["helm", "template", str(CHART), "--set", "keycloak.enabled=true",
                 "--set", f"clusterBaseDomain={TEST_DOMAIN}", "--set", f"securityProfile={profile}"],
                capture_output=True, text=True, check=True,
            )
            _profile_renders[profile] = [d for d in yaml.safe_load_all(out.stdout) if d]
    return _profile_renders[profile]


def _realm_settings(profile: str) -> dict | None:
    for d in _render_profile(profile):
        if d.get("kind") == "ConfigMap" and d["metadata"]["name"] == "zuno-keycloak-clients":
            return json.loads(d["data"]["realm-settings.json"])
    return None


def test_the_realm_file_starts_with_brute_force_protection() -> None:
    """A fresh import must already be protected: the Job only runs after it."""
    realm = _load_realm()
    for key, value in BRUTE_FORCE_KEYS.items():
        assert realm.get(key) == value, f"realm-zuno.json {key}={realm.get(key)!r}, expected {value!r}"
    # hardened-only keys go through the Job, never into the import file
    assert "passwordPolicy" not in realm, "passwordPolicy belongs to the hardened Job settings only"


def test_realm_settings_profile_split() -> None:
    demo, hardened = _realm_settings("demo"), _realm_settings("hardened")
    if demo is None and hardened is None and shutil.which("helm") is None:
        return
    assert demo is not None and hardened is not None, "realm-settings.json missing from the ConfigMap"
    for name, settings in (("demo", demo), ("hardened", hardened)):
        for key, value in BRUTE_FORCE_KEYS.items():
            assert settings.get(key) == value, f"{name}: {key}={settings.get(key)!r}, expected {value!r}"
    assert "passwordPolicy" not in demo, "demo must not set a password policy"
    assert "ssoSessionIdleTimeout" not in demo, "demo must leave the realm file's idle timeout alone"
    assert hardened.get("passwordPolicy") == "length(12) and digits(1) and notUsername"
    assert hardened.get("ssoSessionIdleTimeout") == 3600


def test_an_unknown_profile_fails_the_render() -> None:
    if shutil.which("helm") is None:
        return
    out = subprocess.run(
        ["helm", "template", str(CHART), "--set", "keycloak.enabled=true", "--set", "securityProfile=hardend"],
        capture_output=True, text=True,
    )
    assert out.returncode != 0 and "securityProfile must be demo or hardened" in out.stderr


def test_the_job_applies_realm_settings_and_totp_only_when_hardened() -> None:
    for profile in ("demo", "hardened"):
        job = next((d for d in _render_profile(profile) if d.get("kind") == "Job"
                    and d["metadata"]["name"] == "zuno-keycloak-client-reconcile"), None)
        if job is None:
            return
        container = job["spec"]["template"]["spec"]["containers"][0]
        env = {e["name"]: e.get("value") for e in container["env"]}
        assert env.get("KC_SECURITY_PROFILE") == profile
        script = container["command"][2]
        line = next((ln for ln in script.splitlines()
                     if "update" in ln and 'realms/$KC_REALM' in ln and "realm-settings.json" in ln), None)
        assert line is not None, "the Job never applies realm-settings.json"
        assert " -m" in line, "the realm update must merge (only the listed keys change): " + line.strip()
        # applied after the realm wait, before any client work
        assert script.index('never became reachable') < script.index(line) < script.index("/realm/client-*.json")
        # TOTP: guarded by the profile, console account only, never the automation account
        assert 'requiredActions=["CONFIGURE_TOTP"]' in script
        assert '[ "$KC_SECURITY_PROFILE" = "hardened" ]' in script
        totp_block = script[script.index('[ "$KC_SECURITY_PROFILE" = "hardened" ]'):]
        totp_block = totp_block[:totp_block.index("created=0")]
        assert "KC_CONSOLE_USER" in totp_block and "KC_AUTOMATION_USER" not in totp_block, (
            "CONFIGURE_TOTP on the automation account would make Keycloak refuse every Job's password grant"
        )
        proc = subprocess.run(["bash", "-n"], input=script, capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr


def test_no_client_password_grant_changed_by_the_profile() -> None:
    """User decision (WP-223): openshift and aap keep directAccessGrantsEnabled."""
    realm = _load_realm()
    grants = {c["clientId"]: c.get("directAccessGrantsEnabled") for c in realm["clients"]}
    for cid in ("openshift", "aap"):
        if cid in grants:
            assert grants[cid] is True, f"{cid} must keep the password grant (user decision)"


TESTS = [
    test_the_realm_file_starts_with_brute_force_protection,
    test_realm_settings_profile_split,
    test_an_unknown_profile_fails_the_render,
    test_the_job_applies_realm_settings_and_totp_only_when_hardened,
    test_no_client_password_grant_changed_by_the_profile,
    test_the_realm_file_is_valid_json_and_declares_the_admin_client,
    test_client_text_fields_fit_keycloak_s_columns,
    test_no_service_account_may_write_to_the_realm,
    test_every_service_account_entry_matches_a_real_client,
    test_the_reconcile_configmap_substitutes_the_cluster_domain,
    test_one_configmap_entry_per_declared_client,
    test_the_job_mounts_what_the_configmap_publishes,
    test_the_admin_client_secret_reaches_both_sides,
    test_the_reconcile_script_is_valid_bash,
    test_the_jobs_sign_in_as_the_automation_account_and_create_the_admins,
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


# --- WP-169: evaluation personas ---------------------------------------------


def test_each_eval_persona_copies_its_source_users_groups() -> None:
    cm = _by_kind("ConfigMap", "zuno-keycloak-eval-personas")
    if cm is None:
        return
    import yaml

    values = yaml.safe_load((CHART / "values.yaml").read_text())
    users = {u["username"]: u for u in _load_realm()["users"]}
    lines = {
        line.split()[0]: line.split()[1:]
        for line in cm["data"]["personas.txt"].splitlines()
        if line.strip()
    }
    assert values["evalPersonas"], "no evaluation persona declared"
    for p in values["evalPersonas"]:
        assert p["username"].startswith(("eval-", "stress-")), (
            f"{p['username']}: evaluation personas carry the eval- or stress- prefix, "
            "so they never collide with a demo persona"
        )
        assert p["username"] not in users, (
            f"{p['username']} is also a realm-file user: the Job owns eval personas"
        )
        # the Job adds evalPersonasGroup (when set) to every group of the source persona, or to the explicit
        # `groups` list of a probe persona (ADR-0610/WP-245: eval-ai-dev-01 holds /ocp-ai-dev only)
        base = p["groups"] if p.get("groups") else users[p["copyOf"]]["groups"]
        expected = list(base) + (
            [values["evalPersonasGroup"]] if values.get("evalPersonasGroup") else []
        )
        assert lines[p["username"]] == expected


def test_the_eval_personas_job_runs_after_the_client_reconcile() -> None:
    job = _by_kind("Job", "zuno-keycloak-eval-personas")
    reconcile = _by_kind("Job", "zuno-keycloak-client-reconcile")
    if job is None or reconcile is None:
        return
    ann = job["metadata"]["annotations"]
    assert ann["argocd.argoproj.io/hook"] == "Sync"
    assert ann["argocd.argoproj.io/hook-delete-policy"] == "BeforeHookCreation"
    assert int(ann["argocd.argoproj.io/sync-wave"]) > int(
        reconcile["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"]
    ), "the reconcile Job creates the agent_* groups the personas join"
    assert job["spec"]["activeDeadlineSeconds"] > 0
    spec = job["spec"]["template"]["spec"]
    volumes = {v["name"]: v for v in spec["volumes"]}
    assert volumes["personas"]["configMap"]["name"] == "zuno-keycloak-eval-personas"
