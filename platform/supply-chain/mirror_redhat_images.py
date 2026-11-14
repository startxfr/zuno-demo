#!/usr/bin/env python3
"""Copy the large Red Hat product images into PRIVATE repositories of the internal Quay (ADR-0612 addendum 2026-11-14, WP-261 family e).

`platform/supply-chain/mirrored-redhat-images.yaml` names every image, pinned by the digest the operators run: nothing else
is copied. oras copies by digest (the manifest list and its children byte for byte) and the script refuses a copy whose
digest differs. Red Hat signs these images on its own lookaside server, not in the registry, so there is nothing to copy
beside the image; the cluster pins them by digest.

    python3 platform/supply-chain/mirror_redhat_images.py --to quay-quay-zuno-registry.apps.demo333.startx.fr [--dry-run] [--only SUBSTRING]
    python3 platform/supply-chain/mirror_redhat_images.py --drift

`--drift` reads the running pods (`oc`) and lists the digests of listed repositories that the list does not name, which
is what an operator upgrade leaves behind: add them to the list, then copy.

Credentials: the destination is the push robot's docker config (DOCKER_CONFIG, ~/.config/zuno/quay-push). The source is
the registry.redhat.io entry of the cluster's global pull secret, read with `oc` into a 0600 file in a private temporary
directory that is deleted afterwards (or --source-auth FILE). With QUAY_API_TOKEN set, every repository is checked and made
private if it is not: the route is reachable from the Internet and Red Hat content is never publicly readable.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from typing import Callable, Dict, Iterator, List, Optional

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import admit_okf_bundle as admit  # noqa: E402
import mirror_public_images as public  # noqa: E402

LIST_PATH = HERE / "mirrored-redhat-images.yaml"
ORG = "zuno"
PREFIX = "redhat"
SOURCE_REGISTRY = "registry.redhat.io"
ListError = public.ListError


def load_list(path: pathlib.Path = LIST_PATH) -> List[dict]:
    images = public.load_list(path)
    for item in images:
        if not item["source"].startswith(SOURCE_REGISTRY + "/"):
            raise ListError(f"{item['source']}: family (e) holds {SOURCE_REGISTRY} images only")
        if item["pin"] != "digest":
            raise ListError(f"{item['source']}: family (e) entries are pinned by digest")
    return images


def repository_path(source: str) -> str:
    """`registry.redhat.io/rhoai/odh-mlflow-rhel9` -> `redhat/rhoai/odh-mlflow-rhel9`."""
    return PREFIX + "/" + source.split("/", 1)[1]


def mirror_target(source: str, host: str) -> str:
    return f"{host}/{ORG}/{repository_path(source)}"


@contextlib.contextmanager
def source_auth_from_cluster(run: Callable[..., str] = admit.run) -> Iterator[str]:
    """The registry.redhat.io entry of openshift-config/pull-secret, alone, in a 0600 file removed on exit."""
    raw = run([admit.require("oc"), "get", "secret", "pull-secret", "-n", "openshift-config",
               "-o", "jsonpath={.data.\\.dockerconfigjson}"])
    auths = json.loads(base64.b64decode(raw)).get("auths", {})
    if SOURCE_REGISTRY not in auths:
        raise ListError(f"the cluster pull secret has no {SOURCE_REGISTRY} entry")
    with tempfile.TemporaryDirectory(prefix="rh-auth-") as tmp:  # created 0700
        path = pathlib.Path(tmp) / "config.json"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump({"auths": {SOURCE_REGISTRY: auths[SOURCE_REGISTRY]}}, fh)
        yield str(path)


def copy_one(item: dict, host: str, source_auth: str, run: Callable[..., str] = admit.run) -> str:
    digest = item["digest"]
    target = mirror_target(item["source"], host)
    tag = f"d-{digest.split(':')[1][:12]}"
    # Large layers (up to 2.7 GB) go up in one PUT each. From a workstation link, a PUT that lasts more
    # than about ten minutes was cut ("unexpected EOF") and oras then cancelled the parallel ones, which
    # Quay logs as PUT 400 / BlobDigestMismatchException (demo333, 2026-11-14, three attempts lost).
    # One blob at a time keeps each PUT short at the full link rate; a retry skips the blobs already there.
    attempts = 5
    for attempt in range(1, attempts + 1):
        try:
            run([admit.require("oras"), "cp", "--concurrency", "1", "--from-registry-config", source_auth,
                 f"{item['source']}@{digest}", f"{target}:{tag}"])
            break
        except admit.AdmissionError as exc:
            if attempt == attempts:
                raise
            print(f"RETRY {attempt}/{attempts - 1} {item['source']}: {exc}", file=sys.stderr, flush=True)
            time.sleep(15)
    got = run([admit.require("oras"), "resolve", f"{target}:{tag}"]).strip()
    if got != digest:
        raise ListError(f"{item['source']}: the mirror holds {got}, expected {digest}")
    return f"{target}@{digest}"


def mirror_all(images: List[dict], host: str, dry_run: bool = False, only: str = "",
               copy: Optional[Callable[[dict, str], str]] = None) -> List[str]:
    done: List[str] = []
    for item in images:
        if only and only not in item["source"]:
            continue
        if dry_run:
            done.append(f"{mirror_target(item['source'], host)}@{item['digest']}")
            continue
        ref = copy(item, host)
        print("MIRRORED " + ref, flush=True)
        done.append(ref)
    return done


def ensure_private(host: str, names: List[str], token: str,
                   request: Optional[Callable[[str, str, Optional[dict]], dict]] = None) -> List[str]:
    """Make every named repository private; return the ones that were public. Never makes anything public."""

    def default_request(method: str, url: str, body: Optional[dict]) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:  # trust: system store (Let's Encrypt route certificate)
            text = resp.read().decode() or "{}"
        return json.loads(text)

    send = request or default_request
    fixed = []
    for name in names:
        repo = send("GET", f"https://{host}/api/v1/repository/{ORG}/{name}", None)
        if repo.get("is_public", False):
            send("POST", f"https://{host}/api/v1/repository/{ORG}/{name}/changevisibility", {"visibility": "private"})
            fixed.append(name)
    return fixed


DIGEST_REF = re.compile(r"^(?P<repo>[^@]+)@(?P<digest>sha256:[0-9a-f]{64})$")


def drift(pods: dict, images: List[dict]) -> List[str]:
    """Running `<listed repository>@<digest>` references whose digest the list does not name."""
    listed: Dict[str, set] = {}
    for item in images:
        listed.setdefault(item["source"], set()).add(item["digest"])
    missing: Dict[str, set] = {}
    for pod in pods.get("items", []):
        spec = pod.get("spec", {})
        where = f"{pod['metadata']['namespace']}/{pod['metadata']['name']}"
        for container in spec.get("containers", []) + spec.get("initContainers", []):
            match = DIGEST_REF.match(container.get("image", ""))
            if match and match["repo"] in listed and match["digest"] not in listed[match["repo"]]:
                missing.setdefault(container["image"], set()).add(where)
    return [f"{ref} (used by {', '.join(sorted(users)[:3])})" for ref, users in sorted(missing.items())]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--to", help="registry route host, without organisation")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", default="", help="copy only the sources containing this text")
    parser.add_argument("--source-auth", default="", help="docker config holding the registry.redhat.io credential")
    parser.add_argument("--drift", action="store_true", help="list running digests of listed repositories that are not listed")
    args = parser.parse_args(argv)
    try:
        images = load_list()
        if args.drift:
            pods = json.loads(admit.run([admit.require("oc"), "get", "pods", "-A", "-o", "json"]))
            missing = drift(pods, images)
            for line in missing:
                print("NOT LISTED " + line)
            print("drift: none" if not missing else f"drift: {len(missing)} running digest(s) to add and copy")
            return 1 if missing else 0
        if not args.to:
            parser.error("--to is required unless --drift")
        if args.dry_run:
            for ref in mirror_all(images, args.to, dry_run=True, only=args.only):
                print("WOULD COPY " + ref)
            return 0
        with contextlib.ExitStack() as stack:
            auth = args.source_auth or stack.enter_context(source_auth_from_cluster())
            done = mirror_all(images, args.to, only=args.only, copy=lambda i, h: copy_one(i, h, auth))
    except (ListError, admit.AdmissionError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 1
    token = os.environ.get("QUAY_API_TOKEN", "")
    if done and token:
        names = sorted({repository_path(i["source"]) for i in images if not args.only or args.only in i["source"]})
        try:
            fixed = ensure_private(args.to, names, token)
        except urllib.error.URLError as exc:
            print(f"REFUSED could not check the repository visibility: {exc}", file=sys.stderr)
            return 1
        print("made private: " + ", ".join(fixed) if fixed else "every repository is private")
    elif done:
        print("QUAY_API_TOKEN not set: repository visibility NOT checked (Quay creates pushed repositories private by default)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
