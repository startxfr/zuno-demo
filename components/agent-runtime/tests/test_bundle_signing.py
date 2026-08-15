#!/usr/bin/env python3
"""ADR-0106 tests for AgentRegistry's signature-enforcement path
(`ZUNO_REQUIRE_SIGNED_BUNDLES`). `app/_sign_okf_bundle.py` is only baked
into the built image (Dockerfile `COPY platform/supply-chain/
sign_okf_bundle.py ./app/_sign_okf_bundle.py`), so these tests inject a
fake module at that import path rather than requiring a real `cosign`
binary or a real signed bundle - proving AgentRegistry's own enforcement
logic (existence checks, fail-closed on missing cosign, wrapping
verification failures) independent of the actual cryptography, which
sign_okf_bundle.py's own manual verification (see its docstring) already
covers.

Run directly:

    cd components/agent-runtime && python3 tests/test_bundle_signing.py
"""
from __future__ import annotations

import pathlib
import sys
import types
import unittest.mock as mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
REAL_AGENTS_DIR = REPO_ROOT / "agents"

def _all_real_agent_names() -> list:
    """Derived from the real agents/ tree, not a hardcoded list - WP-41b's
    sixth agent exposed that a literal name list here silently rots every
    time an agent is added (the registry loads EVERY bundle directory, so
    every one needs a fake signature for the enforcement-on happy path)."""
    return sorted(p.name for p in REAL_AGENTS_DIR.iterdir() if (p / "agent.okf.md").exists())


def _install_fake_sign_module(*, verify_error_message: str | None) -> types.ModuleType:
    """Injects a fake `app._sign_okf_bundle` so `AgentRegistry._verify_signature`'s
    lazy `from app import _sign_okf_bundle` resolves to it instead of the
    real (image-only) file. `verify_bundle` raises the fake module's OWN
    `BundleError` (not some unrelated exception class), matching how the
    real module's caller does `except _sign_okf_bundle.BundleError` -
    identity matters here, not just "is an Exception"."""
    fake = types.ModuleType("app._sign_okf_bundle")

    class BundleError(RuntimeError):
        pass

    def verify_bundle(bundle_dir, signature, certificate):  # noqa: ANN001
        if verify_error_message is not None:
            raise BundleError(verify_error_message)

    fake.BundleError = BundleError
    fake.verify_bundle = verify_bundle
    sys.modules["app._sign_okf_bundle"] = fake
    return fake


def _uninstall_fake_sign_module() -> None:
    sys.modules.pop("app._sign_okf_bundle", None)


def test_enforcement_off_by_default_loads_unsigned_bundle() -> None:
    from app.registry import AgentRegistry

    registry = AgentRegistry(agents_dir=str(REAL_AGENTS_DIR), require_signed_bundles=False)
    assert not registry.load_errors, registry.load_errors
    assert registry.get("tekos") is not None


def test_enforcement_on_refuses_a_bundle_with_no_signature_files(tmp_sig_dir) -> None:
    from app.registry import AgentRegistry

    _install_fake_sign_module(verify_error_message=None)
    try:
        registry = AgentRegistry(
            agents_dir=str(REAL_AGENTS_DIR),
            require_signed_bundles=True,
            signatures_dir=str(tmp_sig_dir),  # empty - no .sig/.pem present
        )
    finally:
        _uninstall_fake_sign_module()

    assert registry.get("tekos") is None, "an unsigned bundle must never load when enforcement is on"
    assert any("no signature found" in e for e in registry.load_errors), registry.load_errors


def test_enforcement_on_accepts_a_bundle_whose_signature_verifies(tmp_sig_dir) -> None:
    from app.registry import AgentRegistry

    for name in _all_real_agent_names():
        (tmp_sig_dir / f"{name}.sig").write_text("fake-sig")
        (tmp_sig_dir / f"{name}.pem").write_text("fake-cert")

    _install_fake_sign_module(verify_error_message=None)  # verify_bundle never raises -> "valid"
    try:
        registry = AgentRegistry(
            agents_dir=str(REAL_AGENTS_DIR),
            require_signed_bundles=True,
            signatures_dir=str(tmp_sig_dir),
        )
    finally:
        _uninstall_fake_sign_module()

    assert not registry.load_errors, registry.load_errors
    assert registry.get("tekos") is not None


def test_enforcement_on_refuses_a_tampered_or_invalid_signature(tmp_sig_dir) -> None:
    from app.registry import AgentRegistry

    for name in _all_real_agent_names():
        (tmp_sig_dir / f"{name}.sig").write_text("fake-sig")
        (tmp_sig_dir / f"{name}.pem").write_text("fake-cert")

    _install_fake_sign_module(verify_error_message="digest mismatch")
    try:
        registry = AgentRegistry(
            agents_dir=str(REAL_AGENTS_DIR),
            require_signed_bundles=True,
            signatures_dir=str(tmp_sig_dir),
        )
    finally:
        _uninstall_fake_sign_module()

    assert registry.get("tekos") is None, "a bundle whose signature fails verification must never load"
    assert any("signature verification failed" in e for e in registry.load_errors), registry.load_errors


def test_enforcement_on_without_cosign_binary_refuses_to_construct() -> None:
    from app.registry import AgentRegistry, OkfError

    with mock.patch("shutil.which", return_value=None):
        try:
            AgentRegistry(agents_dir=str(REAL_AGENTS_DIR), require_signed_bundles=True)
            raise AssertionError("expected OkfError when enforcement is on but cosign is missing")
        except OkfError as exc:
            assert "no 'cosign' binary" in str(exc)


TESTS = [
    test_enforcement_off_by_default_loads_unsigned_bundle,
    test_enforcement_on_refuses_a_bundle_with_no_signature_files,
    test_enforcement_on_accepts_a_bundle_whose_signature_verifies,
    test_enforcement_on_refuses_a_tampered_or_invalid_signature,
    test_enforcement_on_without_cosign_binary_refuses_to_construct,
]


def main() -> int:
    import inspect
    import shutil
    import tempfile

    failures = 0
    for test in TESTS:
        params = inspect.signature(test).parameters
        tmp_dir = None
        try:
            if "tmp_sig_dir" in params:
                tmp_dir = pathlib.Path(tempfile.mkdtemp())
                test(tmp_dir)
            else:
                test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
        finally:
            if tmp_dir is not None:
                shutil.rmtree(tmp_dir, ignore_errors=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
