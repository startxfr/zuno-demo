#!/usr/bin/env python3
"""ADR-0586 policy-as-code check: a cluster that verifies its UnifAI images pins them by digest.

Reads `ansible/clusters/*.yml`. For a cluster whose `zuno_unifai_verify_images` is not
`false` (the default is on), the five application images of `zuno_unifai_values.stack.images`
(backend, identity, multiagent, rag, ui) must each be present and written `repo@sha256:...`,
and any other image listed there (the data services) must be pinned by digest as well. A tag
is mutable, so it proves nothing about what a pull returns.

A cluster that switches verification off says so in its own file; it is reported, not
failed, so the switch stays visible until it is turned back on.

Run from the repository root:
    python3 platform/supply-chain/check_unifai_pins.py [ansible/clusters/<cluster>.yml ...]
"""
from __future__ import annotations

import pathlib
import re
import sys
from typing import List, Tuple

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CLUSTERS_DIR = REPO_ROOT / "ansible" / "clusters"
APPLICATION_IMAGES = ("backend", "identity", "multiagent", "rag", "ui")
PINNED = re.compile(r"@sha256:[0-9a-f]{64}$")


def check_cluster(name: str, doc: dict) -> Tuple[List[str], List[str]]:
    """(findings, notes) for one cluster's variables."""
    if "zuno_unifai_values" not in doc:
        return [], []
    if doc.get("zuno_unifai_verify_images", True) is False:
        return [], [f"{name}: zuno_unifai_verify_images is false - its UnifAI images are not verified (ADR-0586)"]
    images = ((doc.get("zuno_unifai_values") or {}).get("stack") or {}).get("images") or {}
    findings: List[str] = []
    for component in APPLICATION_IMAGES:
        ref = images.get(component)
        if not ref:
            findings.append(f"{name}: stack.images.{component} is missing (the five application images are pinned by "
                            f"digest while verification is on)")
        elif not PINNED.search(str(ref)):
            findings.append(f"{name}: stack.images.{component} = {ref} is not pinned by digest")
    for component, ref in sorted(images.items()):
        if component not in APPLICATION_IMAGES and not PINNED.search(str(ref)):
            findings.append(f"{name}: stack.images.{component} = {ref} is not pinned by digest")
    return findings, []


def main(argv: List[str]) -> int:
    paths = [REPO_ROOT / a for a in argv] if argv else sorted(CLUSTERS_DIR.glob("*.yml"))
    findings: List[str] = []
    notes: List[str] = []
    for path in paths:
        f, n = check_cluster(path.stem, yaml.safe_load(path.read_text(encoding="utf-8")) or {})
        findings += f
        notes += n
    print(f"Checked {len(paths)} cluster file(s) under ansible/clusters/.")
    for note in notes:
        print(f"  - {note}")
    for finding in findings:
        print(f"  ✗ {finding}")
    if findings:
        print("\nRESULT: FAIL - pin every UnifAI image by digest, or set zuno_unifai_verify_images: false in the "
              "cluster file with its reason (ADR-0586).")
        return 1
    print("\nRESULT: PASS - every cluster that verifies its UnifAI images pins them by digest.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
