#!/usr/bin/env python3
"""Pin the five UnifAI application images of a cluster to a CI-built `devel-<sha>` (ADR-0586).

A UnifAI deployment is a commit that changes five digests in `ansible/clusters/<cluster>.yml`.
This resolves the digest of `quay.io/zuno/unifai-<component>:devel-<sha>` for the five
components (skopeo), verifies every one with the same policy the `unifai` role applies
(`verify_unifai_images.verify_image`: signature, provenance, signed SBOM, identity of the fork's
publish workflow), and only then rewrites the five lines. One image that does not verify, or a
tag that does not exist, changes nothing. Then, when the cluster answers, the same digests go through its admission webhook (a server-side dry-run
Pod, `admission_preflight.py`, WP-178): a warning or a refusal stops the pin too. `--no-admission-preflight` skips that
step; an unreachable cluster skips it with a notice.

Run from the repository root:
    python3 platform/supply-chain/pin_unifai_images.py devel-ffb64e335 [--cluster demo333] [--accept-dev] [--dry-run]

`--accept-dev` is required for a `devel-<sha>` (a development identity); a release tag `vX.Y.Z` needs
none. The edit is line by line, so the comments of the cluster file survive. Exit 0 on success,
1 when an image is refused or cannot be resolved, 2 for a usage error.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from typing import Callable, Dict, List, Optional

import yaml

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import admit_okf_bundle as admit  # noqa: E402
import admission_preflight  # noqa: E402
import verify_unifai_images as v  # noqa: E402
from check_unifai_pins import APPLICATION_IMAGES  # noqa: E402

REPO_ROOT = HERE.parents[1]
FAMILY = "quay.io/zuno/unifai-"
TAG_RE = re.compile(r"^(devel-[0-9a-f]{7,40}|v\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?)$")


class PinError(ValueError):
    pass


def resolve_digest(repository: str, tag: str) -> str:
    """The digest the registry serves for `repository:tag` (the manifest list digest)."""
    out = subprocess.run(["skopeo", "inspect", "--no-creds", "--format", "{{.Digest}}", f"docker://{repository}:{tag}"],
                         capture_output=True, text=True)
    digest = out.stdout.strip()
    if out.returncode != 0 or not v.DIGEST_RE.search("@" + digest):
        raise PinError(f"{repository}:{tag}: cannot resolve a digest ({out.stderr.strip()[:200] or 'no output'})")
    return digest


def rewrite(text: str, pins: Dict[str, str], label: str) -> str:
    """Replace the five `stack.images.<component>` lines, keeping indentation and comments."""
    lines = text.splitlines(keepends=True)
    done: set = set()
    for i, line in enumerate(lines):
        m = re.match(r"^(\s+)(backend|identity|multiagent|rag|ui): quay\.io/zuno/unifai-\2(?:[:@]\S+)?(\s*#.*)?$", line.rstrip("\n"))
        if m and m.group(2) not in done:
            lines[i] = f"{m.group(1)}{m.group(2)}: {pins[m.group(2)]}  # {label}\n"
            done.add(m.group(2))
    missing = [c for c in APPLICATION_IMAGES if c not in done]
    if missing:
        raise PinError(f"the cluster file has no stack.images line to rewrite for: {', '.join(missing)}")
    return "".join(lines)


def pin(tag: str, cluster_file: pathlib.Path, accept_dev: bool, dry_run: bool = False,
        resolver: Callable[[str, str], str] = resolve_digest,
        verifier: Optional[Callable[[List[str], bool], List[v.Result]]] = None,
        admission: Optional[Callable[[List[str]], List[v.Result]]] = None) -> Dict[str, str]:
    if not TAG_RE.match(tag):
        raise PinError(f"{tag}: expected devel-<sha> or vX.Y.Z")
    if tag.startswith("devel-") and not accept_dev:
        raise PinError(f"{tag} is a development build: pass --accept-dev (the cluster must also accept it)")
    pins = {c: f"{FAMILY}{c}@{resolver(FAMILY + c, tag)}" for c in APPLICATION_IMAGES}
    results = (verifier or (lambda refs, dev: v.verify_all(refs, accept_dev=dev)))(list(pins.values()), accept_dev)
    refused = [r for r in results if not r.ok]
    if refused:
        raise PinError("; ".join(f"{r.reference}: {r.reason[:200]}" for r in refused))
    # What the cluster's admission webhook says about the same digests (WP-178): a digest cosign accepts but the
    # policy-controller does not (e.g. a signature only in the Ed25519 Rekor v2 log) would be refused in `enforce`.
    if admission:
        refused = [r for r in admission(list(pins.values())) if not r.ok]
        if refused:
            raise PinError("; ".join(f"{r.reference}: {r.reason[:300]}" for r in refused))
    new = rewrite(cluster_file.read_text(encoding="utf-8"), pins, tag)
    yaml.safe_load(new)
    if not dry_run:
        cluster_file.write_text(new, encoding="utf-8")
    return pins


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("tag", help="devel-<sha> or vX.Y.Z")
    parser.add_argument("--cluster", default="demo333")
    parser.add_argument("--accept-dev", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-admission-preflight", action="store_true",
                        help="do not ask the cluster's admission webhook about the digests (WP-178)")
    args = parser.parse_args(argv)
    path = REPO_ROOT / "ansible" / "clusters" / f"{args.cluster}.yml"
    if not path.is_file():
        parser.error(f"{path} does not exist")
    try:
        pins = pin(args.tag, path, args.accept_dev, args.dry_run,
                   admission=None if args.no_admission_preflight else admission_preflight.run_or_skip)
    except (PinError, admit.AdmissionError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps({"ok": True, "tag": args.tag, "written": not args.dry_run, "pins": pins}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
