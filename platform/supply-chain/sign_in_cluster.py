#!/usr/bin/env python3
"""ADR-0420 in-cluster supply-chain signing: authenticates to Vault's
Transit-backed platform-signer identity via Kubernetes auth, then drives
cosign's native hashivault:// KMS mode - replacing the GitHub-OIDC/Fulcio/
Rekor keyless model platform/supply-chain/sign_okf_bundle.py and
verify_signatures.py still use today (WP-069/070 migrate them onto this).

Four operations:

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
    verify-images - WP-070: verifies every image in a JSON refs file (the
                  shape `verify_signatures.py --list-refs`'s "resolved"
                  array produces) against the public key baked into this
                  image at build time - no Vault access at all, the whole
                  point of a verifier. Still needs registry auth (a pull),
                  built the same way sign-image's push does. Used by
                  ansible/tasks/verify_image_signatures.yml's in-cluster
                  Job (make d2 check supply-chain).

--tlog-upload=false / --insecure-ignore-tlog=true are load-bearing, not a
security loosening: there is no self-hosted Rekor here (Vault's own audit
device is the in-cluster substitute, see ADR-0420's Decision), and omitting
either flag makes cosign silently reach out to the public
rekor.sigstore.dev - exactly the external dependency this script exists to
remove.

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
import subprocess
import sys
import tempfile
import urllib.error
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


def sign_image(vault_addr: str, vault_token: str, key_name: str, image_ref: str, jwt_path: str) -> None:
    """ADR-0420/WP-070: signs an OCI image by digest (image_ref must already
    be `<repository>@sha256:<digest>` - the caller resolves the live
    ImageStreamTag digest, this function never does, matching
    run_okf_signing_job.yml's own "resolve outside, sign inside" split).
    Unlike sign-blob, plain `cosign sign` gates transparency-log upload
    behind an opt-in COSIGN_EXPERIMENTAL env var rather than a flag - not
    setting it (never set anywhere in this repo) is the whole story, no
    extra flag needed here."""
    cosign_bin = _cosign_path()
    docker_config_dir = _registry_docker_config(image_ref, jwt_path)
    try:
        env = _cosign_env(vault_addr, vault_token)
        env["DOCKER_CONFIG"] = str(docker_config_dir)
        result = subprocess.run(
            [cosign_bin, "sign", "--yes", "--key", f"hashivault://{key_name}", image_ref],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
    finally:
        shutil.rmtree(docker_config_dir, ignore_errors=True)
    if result.returncode != 0:
        raise SignerError(f"cosign sign failed for {image_ref}: {(result.stderr or result.stdout).strip()}")
    print(f"signed {image_ref}")


def verify_image(public_key: pathlib.Path, image_ref: str, jwt_path: str) -> None:
    """ADR-0420/WP-070: verifies an OCI image by digest against a LOCAL
    public key file - no Vault access needed, matching
    sign_okf_bundle.py's verify_bundle(). Still needs registry auth (a
    pull), built the same Docker-config-from-SA-token way sign_image()
    builds it for a push."""
    cosign_bin = _cosign_path()
    docker_config_dir = _registry_docker_config(image_ref, jwt_path)
    try:
        env = os.environ.copy()
        env["DOCKER_CONFIG"] = str(docker_config_dir)
        result = subprocess.run(
            [cosign_bin, "verify", "--key", str(public_key), image_ref],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
    finally:
        shutil.rmtree(docker_config_dir, ignore_errors=True)
    if result.returncode != 0:
        raise SignerError(f"cosign verify failed for {image_ref}: {(result.stderr or result.stdout).strip()}")
    print(f"verified {image_ref}")


def verify_images_from_file(refs_path: pathlib.Path, public_key: pathlib.Path, jwt_path: str) -> None:
    """ADR-0420/WP-070: verifies every ref in a JSON file - the shape
    `verify_signatures.py --list-refs`'s "resolved" array produces,
    `[{"name", "repository", "digest"}, ...]` - against a local public
    key. Used by ansible/tasks/verify_image_signatures.yml's in-cluster
    Job (make d2 check supply-chain)."""
    refs = json.loads(refs_path.read_text())
    failures = []
    for ref in refs:
        image_ref = f"{ref['repository']}@{ref['digest']}"
        try:
            verify_image(public_key, image_ref, jwt_path)
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

    p_sign_image = sub.add_parser("sign-image", help="sign an OCI image by digest with the Transit key")
    p_sign_image.add_argument("image_ref", help="<repository>@sha256:<digest>")

    p_verify = sub.add_parser("verify-blob", help="verify a blob's signature (no Vault access needed)")
    p_verify.add_argument("blob", type=pathlib.Path)
    p_verify.add_argument("--public-key", required=True, type=pathlib.Path)
    p_verify.add_argument("--signature", required=True, type=pathlib.Path)

    sub.add_parser("dry-run", help="WP-068 acceptance check: sign+verify a scratch blob end-to-end")

    p_okf = sub.add_parser("sign-okf-bundles", help="sign every agents/<agent>/ bundle and write results to Vault KV")
    p_okf.add_argument("--agents-root", required=True, type=pathlib.Path)
    p_okf.add_argument("--kv-mount", default=DEFAULT_KV_MOUNT)
    p_okf.add_argument("--kv-path", default=DEFAULT_KV_PATH)

    p_verify_images = sub.add_parser("verify-images", help="verify every image in a JSON refs file (no Vault access needed)")
    p_verify_images.add_argument("--refs-file", required=True, type=pathlib.Path)
    p_verify_images.add_argument("--public-key", default=DEFAULT_LOCAL_PUBLIC_KEY_PATH, type=pathlib.Path)

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
            token = vault_login(args.vault_addr, args.role, args.jwt_path)
            sign_image(args.vault_addr, token, args.key_name, args.image_ref, args.jwt_path)
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
            verify_images_from_file(args.refs_file, args.public_key, args.jwt_path)
    except (SignerError, sign_okf_bundle.BundleError) as exc:
        print(f"RESULT: FAIL - {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
