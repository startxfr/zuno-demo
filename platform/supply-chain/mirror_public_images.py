#!/usr/bin/env python3
"""Copy the closed list of public third-party images into the internal Red Hat Quay (ADR-0612 clause 7d, WP-248 family d).

`platform/supply-chain/mirrored-images.yaml` names every image: nothing else is copied. Only entries pinned by digest are
copied (`pin: digest`); an entry pinned by tag waits until its chart pins a digest, because an ImageDigestMirrorSet
redirects digest pulls only. The copy keeps the digest (oras copies the manifest list and its children byte for byte)
and the script refuses a copy whose digest differs. These publishers sign nothing we verify: the digest pin is the trust.

    python3 platform/supply-chain/mirror_public_images.py --to quay-quay-zuno-registry.apps.demo333.startx.fr [--dry-run] [--only SUBSTRING]

Credentials: the push robot's docker config (DOCKER_CONFIG). With QUAY_API_TOKEN set the repositories are made publicly
readable afterwards (the images are public at their source; the nodes then need no credential).
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys
from typing import Callable, Dict, List, Optional

import yaml

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import admit_okf_bundle as admit  # noqa: E402
import mirror_unifai_images as unifai_mirror  # noqa: E402

LIST_PATH = HERE / "mirrored-images.yaml"
ORG = "zuno"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ListError(ValueError):
    pass


def load_list(path: pathlib.Path = LIST_PATH) -> List[dict]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    images = doc.get("images") or []
    seen = set()
    for item in images:
        for key in ("source", "pin", "signature", "reason"):
            if not item.get(key):
                raise ListError(f"{path}: an entry has no '{key}': {item}")
        if item["pin"] not in ("digest", "tag"):
            raise ListError(f"{item['source']}: pin must be digest or tag")
        if item["pin"] == "digest" and not DIGEST_RE.match(str(item.get("digest", ""))):
            raise ListError(f"{item['source']}: pin digest needs a sha256 digest")
        key = (item["source"], item.get("digest") or item.get("tag"))
        if key in seen:
            raise ListError(f"{item['source']}: listed twice")
        seen.add(key)
    return images


def repository_path(source: str) -> str:
    """`docker.io/hashicorp/vault` -> `mirror/hashicorp/vault` (the registry host is dropped)."""
    return "mirror/" + source.split("/", 1)[1]


def mirror_target(source: str, host: str) -> str:
    return f"{host}/{ORG}/{repository_path(source)}"


def copy_one(item: dict, host: str, run: Callable[..., str] = admit.run) -> str:
    digest = item["digest"]
    target = mirror_target(item["source"], host)
    tag = f"d-{digest.split(':')[1][:12]}"
    run([admit.require("oras"), "cp", "-r", f"{item['source']}@{digest}", f"{target}:{tag}"])
    got = run([admit.require("oras"), "resolve", f"{target}:{tag}"]).strip()
    if got != digest:
        raise ListError(f"{item['source']}: the mirror holds {got}, expected {digest}")
    return f"{target}@{digest}"


def mirror_all(images: List[dict], host: str, dry_run: bool = False, only: str = "",
               copy: Callable[[dict, str], str] = copy_one) -> Dict[str, List[str]]:
    done: List[str] = []
    waiting: List[str] = []
    for item in images:
        if only and only not in item["source"]:
            continue
        if item["pin"] != "digest":
            waiting.append(f"{item['source']}:{item.get('tag')}")
            continue
        done.append(f"{mirror_target(item['source'], host)}@{item['digest']}" if dry_run else copy(item, host))
    return {"copied": done, "waiting_for_a_digest_pin": waiting}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--to", required=True, help="registry route host, without organisation")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", default="", help="copy only the sources containing this text")
    args = parser.parse_args(argv)
    try:
        images = load_list()
        result = mirror_all(images, args.to, args.dry_run, args.only)
    except (ListError, admit.AdmissionError) as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 1
    for ref in result["copied"]:
        print(("WOULD COPY " if args.dry_run else "MIRRORED ") + ref)
    for ref in result["waiting_for_a_digest_pin"]:
        print("WAITING (pinned by tag, not copied) " + ref)
    token = os.environ.get("QUAY_API_TOKEN", "")
    if not args.dry_run and result["copied"]:
        if token:
            names = sorted({repository_path(i["source"]) for i in images if i["pin"] == "digest" and (not args.only or args.only in i["source"])})
            unifai_mirror.make_public(f"{args.to}/{ORG}", names, token)
            print("repositories are publicly readable")
        else:
            print("QUAY_API_TOKEN not set: the repositories stay private until they are made public")
    return 0


if __name__ == "__main__":
    sys.exit(main())
