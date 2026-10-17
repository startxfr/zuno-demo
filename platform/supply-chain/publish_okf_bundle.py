#!/usr/bin/env python3
"""ADR-0564 OKF bundle publication: push a signed `agents/<agent>/` tree to an
OCI registry so unifai-operator's UnifaiAgentBundle can pull it by digest.

Runs AFTER `make d3 sign agents`, never instead of it: the signature it
publishes is the one the signing Job wrote to Vault KV, and the bundle is
re-verified against `agents/zuno-platform-signer.pub` before anything is
pushed - a bundle edited since it was signed is refused here, not discovered
later by the operator (the ADR-0544 rebuild-then-sign trap).

Artifact layout (mirrored by fork/unifai-operator/internal/okf/oci.go):
    artifact type   application/vnd.zuno.okf.bundle.v1
    one layer       application/vnd.zuno.okf.bundle.v1.tar+gzip - the bundle
                    tree, deterministic (sorted, mtime 0, uid/gid 0, mode 0644)
                    so the same content always yields the same layer digest
    annotations     zuno.okf.signature - the cosign sign-blob signature of
                    the bundle digest; zuno.okf.digest - that digest

Two operations:
    layer    - write the deterministic layer (inspection, tests)
    publish  - verify, then `oras push`; prints <repository>@<manifest digest>

Run from the repository root:
    python3 platform/supply-chain/publish_okf_bundle.py publish agents/tekos \\
        --signature /tmp/tekos.sig --repository quay.io/zuno/okf-tekos \\
        --public-key agents/zuno-platform-signer.pub
"""
from __future__ import annotations

import argparse
import contextlib
import gzip
import io
import json
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import sign_okf_bundle  # noqa: E402

ARTIFACT_TYPE = "application/vnd.zuno.okf.bundle.v1"
LAYER_MEDIA_TYPE = "application/vnd.zuno.okf.bundle.v1.tar+gzip"
SIGNATURE_ANNOTATION = "zuno.okf.signature"
DIGEST_ANNOTATION = "zuno.okf.digest"
LAYER_FILENAME = "okf-bundle.tar.gz"


class PublishError(RuntimeError):
    pass


def build_layer(bundle_dir: pathlib.Path) -> bytes:
    """Deterministic gzipped tar of exactly the files the digest covers."""
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for path in sign_okf_bundle._bundle_files(bundle_dir):
                data = path.read_bytes()
                info = tarfile.TarInfo(path.relative_to(bundle_dir).as_posix())
                info.size, info.mode, info.mtime = len(data), 0o644, 0
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def oras_push_args(repository: str, digest: str, signature: str) -> list:
    """`oras push` arguments; the tag names the bundle digest so a re-run is idempotent."""
    return [
        "push",
        f"{repository}:okf-{digest[:16]}",
        "--artifact-type", ARTIFACT_TYPE,
        "--annotation", f"{SIGNATURE_ANNOTATION}={signature}",
        "--annotation", f"{DIGEST_ANNOTATION}={digest}",
        "--format", "json",
        f"{LAYER_FILENAME}:{LAYER_MEDIA_TYPE}",
    ]


def publish(bundle_dir: pathlib.Path, signature_path: pathlib.Path, repository: str,
            public_key: pathlib.Path, oras_bin: str = "oras") -> str:
    signature = signature_path.read_text().strip()
    if not signature:
        raise PublishError(f"{signature_path} is empty")
    try:
        # verify_bundle reports on stdout; keep stdout for the published reference only.
        with contextlib.redirect_stdout(sys.stderr):
            sign_okf_bundle.verify_bundle(bundle_dir, signature_path, public_key)
    except sign_okf_bundle.BundleError as exc:
        raise PublishError(f"refusing to publish {bundle_dir}: {exc}") from exc
    digest = sign_okf_bundle.compute_digest(bundle_dir)
    oras = shutil.which(oras_bin)
    if oras is None:
        raise PublishError(f"{oras_bin} not found on PATH")
    with tempfile.TemporaryDirectory() as tmp:
        (pathlib.Path(tmp) / LAYER_FILENAME).write_bytes(build_layer(bundle_dir))
        result = subprocess.run([oras, *oras_push_args(repository, digest, signature)],
                                cwd=tmp, capture_output=True, text=True)
    if result.returncode != 0:
        raise PublishError(f"oras push failed for {bundle_dir}: {(result.stderr or result.stdout).strip()}")
    try:
        manifest_digest = json.loads(result.stdout)["digest"]
    except (ValueError, KeyError) as exc:
        raise PublishError(f"unexpected oras output: {result.stdout.strip()[:300]}") from exc
    return f"{repository}@{manifest_digest}"


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    lay = sub.add_parser("layer", help="write the deterministic bundle layer")
    lay.add_argument("bundle_dir", type=pathlib.Path)
    lay.add_argument("--output", type=pathlib.Path, required=True)
    pub = sub.add_parser("publish", help="verify then push the bundle")
    pub.add_argument("bundle_dir", type=pathlib.Path)
    pub.add_argument("--signature", type=pathlib.Path, required=True)
    pub.add_argument("--repository", required=True, help="e.g. quay.io/zuno/okf-tekos")
    pub.add_argument("--public-key", type=pathlib.Path, default=pathlib.Path("agents/zuno-platform-signer.pub"))
    args = parser.parse_args(argv)
    try:
        if args.command == "layer":
            args.output.write_bytes(build_layer(args.bundle_dir))
            print(args.output)
        else:
            print(publish(args.bundle_dir, args.signature, args.repository, args.public_key))
    except (PublishError, sign_okf_bundle.BundleError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
