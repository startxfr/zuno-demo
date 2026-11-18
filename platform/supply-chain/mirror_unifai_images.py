#!/usr/bin/env python3
"""Copy the pinned UnifAI images into the internal Red Hat Quay (ADR-0612 clause 7c, WP-248 family c).

What the cluster runs is a set of digests: the five application images in `ansible/clusters/<cluster>.yml`
(`stack.images`), the operator catalog in `gitops/charts/unifai/values.yaml`, and the operator and its bundle of the
catalog's version. Each one is verified at its source with the policy of ADR-0586 (signature, provenance, signed SBOM),
copied by digest with its `.sig`, `.att` and `.sbom` tags and the signature of the SBOM artifact, then verified again
from the copy. Digests never change, so the pins, the admission policy and the signatures stay as they are; only the
registry that serves them differs. Nothing is copied that the pins do not name.

    python3 platform/supply-chain/mirror_unifai_images.py --to quay-quay-zuno-registry.apps.demo333.startx.fr/zuno \\
        --version 0.1.68 [--cluster demo333] [--dry-run]

Credentials: the push robot's docker config (DOCKER_CONFIG). With QUAY_API_TOKEN set, the repositories are made
publicly readable afterwards (the images are public on quay.io already); without it the script says so and stops there.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
import urllib.request
from typing import Callable, Dict, List, Optional

import yaml

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import admit_okf_bundle as admit  # noqa: E402
import verify_unifai_images as v  # noqa: E402
from check_unifai_pins import APPLICATION_IMAGES  # noqa: E402

REPO_ROOT = HERE.parents[1]
FAMILY = "quay.io/zuno/"
CATALOG_RE = re.compile(r"^\s*catalogImage:\s*(quay\.io/zuno/unifai-operator-catalog@sha256:[0-9a-f]{64})\s*$", re.M)


class MirrorError(ValueError):
    pass


def pinned_references(cluster_file: pathlib.Path, unifai_values: pathlib.Path) -> Dict[str, str]:
    """The five application images and the catalog, as pinned in the repository."""
    stack = (yaml.safe_load(cluster_file.read_text(encoding="utf-8")) or {}).get("zuno_unifai_values", {})
    images = (stack.get("stack") or {}).get("images") or {}
    refs: Dict[str, str] = {}
    for component in APPLICATION_IMAGES:
        ref = images.get(component, "")
        if not ref.startswith(FAMILY) or "@sha256:" not in ref:
            raise MirrorError(f"{cluster_file}: stack.images.{component} is not a pinned {FAMILY}* reference: {ref!r}")
        refs[f"unifai-{component}"] = ref
    match = CATALOG_RE.search(unifai_values.read_text(encoding="utf-8"))
    if not match:
        raise MirrorError(f"{unifai_values}: no pinned catalogImage")
    refs["unifai-operator-catalog"] = match.group(1)
    return refs


def resolve_tag(repository: str, tag: str) -> str:
    out = subprocess.run(["skopeo", "inspect", "--no-creds", "--format", "{{.Digest}}", f"docker://{repository}:{tag}"],
                         capture_output=True, text=True)
    digest = out.stdout.strip()
    if out.returncode != 0 or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise MirrorError(f"{repository}:{tag}: cannot resolve a digest ({out.stderr.strip()[:200] or 'no output'})")
    return f"{repository}@{digest}"


def _tags(digest_hex: str) -> List[str]:
    return [f"sha256-{digest_hex}{suffix}" for suffix in (".sig", ".att", ".sbom")]


def _copy_tag(src_repo: str, dst_repo: str, tag: str, run: Callable[..., str]) -> Optional[str]:
    """Copy `repo:tag` (with its referrers); a missing tag is not an error, the verification decides."""
    try:
        run([admit.require("oras"), "cp", "-r", f"{src_repo}:{tag}", f"{dst_repo}:{tag}"])
    except admit.AdmissionError as exc:
        if "not found" in str(exc).lower():
            return None
        raise
    return tag


def copy_image(source: str, mirror: str, run: Callable[..., str] = admit.run) -> str:
    """Copy one pinned image and everything cosign reads next to it; return the mirrored reference."""
    target = admit.mirror_reference(source, mirror)
    src_repo, dst_repo = source.split("@", 1)[0], target.split("@", 1)[0]
    digest = admit._hex(source)
    run([admit.require("oras"), "cp", "-r", source, f"{dst_repo}:d-{digest[:12]}"])
    for tag in _tags(digest):
        _copy_tag(src_repo, dst_repo, tag, run)
    # The SBOM artifact is signed on its own digest: `sha256-<sbom digest>.sig` (and .att) must travel too.
    try:
        sbom = run([admit.require("oras"), "resolve", f"{src_repo}:sha256-{digest}.sbom"]).strip()
    except admit.AdmissionError:
        sbom = ""
    if sbom.startswith("sha256:"):
        for suffix in (".sig", ".att"):
            _copy_tag(src_repo, dst_repo, f"{sbom.replace(':', '-')}{suffix}", run)
    got = run([admit.require("oras"), "resolve", f"{dst_repo}:d-{digest[:12]}"]).strip()
    if got != f"sha256:{digest}":
        raise MirrorError(f"mirror digest mismatch for {target}: the mirror holds {got}")
    return target


def mirror_all(references: Dict[str, str], mirror: str, accept_dev: bool = False, dry_run: bool = False,
               verify: Optional[Callable[[str, Optional[str]], v.Result]] = None,
               copy: Callable[[str, str], str] = copy_image) -> List[str]:
    identities = v.load_identities()
    with admit.offline_trust() as env:
        check = verify or (lambda reference, policy: v.verify_image(reference, env, identities, accept_dev,
                                                                    policy_reference=policy))
        for name, ref in references.items():
            res = check(ref, None)
            if not res.ok:
                raise MirrorError(f"{ref}: refused at its source - {res.reason[:300]}")
        if dry_run:
            return [admit.mirror_reference(ref, mirror) for ref in references.values()]
        out = []
        for name, ref in references.items():
            target = copy(ref, mirror)
            res = check(target, ref)
            if not res.ok:
                raise MirrorError(f"{target}: refused from the mirror - {res.reason[:300]}")
            out.append(target)
        return out


def make_public(mirror: str, names: List[str], token: str,
                request: Optional[Callable[[str, str, str, dict], None]] = None) -> None:
    host, org = mirror.split("/", 1)

    def default_request(method: str, url: str, tok: str, body: dict) -> None:
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method=method,
                                     headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30):  # trust: system store (Let's Encrypt route certificate)
            pass

    send = request or default_request
    for name in names:
        send("POST", f"https://{host}/api/v1/repository/{org}/{name}/changevisibility", token, {"visibility": "public"})


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--to", required=True, help="registry prefix, <route host>/<organisation>")
    parser.add_argument("--version", required=True, help="operator release whose operator and bundle images are copied, e.g. 0.1.68")
    parser.add_argument("--cluster", default="demo333")
    parser.add_argument("--accept-dev", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        refs = pinned_references(REPO_ROOT / "ansible" / "clusters" / f"{args.cluster}.yml",
                                 REPO_ROOT / "gitops" / "charts" / "unifai" / "values.yaml")
        refs["unifai-operator"] = resolve_tag(FAMILY + "unifai-operator", f"v{args.version}")
        refs["unifai-operator-bundle"] = resolve_tag(FAMILY + "unifai-operator-bundle", f"v{args.version}")
        done = mirror_all(refs, args.to, args.accept_dev, args.dry_run)
    except (MirrorError, admit.AdmissionError, v.ImageError) as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 1
    for ref in done:
        print(("WOULD COPY " if args.dry_run else "MIRRORED ") + ref)
    if not args.dry_run:
        import os
        token = os.environ.get("QUAY_API_TOKEN", "")
        if token:
            make_public(args.to, list(refs.keys()), token)
            print("repositories are publicly readable")
        else:
            print("QUAY_API_TOKEN not set: the repositories stay private until they are made public")
    return 0


if __name__ == "__main__":
    sys.exit(main())
