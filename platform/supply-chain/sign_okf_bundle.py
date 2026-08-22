#!/usr/bin/env python3
"""ADR-0106/ADR-0420 OKF bundle signing: computes a deterministic digest
over an `agents/<agent>/` tree and signs/verifies it with Cosign, backed by
the in-cluster Vault Transit key `platform/supply-chain/sign_in_cluster.py`
authenticates to - here applied to a directory of Markdown/YAML files
instead of an OCI image, since an OKF bundle isn't a container.

Three independent operations:

    digest    - print the canonical sha256 digest of a bundle (no cosign
                needed; always available, used by validate_okf_bundle.py
                and the runtime too).
    sign      - `cosign sign-blob --key hashivault://<name>` over that
                digest, producing a detached signature (no certificate -
                Transit signs with a fixed key, not an ephemeral Fulcio
                cert). Needs VAULT_ADDR/VAULT_TOKEN in the environment
                (sign_in_cluster.py's vault_login() supplies these) and can
                only succeed against a reachable in-cluster Vault, not in a
                local sandbox.
    verify    - `cosign verify-blob --key <public-key-file>`. Needs only
                the bundle, its signature and the committed public key
                (`platform/supply-chain/keys/zuno-platform-signer.pub`) -
                NO Vault access and NO network, so this mode works
                anywhere, including a fully offline check.

Digest determinism: sorted (relative_path, sha256(content)) pairs over
every file in the bundle tree, joined and hashed - independent of
filesystem iteration order or OS, and changes if and only if bundle
*content* changes (never signing metadata, matching ADR-0106's "signing
wraps the bundle; it does not modify it").

Run from the repository root:

    python3 platform/supply-chain/sign_okf_bundle.py digest agents/tekos
    python3 platform/supply-chain/sign_okf_bundle.py sign agents/tekos --output-dir /tmp/sigs
    python3 platform/supply-chain/sign_okf_bundle.py verify agents/tekos \\
        --signature /tmp/sigs/tekos.sig \\
        --public-key platform/supply-chain/keys/zuno-platform-signer.pub
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import subprocess
import sys
from typing import List

DEFAULT_KMS_KEY = "hashivault://zuno-platform-signer"

# Files that must never affect the digest even if present (none expected
# under agents/, but defensive: __pycache__/.DS_Store-style noise must
# never make a bundle's signature depend on which OS/tool touched it last).
_IGNORED_NAMES = {"__pycache__", ".DS_Store"}


class BundleError(RuntimeError):
    pass


def _bundle_files(bundle_dir: pathlib.Path) -> List[pathlib.Path]:
    if not bundle_dir.is_dir():
        raise BundleError(f"{bundle_dir} is not a directory")
    files = [
        p
        for p in sorted(bundle_dir.rglob("*"))
        if p.is_file() and not any(part in _IGNORED_NAMES for part in p.parts)
    ]
    if not files:
        raise BundleError(f"{bundle_dir} contains no files to digest")
    return files


def compute_digest(bundle_dir: pathlib.Path) -> str:
    files = _bundle_files(bundle_dir)
    lines = []
    for path in files:
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        rel = path.relative_to(bundle_dir).as_posix()
        lines.append(f"{rel}:{file_hash}")
    manifest = "\n".join(lines) + "\n"
    return hashlib.sha256(manifest.encode("utf-8")).hexdigest()


def _cosign_path() -> str:
    cosign_bin = shutil.which("cosign")
    if cosign_bin is None:
        raise BundleError("cosign binary not found on PATH")
    return cosign_bin


def sign_bundle(bundle_dir: pathlib.Path, output_dir: pathlib.Path, kms_key: str = DEFAULT_KMS_KEY) -> None:
    digest = compute_digest(bundle_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    digest_file = output_dir / f"{bundle_dir.name}.digest"
    digest_file.write_text(digest + "\n")

    sig_path = output_dir / f"{bundle_dir.name}.sig"
    cosign_bin = _cosign_path()
    result = subprocess.run(
        [
            cosign_bin,
            "sign-blob",
            "--yes",
            "--tlog-upload=false",
            "--key",
            kms_key,
            "--output-signature",
            str(sig_path),
            str(digest_file),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise BundleError(
            f"cosign sign-blob failed for {bundle_dir}: {(result.stderr or result.stdout).strip()}"
        )
    print(f"signed {bundle_dir} -> {sig_path} (digest {digest})")


def verify_bundle(bundle_dir: pathlib.Path, signature: pathlib.Path, public_key: pathlib.Path) -> None:
    digest = compute_digest(bundle_dir)
    cosign_bin = _cosign_path()
    # cosign verify-blob hashes the exact bytes of the file it's given, so
    # the verified artifact is the digest string itself, recomputed fresh
    # here - never trust a stale on-disk .digest file for verification.
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".digest", delete=False) as fh:
        fh.write(digest + "\n")
        digest_file = pathlib.Path(fh.name)
    try:
        result = subprocess.run(
            [
                cosign_bin,
                "verify-blob",
                "--insecure-ignore-tlog=true",
                "--key",
                str(public_key),
                "--signature",
                str(signature),
                str(digest_file),
            ],
            capture_output=True,
            text=True,
        )
    finally:
        digest_file.unlink(missing_ok=True)

    if result.returncode != 0:
        raise BundleError(
            f"signature verification failed for {bundle_dir}: {(result.stderr or result.stdout).strip()}"
        )
    print(f"verified {bundle_dir} (digest {digest})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_digest = sub.add_parser("digest", help="print the canonical bundle digest")
    p_digest.add_argument("bundle_dir", type=pathlib.Path)

    p_sign = sub.add_parser("sign", help="sign a bundle via the in-cluster Vault Transit key (needs VAULT_ADDR/VAULT_TOKEN)")
    p_sign.add_argument("bundle_dir", type=pathlib.Path)
    p_sign.add_argument("--output-dir", required=True, type=pathlib.Path)
    p_sign.add_argument("--kms-key", default=DEFAULT_KMS_KEY)

    p_verify = sub.add_parser("verify", help="verify a bundle's signature (no Vault access needed)")
    p_verify.add_argument("bundle_dir", type=pathlib.Path)
    p_verify.add_argument("--signature", required=True, type=pathlib.Path)
    p_verify.add_argument("--public-key", required=True, type=pathlib.Path)

    args = parser.parse_args()

    try:
        if args.command == "digest":
            print(compute_digest(args.bundle_dir))
        elif args.command == "sign":
            sign_bundle(args.bundle_dir, args.output_dir, args.kms_key)
        elif args.command == "verify":
            verify_bundle(args.bundle_dir, args.signature, args.public_key)
    except BundleError as exc:
        print(f"RESULT: FAIL - {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
