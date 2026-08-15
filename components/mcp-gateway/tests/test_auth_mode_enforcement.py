"""WP-26 (ADR-0208) acceptance tests: the invoke_tool endpoint's auth_mode
enforcement (main.py, using the real repo bindings/policy/agent files -
same "load the real files" pattern as tests/test_bindings.py) and
app/delegation.py's fail-closed delegated-token contract.

Run directly:

    cd components/mcp-gateway && python3 tests/test_auth_mode_enforcement.py
"""
from __future__ import annotations

import io
import logging
import os
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
# Point every module-level singleton app.main constructs at import time at
# the REAL repo files (default paths are /app/..., the in-image location) -
# must be set before `import app.main` triggers those constructions, same
# pattern components/agent-runtime/tests/test_retrieve_metadata.py uses
# for AGENTS_DIR.
os.environ.setdefault("TOOL_BINDINGS_PATH", str(_REPO_ROOT / "platform/bindings/tools/tool-bindings.yaml"))
os.environ.setdefault("TOOL_POLICY_PATH", str(_REPO_ROOT / "policies/tools/tool-policy.yaml"))
os.environ.setdefault(
    "DATA_CLASSIFICATION_PATH", str(_REPO_ROOT / "policies/data-classification/classification.yaml")
)
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

from fastapi.testclient import TestClient  # noqa: E402

import app.main as gateway_main  # noqa: E402
from app import delegation  # noqa: E402
from app.auth import CallerIdentity, validate_token  # noqa: E402

_FAKE_IDENTITY = CallerIdentity(
    sub="consultant-1", groups=["consultant"], raw_claims={}, token="caller-jwt"
)


def _client() -> TestClient:
    assert gateway_main.binding_registry.loaded, gateway_main.binding_registry.load_error
    assert gateway_main.policy_store.loaded, gateway_main.policy_store.load_error
    gateway_main.app.dependency_overrides[validate_token] = lambda: _FAKE_IDENTITY
    return TestClient(gateway_main.app)


def _invoke(client: TestClient, tool: str, agent: str, task: str, body: dict) -> "object":
    return client.post(
        f"/v1/tools/{tool}/invoke",
        json=body,
        headers={"X-Zuno-Agent": agent, "X-Zuno-Task": task, "X-Zuno-Data-Classification": "C1"},
    )


def test_delegated_user_binding_denies_without_a_delegated_token() -> None:
    """drive.document.search (list_drive_files) is delegated-user - with no
    token resolver installed (app.delegation's default: no live broker
    integration, see that module's docstring), every call must be denied,
    never silently served by a shared credential."""
    delegation.set_token_resolver(None)
    client = _client()
    try:
        resp = _invoke(client, "list_drive_files", "tekos", "check-my-drive-docs", {"folder": "x"})
        assert resp.status_code == 403, resp.text
        assert "delegated" in resp.json()["detail"].lower()
    finally:
        gateway_main.app.dependency_overrides.clear()


def test_delegated_user_binding_succeeds_once_a_token_resolves() -> None:
    delegation.set_token_resolver(lambda provider, sub: "fake-google-token")
    client = _client()
    try:
        resp = _invoke(client, "list_drive_files", "tekos", "check-my-drive-docs", {"folder": "x"})
        assert resp.status_code == 200, resp.text
    finally:
        delegation.set_token_resolver(None)
        gateway_main.app.dependency_overrides.clear()


def test_revoked_delegated_permission_denies_even_though_policy_allows() -> None:
    """Mock-level revocation (real revocation is the operator check, per
    the WP-26 brief): a resolver that goes from returning a token to
    returning None (simulating the user's Google permission being pulled)
    must deny the very next call, even though the policy intersection
    (agent/task/groups/classification) is unchanged and still allows the
    capability."""
    delegation.set_token_resolver(lambda provider, sub: "fake-google-token")
    client = _client()
    try:
        allowed = _invoke(client, "list_drive_files", "tekos", "check-my-drive-docs", {})
        assert allowed.status_code == 200, allowed.text

        delegation.set_token_resolver(lambda provider, sub: None)  # "revoked"
        denied = _invoke(client, "list_drive_files", "tekos", "check-my-drive-docs", {})
        assert denied.status_code == 403, denied.text
    finally:
        delegation.set_token_resolver(None)
        gateway_main.app.dependency_overrides.clear()


def test_service_identity_binding_never_needs_a_delegated_token() -> None:
    """web.page.search (web_search) is service-identity - must succeed
    with no token resolver installed at all (delegation is never
    consulted for this mode)."""
    delegation.set_token_resolver(None)
    client = _client()
    try:
        resp = _invoke(
            client, "web_search", "tekos", "answer-technical-question", {"query": "openshift ai gpu sizing"}
        )
        assert resp.status_code == 200, resp.text
    finally:
        gateway_main.app.dependency_overrides.clear()


def test_no_token_material_appears_in_the_audit_log_line() -> None:
    """ADR-0208: audit records carry auth_mode + subject/capability/
    binding - never the token itself."""
    secret_token = "super-secret-google-token-value-12345"
    delegation.set_token_resolver(lambda provider, sub: secret_token)
    client = _client()

    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    logger = logging.getLogger("mcp_gateway")
    logger.addHandler(handler)
    try:
        resp = _invoke(client, "list_drive_files", "tekos", "check-my-drive-docs", {})
        assert resp.status_code == 200, resp.text
    finally:
        logger.removeHandler(handler)
        delegation.set_token_resolver(None)
        gateway_main.app.dependency_overrides.clear()

    logged = log_capture.getvalue()
    assert secret_token not in logged
    assert "auth_mode=delegated-user" in logged


TESTS = [
    test_delegated_user_binding_denies_without_a_delegated_token,
    test_delegated_user_binding_succeeds_once_a_token_resolves,
    test_revoked_delegated_permission_denies_even_though_policy_allows,
    test_service_identity_binding_never_needs_a_delegated_token,
    test_no_token_material_appears_in_the_audit_log_line,
]


def main() -> int:
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
