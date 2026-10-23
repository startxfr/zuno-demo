#!/usr/bin/env python3
"""Install the two binaries admission needs, cosign and oras, into a directory (WP-165).

Used by the image builds that bake content of the admitted agents release
(components/ai-gateway/Dockerfile, components/mlops/Containerfile): their
builder stage runs this, then platform/okf/release_cache.py, so the release
is verified offline before a single file of it is copied into the image.
Python only (urllib, hashlib), so it works on every base image the builds
use, Debian slim and UBI alike, without a package manager or curl.

The pins are those of components/supply-chain-signer/Dockerfile and
components/aap-execution-environment (cosign v2.4.1, oras 1.2.2), digests
from each project's published checksums file; re-verify on any bump.

    python3 platform/okf/install_release_tools.py DIR
"""
from __future__ import annotations

import hashlib
import io
import pathlib
import sys
import tarfile
import urllib.request

COSIGN_VERSION = "v2.4.1"
COSIGN_SHA256 = "8b24b946dd5809c6bd93de08033bcf6bc0ed7d336b7785787c080f574b89249b"
ORAS_VERSION = "1.2.2"
ORAS_SHA256 = "bff970346470e5ef888e9f2c0bf7f8ee47283f5a45207d6e7a037da1fb0eae0d"


def _download(url: str, sha256: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 - pinned https URL
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != sha256:
        raise SystemExit(f"{url}: sha256 {digest}, expected {sha256}")
    return data


def main(argv: list) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    out = pathlib.Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)

    cosign = out / "cosign"
    cosign.write_bytes(_download(
        f"https://github.com/sigstore/cosign/releases/download/{COSIGN_VERSION}/cosign-linux-amd64",
        COSIGN_SHA256))
    cosign.chmod(0o755)

    archive = _download(
        f"https://github.com/oras-project/oras/releases/download/v{ORAS_VERSION}/"
        f"oras_{ORAS_VERSION}_linux_amd64.tar.gz", ORAS_SHA256)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        oras = out / "oras"
        oras.write_bytes(tar.extractfile(tar.getmember("oras")).read())
    oras.chmod(0o755)
    print(f"installed cosign {COSIGN_VERSION} and oras {ORAS_VERSION} into {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
