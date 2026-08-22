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
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

DEFAULT_VAULT_ADDR = "http://zuno-vault.zuno-vault.svc:8200"
DEFAULT_ROLE = "platform-signer"
DEFAULT_KEY_NAME = "zuno-platform-signer"
DEFAULT_JWT_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"


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

    p_verify = sub.add_parser("verify-blob", help="verify a blob's signature (no Vault access needed)")
    p_verify.add_argument("blob", type=pathlib.Path)
    p_verify.add_argument("--public-key", required=True, type=pathlib.Path)
    p_verify.add_argument("--signature", required=True, type=pathlib.Path)

    sub.add_parser("dry-run", help="WP-068 acceptance check: sign+verify a scratch blob end-to-end")

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
        elif args.command == "verify-blob":
            verify_blob(args.public_key, args.blob, args.signature)
        elif args.command == "dry-run":
            dry_run(args.vault_addr, args.role, args.key_name, args.jwt_path)
    except SignerError as exc:
        print(f"RESULT: FAIL - {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
