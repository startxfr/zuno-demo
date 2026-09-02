#!/usr/bin/env python3
"""ADR-0420/ADR-0535 in-cluster supply-chain signing.

`sign-image`/`verify-images` (WP-111/ADR-0535) sign and verify the 14
Priority-1 first-party images keyless via RHTAS - a Keycloak
client-credentials token for the `zuno-signer` identity exchanged for a
short-lived Fulcio certificate, with the signature recorded in Rekor's
transparency log. This REPLACES the `hashivault://` Vault Transit mode
those two operations used before WP-111 (ADR-0420/WP-070) - not because
Vault Transit was insufficient (it remains valid, sufficient, and live for
every other operation below), but because demonstrating RHTAS is this
ADR's actual point (see ADR-0535's Context).

Every OTHER operation (`sign-blob`/`verify-blob`/`sign-okf-bundles`/
`public-key`/`login`/`dry-run`) is untouched and still uses Vault's
Transit-backed platform-signer identity via Kubernetes auth, driving
cosign's native `hashivault://` KMS mode - the GitHub-OIDC/Fulcio/Rekor
keyless model platform/supply-chain/sign_okf_bundle.py and
verify_signatures.py's own historical mode is what WP-069/070 replaced
with this, before RHTAS existed. OKF bundle signing is explicitly out of
ADR-0535's scope (Non-goals - blocked on ADR-0506/ADR-0507).

Operations:

    login       - authenticate to Vault via Kubernetes auth only. Proves the
                  zuno-signer ServiceAccount's role binding actually works
                  (or is actually scoped, if run as a different identity).
    public-key  - export the Transit key's public key. No private material
                  ever leaves Vault - `cosign public-key` reads
                  transit/keys/<name>, never an export endpoint (the key is
                  configured non-exportable, see ansible/roles/vault).
    sign-blob   - `cosign sign-blob --key hashivault://<name> --tlog-upload=false`
                  over an arbitrary file.
    verify-blob - `cosign verify-blob --key <pubkey> --insecure-ignore-tlog=true`.
                  Deliberately takes no Vault address/token: a verifier needs
                  only the committed public key, never Vault access.
    dry-run     - WP-068's own acceptance check: login, export the public
                  key, sign a scratch blob, verify it, then confirm a
                  tampered copy is rejected. Touches no real bundle or
                  image - see docs/roadmap/work-packages/
                  wp-068-vault-transit-signing-backend.md.
    sign-okf-bundles - WP-069: sign every agents/<agent>/ bundle found under
                  --agents-root with sign_okf_bundle.py, then write every
                  {agent}.sig plus the shared public key into Vault KV
                  (--kv-mount/--kv-path), where
                  gitops/charts/agent-runtime/templates/
                  externalsecret-okf-signatures.yaml picks them up.
    sign-image  - WP-111/ADR-0535: signs an OCI image by digest keyless via
                  RHTAS - exchanges the `zuno-signer` Keycloak
                  client-credentials token for a short-lived Fulcio
                  certificate (`--fulcio-url`), signs, and records the
                  signature in Rekor (`--rekor-url`). Replaces the
                  pre-WP-111 `--key hashivault://<name>` mode for this
                  operation only.
    verify-images - WP-111/ADR-0535: verifies every image in a JSON refs
                  file (the shape `verify_signatures.py --list-refs`'s
                  "resolved" array produces) keyless via RHTAS - checks
                  the Fulcio-issued certificate's identity/issuer
                  (`--certificate-identity`/`--certificate-oidc-issuer`)
                  against a real Rekor transparency-log entry
                  (`--rekor-url`), not a static committed public key.
                  Still needs registry auth (a pull), built the same way
                  sign-image's push does. Used by ansible/tasks/
                  verify_image_signatures.yml's in-cluster Job
                  (make d2 check supply-chain).

--tlog-upload=false / --insecure-ignore-tlog=true (sign-blob/verify-blob
only) are load-bearing, not a security loosening: those two operations
still use Vault's Transit-backed key with no self-hosted Rekor behind
them (Vault's own audit device is the in-cluster substitute, see
ADR-0420's Decision), and omitting either flag makes cosign silently
reach out to the public rekor.sigstore.dev - exactly the external
dependency those two operations exist to remove. sign-image/verify-images
are the opposite: RHTAS's self-hosted Rekor (`--rekor-url`) is the whole
point of ADR-0535, so a real transparency-log entry is expected there.

Run from inside a pod using the zuno-signer ServiceAccount (namespace
zuno-ai-build), which Vault's platform-signer Kubernetes-auth role is bound
to (ansible/roles/vault):

    python3 platform/supply-chain/sign_in_cluster.py dry-run
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

import sign_okf_bundle

DEFAULT_VAULT_ADDR = "http://zuno-vault.zuno-vault.svc:8200"
DEFAULT_ROLE = "platform-signer"
DEFAULT_KEY_NAME = "zuno-platform-signer"
DEFAULT_JWT_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
DEFAULT_KV_MOUNT = "zuno"
DEFAULT_KV_PATH = "okf-signatures"
# Baked into components/supply-chain-signer/Dockerfile at build time - a
# verifier reads this local file, never Vault, matching ADR-0420's core
# principle.
DEFAULT_LOCAL_PUBLIC_KEY_PATH = pathlib.Path("/app/zuno-platform-signer.pub")

# WP-111/ADR-0535: RHTAS keyless signing/verification defaults. All
# overridable via env (set by ansible/tasks/run_image_signing_job.yml and
# verify_image_signatures.yml's Job definitions, which resolve the live
# cluster domain the same way every other domain-bearing Application in
# this repo does) or CLI flags - never hardcoded to one cluster.
DEFAULT_FULCIO_URL = os.environ.get("RHTAS_FULCIO_URL", "http://fulcio-server.zuno-rhtas.svc.cluster.local")
DEFAULT_REKOR_URL = os.environ.get("RHTAS_REKOR_URL", "http://rekor-server.zuno-rhtas.svc.cluster.local")
DEFAULT_TUF_URL = os.environ.get("RHTAS_TUF_URL", "http://tuf.zuno-rhtas.svc.cluster.local")
# The zuno-signer client's hardcoded email protocol mappers (ADR-0535/
# WP-110) - Fulcio's "email" issuer type asserts this as the certificate
# identity.
DEFAULT_CERT_IDENTITY = os.environ.get("RHTAS_CERT_IDENTITY", "zuno-signer@zuno-demo.internal")
# No safe cluster-agnostic default: must match the Securesign CR's
# fulcio.config.OIDCIssuers[].Issuer exactly (ADR-0535's Design
# decisions), which is cluster-domain-specific.
DEFAULT_CERT_OIDC_ISSUER = os.environ.get("RHTAS_CERT_OIDC_ISSUER", "")
# The EXTERNAL Keycloak route, not the in-cluster Service - Keycloak's
# `iss` claim reflects the scheme of the request that reached it (no
# X-Forwarded-Proto through the internal ClusterIP), so a token fetched
# internally carries `iss: http://...` and Fulcio (configured with the
# https external issuer) rejects it (live finding, WP-111).
DEFAULT_KC_TOKEN_URL = os.environ.get("RHTAS_KEYCLOAK_TOKEN_URL", "")
DEFAULT_KC_CLIENT_ID = os.environ.get("RHTAS_CLIENT_ID", "zuno-signer")
DEFAULT_KC_CLIENT_SECRET_PATH = os.environ.get("RHTAS_CLIENT_SECRET_PATH", "")
# CA bundle for the external Keycloak route's Vault-PKI-issued cert
# (ADR-0347's finding, republished per-namespace by the rhtas/rhtas-config
# ansible roles as the rhtas-keycloak-ca ConfigMap).
DEFAULT_KC_CA_FILE = os.environ.get("RHTAS_KC_CA_FILE", "")


class SignerError(RuntimeError):
    pass


def _cosign_path() -> str:
    cosign_bin = shutil.which("cosign")
    if cosign_bin is None:
        raise SignerError("cosign binary not found on PATH")
    return cosign_bin


def vault_login(vault_addr: str, role: str, jwt_path: str) -> str:
    """Kubernetes-auth login against Vault; returns a client token.

    Uses stdlib urllib, not hvac/requests - this script runs inside the
    minimal signer image, which has no Python dependencies beyond the
    standard library.
    """
    jwt = pathlib.Path(jwt_path).read_text().strip()
    payload = json.dumps({"jwt": jwt, "role": role}).encode("utf-8")
    req = urllib.request.Request(
        f"{vault_addr}/v1/auth/kubernetes/login",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise SignerError(f"Vault Kubernetes-auth login failed ({exc.code}): {exc.read().decode()}") from exc
    except urllib.error.URLError as exc:
        raise SignerError(f"cannot reach Vault at {vault_addr}: {exc.reason}") from exc

    token = body.get("auth", {}).get("client_token")
    if not token:
        raise SignerError(f"Vault login response had no auth.client_token: {body}")
    return token


def _cosign_env(vault_addr: str, vault_token: str) -> dict:
    env = os.environ.copy()
    env["VAULT_ADDR"] = vault_addr
    env["VAULT_TOKEN"] = vault_token
    return env


def export_public_key(vault_addr: str, vault_token: str, key_name: str, output: pathlib.Path) -> None:
    cosign_bin = _cosign_path()
    result = subprocess.run(
        [cosign_bin, "public-key", "--key", f"hashivault://{key_name}"],
        env=_cosign_env(vault_addr, vault_token),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SignerError(f"cosign public-key failed: {(result.stderr or result.stdout).strip()}")
    output.write_text(result.stdout)
    print(f"public key -> {output}")


def _registry_docker_config(image_ref: str, jwt_path: str) -> pathlib.Path:
    """Cosign resolves registry credentials the standard Docker way (a
    config.json), not from the ambient Kubernetes ServiceAccount token -
    build one pointing at this pod's own token, the same "any username,
    token as password" Basic Auth convention `oc registry login` uses
    against OpenShift's internal registry. zuno-signer's own
    system:image-builder RoleBinding (ansible/roles/
    supply_chain_signer_build) is what actually authorizes this identity to
    push/pull, once it authenticates with this token."""
    registry = image_ref.split("/", 1)[0]
    token = pathlib.Path(jwt_path).read_text().strip()
    auth = base64.b64encode(f"serviceaccount:{token}".encode("utf-8")).decode("ascii")
    config_dir = pathlib.Path(tempfile.mkdtemp())
    (config_dir / "config.json").write_text(json.dumps({"auths": {registry: {"auth": auth}}}))
    return config_dir


def fetch_oidc_token(token_url: str, client_id: str, client_secret: str, ca_file: str = "") -> str:
    """WP-111/ADR-0535: exchanges the zuno-signer client-credentials grant
    for an access token whose `iss` Fulcio trusts. Must hit the EXTERNAL
    Keycloak route (see DEFAULT_KC_TOKEN_URL's comment) - ca_file is the
    Vault-PKI CA that route's cert chains to, not optional in practice."""
    data = urllib.parse.urlencode(
        {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
    ).encode("utf-8")
    req = urllib.request.Request(token_url, data=data, method="POST")
    context = ssl.create_default_context(cafile=ca_file) if ca_file else None
    try:
        with urllib.request.urlopen(req, timeout=15, context=context) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise SignerError(f"Keycloak token request failed ({exc.code}): {exc.read().decode()}") from exc
    except urllib.error.URLError as exc:
        raise SignerError(f"cannot reach Keycloak at {token_url}: {exc.reason}") from exc

    token = body.get("access_token")
    if not token:
        raise SignerError(f"Keycloak token response had no access_token: {body}")
    return token


def _cosign_initialize_tuf(tuf_url: str) -> None:
    """RHTAS's TUF trust root (Fulcio/Rekor/CTLog public keys) - every
    keyless sign/verify needs this cache initialized first. Re-run on
    every invocation: this script's callers are ephemeral pods with no
    persistent $HOME, so nothing survives between runs anyway."""
    cosign_bin = _cosign_path()
    env = os.environ.copy()
    env.setdefault("HOME", tempfile.gettempdir())
    result = subprocess.run(
        [cosign_bin, "initialize", "--mirror", tuf_url, "--root", f"{tuf_url}/root.json"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise SignerError(f"cosign initialize (TUF root, {tuf_url}) failed: {(result.stderr or result.stdout).strip()}")


def sign_image(
    image_ref: str,
    jwt_path: str,
    identity_token: str,
    fulcio_url: str = DEFAULT_FULCIO_URL,
    rekor_url: str = DEFAULT_REKOR_URL,
    tuf_url: str = DEFAULT_TUF_URL,
) -> None:
    """WP-111/ADR-0535: signs an OCI image by digest keyless via RHTAS
    (image_ref must already be `<repository>@sha256:<digest>` - the caller
    resolves the live ImageStreamTag digest, this function never does,
    matching run_okf_signing_job.yml's own "resolve outside, sign inside"
    split). Unlike sign-blob, plain `cosign sign` gates transparency-log
    upload behind an opt-in COSIGN_EXPERIMENTAL env var rather than a
    flag - not setting it (never set anywhere in this repo) is the whole
    story; RHTAS's own --rekor-url is what actually records the entry."""
    _cosign_initialize_tuf(tuf_url)
    cosign_bin = _cosign_path()
    docker_config_dir = _registry_docker_config(image_ref, jwt_path)
    token_file = pathlib.Path(tempfile.mkstemp(suffix=".tok")[1])
    token_file.write_text(identity_token)
    try:
        env = os.environ.copy()
        env["DOCKER_CONFIG"] = str(docker_config_dir)
        env.setdefault("HOME", tempfile.gettempdir())
        result = subprocess.run(
            [
                cosign_bin, "sign", "--yes",
                "--fulcio-url", fulcio_url,
                "--rekor-url", rekor_url,
                "--identity-token", str(token_file),
                image_ref,
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
    finally:
        shutil.rmtree(docker_config_dir, ignore_errors=True)
        token_file.unlink(missing_ok=True)
    if result.returncode != 0:
        raise SignerError(f"cosign sign (keyless, RHTAS) failed for {image_ref}: {(result.stderr or result.stdout).strip()}")
    print(f"signed {image_ref} (keyless, RHTAS)")


def verify_image(
    image_ref: str,
    jwt_path: str,
    cert_identity: str = DEFAULT_CERT_IDENTITY,
    cert_oidc_issuer: str = DEFAULT_CERT_OIDC_ISSUER,
    rekor_url: str = DEFAULT_REKOR_URL,
    tuf_url: str = DEFAULT_TUF_URL,
) -> None:
    """WP-111/ADR-0535: verifies an OCI image by digest keyless via
    RHTAS - checks the Fulcio-issued certificate's identity/issuer against
    a real Rekor transparency-log entry, replacing the pre-WP-111 static
    committed public key (`--key`). Still needs registry auth (a pull),
    built the same Docker-config-from-SA-token way sign_image() builds it
    for a push.

    `cosign verify` always initializes a local Sigstore TUF trust-root
    cache under $HOME/.sigstore - defaults HOME to a throwaway writable
    dir if unset, so this works regardless of the caller's environment (a
    Job with no HOME set, an interactive debug pod, ...) rather than
    requiring every caller to remember to set it."""
    _cosign_initialize_tuf(tuf_url)
    cosign_bin = _cosign_path()
    docker_config_dir = _registry_docker_config(image_ref, jwt_path)
    try:
        env = os.environ.copy()
        env["DOCKER_CONFIG"] = str(docker_config_dir)
        env.setdefault("HOME", tempfile.gettempdir())
        result = subprocess.run(
            [
                cosign_bin, "verify",
                "--rekor-url", rekor_url,
                "--certificate-identity", cert_identity,
                "--certificate-oidc-issuer", cert_oidc_issuer,
                image_ref,
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
    finally:
        shutil.rmtree(docker_config_dir, ignore_errors=True)
    if result.returncode != 0:
        raise SignerError(f"cosign verify (keyless, RHTAS) failed for {image_ref}: {(result.stderr or result.stdout).strip()}")
    print(f"verified {image_ref} (keyless, RHTAS)")


def verify_images_from_file(
    refs_path: pathlib.Path,
    jwt_path: str,
    cert_identity: str = DEFAULT_CERT_IDENTITY,
    cert_oidc_issuer: str = DEFAULT_CERT_OIDC_ISSUER,
    rekor_url: str = DEFAULT_REKOR_URL,
    tuf_url: str = DEFAULT_TUF_URL,
) -> None:
    """WP-111/ADR-0535: verifies every ref in a JSON file - the shape
    `verify_signatures.py --list-refs`'s "resolved" array produces,
    `[{"name", "repository", "digest"}, ...]` - keyless via RHTAS. Used by
    ansible/tasks/verify_image_signatures.yml's in-cluster Job
    (make d2 check supply-chain)."""
    if not cert_oidc_issuer:
        raise SignerError("--cert-oidc-issuer (or RHTAS_CERT_OIDC_ISSUER) is required and was not set")
    refs = json.loads(refs_path.read_text())
    failures = []
    for ref in refs:
        image_ref = f"{ref['repository']}@{ref['digest']}"
        try:
            verify_image(image_ref, jwt_path, cert_identity, cert_oidc_issuer, rekor_url, tuf_url)
        except SignerError as exc:
            print(f"FAIL {ref['name']}: {exc}")
            failures.append(ref["name"])

    if failures:
        raise SignerError(f"{len(failures)} of {len(refs)} image(s) failed verification: {', '.join(failures)}")

    print(f"RESULT: PASS - all {len(refs)} image(s) verified")


def sign_blob(vault_addr: str, vault_token: str, key_name: str, blob: pathlib.Path, signature: pathlib.Path) -> None:
    cosign_bin = _cosign_path()
    result = subprocess.run(
        [
            cosign_bin,
            "sign-blob",
            "--yes",
            "--tlog-upload=false",
            "--key",
            f"hashivault://{key_name}",
            "--output-signature",
            str(signature),
            str(blob),
        ],
        env=_cosign_env(vault_addr, vault_token),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SignerError(f"cosign sign-blob failed: {(result.stderr or result.stdout).strip()}")
    print(f"signed {blob} -> {signature}")


def verify_blob(public_key: pathlib.Path, blob: pathlib.Path, signature: pathlib.Path) -> None:
    cosign_bin = _cosign_path()
    result = subprocess.run(
        [
            cosign_bin,
            "verify-blob",
            "--insecure-ignore-tlog=true",
            "--key",
            str(public_key),
            "--signature",
            str(signature),
            str(blob),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SignerError(f"cosign verify-blob failed: {(result.stderr or result.stdout).strip()}")
    print(f"verified {blob}")


def kv_put(vault_addr: str, vault_token: str, mount: str, path: str, data: dict) -> None:
    """Writes a full KV v2 secret version (overwrites, not merges - matches
    Vault's own `kv put` semantics). Used instead of the idempotent
    seed-if-missing pattern `ansible/tasks/vault_seed_if_missing.yml` uses
    for operator-supplied credentials: a signature must update whenever
    bundle content changes, so this always writes the current value."""
    payload = json.dumps({"data": data}).encode("utf-8")
    req = urllib.request.Request(
        f"{vault_addr}/v1/{mount}/data/{path}",
        data=payload,
        headers={"Content-Type": "application/json", "X-Vault-Token": vault_token},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as exc:
        raise SignerError(f"Vault KV write to {mount}/data/{path} failed ({exc.code}): {exc.read().decode()}") from exc
    except urllib.error.URLError as exc:
        raise SignerError(f"cannot reach Vault at {vault_addr}: {exc.reason}") from exc


def sign_all_okf_bundles(
    vault_addr: str,
    role: str,
    key_name: str,
    jwt_path: str,
    agents_root: pathlib.Path,
    kv_mount: str,
    kv_path: str,
) -> None:
    """WP-069: signs every agents/<agent>/ bundle found under agents_root
    and writes the results to Vault KV in one call - {agent}.sig per agent
    plus the shared cosign.pub, all under one KV path so
    externalsecret-okf-signatures.yaml materializes them as a single
    Secret."""
    token = vault_login(vault_addr, role, jwt_path)
    print("Vault Kubernetes-auth login: OK")

    # sign_okf_bundle.sign_bundle() shells out to cosign, which reads
    # VAULT_ADDR/VAULT_TOKEN from the process environment for its
    # hashivault:// KMS calls - set once here rather than threading env
    # through every call.
    os.environ["VAULT_ADDR"] = vault_addr
    os.environ["VAULT_TOKEN"] = token

    bundle_dirs = sorted(p for p in agents_root.iterdir() if (p / "agent.okf.md").is_file())
    if not bundle_dirs:
        raise SignerError(f"no agent bundles found under {agents_root}")

    kv_data: dict = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)

        pubkey_path = tmp_dir / "cosign.pub"
        export_public_key(vault_addr, token, key_name, pubkey_path)
        kv_data["cosign.pub"] = pubkey_path.read_text()

        for bundle_dir in bundle_dirs:
            sign_okf_bundle.sign_bundle(bundle_dir, tmp_dir, kms_key=f"hashivault://{key_name}")
            sig_path = tmp_dir / f"{bundle_dir.name}.sig"
            kv_data[f"{bundle_dir.name}.sig"] = sig_path.read_text()

    kv_put(vault_addr, token, kv_mount, kv_path, kv_data)
    print(f"signed {len(bundle_dirs)} bundle(s), wrote {kv_mount}/data/{kv_path}: {', '.join(sorted(kv_data))}")


def dry_run(vault_addr: str, role: str, key_name: str, jwt_path: str) -> None:
    token = vault_login(vault_addr, role, jwt_path)
    print("Vault Kubernetes-auth login: OK")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        pubkey = tmp_dir / "cosign.pub"
        export_public_key(vault_addr, token, key_name, pubkey)

        blob = tmp_dir / "scratch.txt"
        blob.write_text("wp-068 dry-run scratch content\n")
        signature = tmp_dir / "scratch.sig"
        sign_blob(vault_addr, token, key_name, blob, signature)

        verify_blob(pubkey, blob, signature)

        # A modified blob must fail verification, or this exercise only
        # proves cosign runs, not that it checks anything.
        blob.write_text("tampered content\n")
        tampered_ok = False
        try:
            verify_blob(pubkey, blob, signature)
        except SignerError:
            tampered_ok = True
        if not tampered_ok:
            raise SignerError("tamper test failed: a modified blob verified successfully")
        print("tamper test: modified blob correctly rejected")

    print("RESULT: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--vault-addr", default=os.environ.get("VAULT_ADDR", DEFAULT_VAULT_ADDR))
    parser.add_argument("--role", default=os.environ.get("VAULT_K8S_ROLE", DEFAULT_ROLE))
    parser.add_argument("--key-name", default=os.environ.get("TRANSIT_KEY_NAME", DEFAULT_KEY_NAME))
    parser.add_argument("--jwt-path", default=DEFAULT_JWT_PATH)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="Vault Kubernetes-auth login only (proves the role binding)")

    p_pub = sub.add_parser("public-key", help="export the Transit key's public key")
    p_pub.add_argument("--output", required=True, type=pathlib.Path)

    p_sign = sub.add_parser("sign-blob", help="sign a blob with the Transit key")
    p_sign.add_argument("blob", type=pathlib.Path)
    p_sign.add_argument("--output-signature", required=True, type=pathlib.Path)

    p_sign_image = sub.add_parser("sign-image", help="sign an OCI image by digest keyless via RHTAS (ADR-0535/WP-111)")
    p_sign_image.add_argument("image_ref", help="<repository>@sha256:<digest>")
    p_sign_image.add_argument("--fulcio-url", default=DEFAULT_FULCIO_URL)
    p_sign_image.add_argument("--rekor-url", default=DEFAULT_REKOR_URL)
    p_sign_image.add_argument("--tuf-url", default=DEFAULT_TUF_URL)
    p_sign_image.add_argument("--kc-token-url", default=DEFAULT_KC_TOKEN_URL, help="external Keycloak token endpoint (RHTAS_KEYCLOAK_TOKEN_URL)")
    p_sign_image.add_argument("--kc-client-id", default=DEFAULT_KC_CLIENT_ID)
    p_sign_image.add_argument("--kc-client-secret-path", default=DEFAULT_KC_CLIENT_SECRET_PATH, help="file containing the zuno-signer client secret (RHTAS_CLIENT_SECRET_PATH)")
    p_sign_image.add_argument("--kc-ca-file", default=DEFAULT_KC_CA_FILE)

    p_verify = sub.add_parser("verify-blob", help="verify a blob's signature (no Vault access needed)")
    p_verify.add_argument("blob", type=pathlib.Path)
    p_verify.add_argument("--public-key", required=True, type=pathlib.Path)
    p_verify.add_argument("--signature", required=True, type=pathlib.Path)

    sub.add_parser("dry-run", help="WP-068 acceptance check: sign+verify a scratch blob end-to-end")

    p_okf = sub.add_parser("sign-okf-bundles", help="sign every agents/<agent>/ bundle and write results to Vault KV")
    p_okf.add_argument("--agents-root", required=True, type=pathlib.Path)
    p_okf.add_argument("--kv-mount", default=DEFAULT_KV_MOUNT)
    p_okf.add_argument("--kv-path", default=DEFAULT_KV_PATH)

    p_verify_images = sub.add_parser("verify-images", help="verify every image in a JSON refs file keyless via RHTAS (ADR-0535/WP-111)")
    p_verify_images.add_argument("--refs-file", required=True, type=pathlib.Path)
    p_verify_images.add_argument("--cert-identity", default=DEFAULT_CERT_IDENTITY)
    p_verify_images.add_argument("--cert-oidc-issuer", default=DEFAULT_CERT_OIDC_ISSUER)
    p_verify_images.add_argument("--rekor-url", default=DEFAULT_REKOR_URL)
    p_verify_images.add_argument("--tuf-url", default=DEFAULT_TUF_URL)

    args = parser.parse_args()

    try:
        if args.command == "login":
            vault_login(args.vault_addr, args.role, args.jwt_path)
            print("RESULT: PASS - Vault Kubernetes-auth login succeeded")
        elif args.command == "public-key":
            token = vault_login(args.vault_addr, args.role, args.jwt_path)
            export_public_key(args.vault_addr, token, args.key_name, args.output)
        elif args.command == "sign-blob":
            token = vault_login(args.vault_addr, args.role, args.jwt_path)
            sign_blob(args.vault_addr, token, args.key_name, args.blob, args.output_signature)
        elif args.command == "sign-image":
            if not args.kc_token_url:
                raise SignerError("--kc-token-url (or RHTAS_KEYCLOAK_TOKEN_URL) is required and was not set")
            if not args.kc_client_secret_path:
                raise SignerError("--kc-client-secret-path (or RHTAS_CLIENT_SECRET_PATH) is required and was not set")
            client_secret = pathlib.Path(args.kc_client_secret_path).read_text().strip()
            identity_token = fetch_oidc_token(args.kc_token_url, args.kc_client_id, client_secret, args.kc_ca_file)
            sign_image(args.image_ref, args.jwt_path, identity_token, args.fulcio_url, args.rekor_url, args.tuf_url)
        elif args.command == "verify-blob":
            verify_blob(args.public_key, args.blob, args.signature)
        elif args.command == "dry-run":
            dry_run(args.vault_addr, args.role, args.key_name, args.jwt_path)
        elif args.command == "sign-okf-bundles":
            sign_all_okf_bundles(
                args.vault_addr, args.role, args.key_name, args.jwt_path,
                args.agents_root, args.kv_mount, args.kv_path,
            )
        elif args.command == "verify-images":
            verify_images_from_file(
                args.refs_file, args.jwt_path,
                args.cert_identity, args.cert_oidc_issuer, args.rekor_url, args.tuf_url,
            )
    except (SignerError, sign_okf_bundle.BundleError) as exc:
        print(f"RESULT: FAIL - {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
