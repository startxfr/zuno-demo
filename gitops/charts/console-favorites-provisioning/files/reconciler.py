#!/usr/bin/env python3
"""ADR-0320 console_favorites_provisioning CronJob reconciler.

Runs periodically (see the CronJob's schedule) rather than once, because a
new Keycloak user can appear at any time and their OpenShift Console
favorites must exist *before* their first Console visit - which requires
knowing their User object's UID ahead of that visit, which requires
pre-creating the User (OpenShift OAuth's `mappingMethod: add`, configured
in gitops/charts/openshift-oauth, then attaches a later real login to this
pre-created User instead of creating a duplicate).

Each run, for every enabled Keycloak user in one of PROFILE_GROUPS:
  1. ensure an OpenShift `User` object named after their Keycloak username
     exists (create if missing, read back if it already exists);
  2. ensure a `ConfigMap user-settings-<uid>` exists in
     openshift-console-user-settings, seeded ONCE from that profile's
     favorites template - never overwritten on a later run, so a user's
     own later customization in the real Console is never clobbered (this
     is the idempotency requirement ADR-0320 calls out explicitly: a
     one-shot provisioner could not clobber anything; a periodic one can,
     and must be written not to);
  3. ensure a scoped `Role`/`RoleBinding` limiting that ConfigMap to the
     user themselves exists, same create-if-missing semantics;
  4. all three carry an ownerReference to the `User` object, so Kubernetes
     garbage-collects them automatically if the User is ever deleted.

`console.favorites`'s internal ConfigMap JSON format is deliberately NOT
computed or interpreted by this script (ADR-0320's Decision: "stays out
of this reconciler's own logic") - each profile's exact value must be
captured once from a real Console session against a template account and
checked into this chart's files/favorites-template-<profile>.json, then
mounted read-only and seeded verbatim. See this chart's README and
ansible/roles/console_favorites_provisioning/README.md for that manual
step - the checked-in files as of this commit are UNVERIFIED PLACEHOLDERS
(no live Console session was available to capture the real format) and
must not be treated as the real key/schema until replaced.

Errors reaching the Keycloak Admin API or the OpenShift API for one user
must not abort the whole run - the next scheduled run retries every user
again, including ones already handled (safe, since steps 2-3 are
create-if-missing).
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import sys
from typing import Any, Dict, List, Optional

import requests
from kubernetes import client, config
from kubernetes.client.rest import ApiException

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("console-favorites-provisioning")

KEYCLOAK_URL = os.environ["KEYCLOAK_URL"]
KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM", "zuno")
KEYCLOAK_CLIENT_ID = os.environ.get("KEYCLOAK_CLIENT_ID", "console-favorites-provisioner")
KEYCLOAK_CLIENT_SECRET = os.environ["KEYCLOAK_CLIENT_SECRET"]

FAVORITES_NAMESPACE = "openshift-console-user-settings"
TEMPLATE_DIR = pathlib.Path(os.environ.get("TEMPLATE_DIR", "/templates"))
PROFILE_GROUPS = ["admin", "zuno-admin", "aidev", "aiops"]
HTTP_TIMEOUT = 10


def get_admin_token() -> str:
    resp = requests.post(
        f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": KEYCLOAK_CLIENT_ID,
            "client_secret": KEYCLOAK_CLIENT_SECRET,
        },
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def group_member_usernames(token: str, group_name: str) -> List[str]:
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(
        f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/groups",
        headers=headers,
        params={"search": group_name},
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    matches = [g for g in r.json() if g["name"] == group_name]
    if not matches:
        log.warning("Keycloak group %r not found in realm %r", group_name, KEYCLOAK_REALM)
        return []

    r = requests.get(
        f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/groups/{matches[0]['id']}/members",
        headers=headers,
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    return [u["username"] for u in r.json() if u.get("enabled", True)]


def ensure_user(custom_api: "client.CustomObjectsApi", username: str) -> Dict[str, Any]:
    try:
        return custom_api.get_cluster_custom_object("user.openshift.io", "v1", "users", username)
    except ApiException as exc:
        if exc.status != 404:
            raise
    log.info("creating User %s", username)
    body = {
        "apiVersion": "user.openshift.io/v1",
        "kind": "User",
        "metadata": {"name": username},
        "identities": [],
    }
    return custom_api.create_cluster_custom_object("user.openshift.io", "v1", "users", body)


def load_favorites_template(profile: str) -> str:
    path = TEMPLATE_DIR / f"favorites-template-{profile}.json"
    return path.read_text()


def owner_reference(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": "user.openshift.io/v1",
        "kind": "User",
        "name": user["metadata"]["name"],
        "uid": user["metadata"]["uid"],
        "blockOwnerDeletion": False,
        "controller": False,
    }


def ensure_favorites_configmap(v1: "client.CoreV1Api", user: Dict[str, Any], profile: str) -> bool:
    """Returns True if created, False if it already existed (no-op)."""
    uid = user["metadata"]["uid"]
    name = f"user-settings-{uid}"
    body = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(
            name=name,
            namespace=FAVORITES_NAMESPACE,
            owner_references=[client.V1OwnerReference(**owner_reference(user))],
        ),
        data={"console.favorites": load_favorites_template(profile)},
    )
    try:
        v1.create_namespaced_config_map(FAVORITES_NAMESPACE, body)
        return True
    except ApiException as exc:
        if exc.status == 409:
            # Idempotency requirement (ADR-0320): never overwrite - a
            # user's own later customization must survive every
            # subsequent reconciliation pass.
            return False
        raise


def ensure_scoping_rbac(rbac_api: "client.RbacAuthorizationV1Api", user: Dict[str, Any]) -> None:
    username = user["metadata"]["name"]
    uid = user["metadata"]["uid"]
    configmap_name = f"user-settings-{uid}"
    rbac_name = f"user-settings-{uid}"
    owner = client.V1OwnerReference(**owner_reference(user))

    role = client.V1Role(
        metadata=client.V1ObjectMeta(name=rbac_name, namespace=FAVORITES_NAMESPACE, owner_references=[owner]),
        rules=[
            client.V1PolicyRule(
                api_groups=[""],
                resources=["configmaps"],
                resource_names=[configmap_name],
                verbs=["get", "update", "patch"],
            )
        ],
    )
    try:
        rbac_api.create_namespaced_role(FAVORITES_NAMESPACE, role)
    except ApiException as exc:
        if exc.status != 409:
            raise

    binding = client.V1RoleBinding(
        metadata=client.V1ObjectMeta(name=rbac_name, namespace=FAVORITES_NAMESPACE, owner_references=[owner]),
        subjects=[client.RbacV1Subject(kind="User", name=username, api_group="rbac.authorization.k8s.io")],
        role_ref=client.V1RoleRef(kind="Role", name=rbac_name, api_group="rbac.authorization.k8s.io"),
    )
    try:
        rbac_api.create_namespaced_role_binding(FAVORITES_NAMESPACE, binding)
    except ApiException as exc:
        if exc.status != 409:
            raise


def reconcile_profile(
    token: str,
    custom_api: "client.CustomObjectsApi",
    v1: "client.CoreV1Api",
    rbac_api: "client.RbacAuthorizationV1Api",
    profile: str,
) -> None:
    usernames = group_member_usernames(token, profile)
    log.info("profile %s: %d Keycloak user(s)", profile, len(usernames))
    for username in usernames:
        try:
            user = ensure_user(custom_api, username)
            created = ensure_favorites_configmap(v1, user, profile)
            ensure_scoping_rbac(rbac_api, user)
            log.info(
                "%s (%s): favorites %s",
                username,
                profile,
                "seeded" if created else "already present, left untouched",
            )
        except Exception:  # noqa: BLE001 - one user's failure must not abort the run
            log.exception("failed reconciling user %r (profile %r) - will retry next run", username, profile)


def main() -> int:
    config.load_incluster_config()
    custom_api = client.CustomObjectsApi()
    v1 = client.CoreV1Api()
    rbac_api = client.RbacAuthorizationV1Api()

    token = get_admin_token()
    for profile in PROFILE_GROUPS:
        reconcile_profile(token, custom_api, v1, rbac_api, profile)
    return 0


if __name__ == "__main__":
    sys.exit(main())
