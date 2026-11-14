#!/usr/bin/env python3
"""Refuse a UnifAI pin whose images are not in the internal Quay yet (ADR-0612, WP-248 family c).

Once `zuno_unifai_signature_mirror_host` is set, the admission policies read the image signatures from the internal
registry, not from quay.io. A release that was pinned before it was copied would leave the pods refused ("no signatures
found") with nothing in the pin to say why. This check is the "copy before pin" rule: for every `quay.io/zuno/unifai-*@sha256:`
reference it asks the registry, anonymously (the repositories are public), for the image by digest and for its `.sig` tag.

    python3 platform/supply-chain/check_unifai_in_registry.py --prefix quay-quay-zuno-registry.apps.demo333.startx.fr/zuno \\
        --refs-json refs.json

Prints {"results": [{"reference", "ok", "reason"}]} and exits 1 when one is missing. References outside quay.io/zuno/unifai-
are not this check's business and are skipped.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Callable, Dict, List, Optional

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import admit_okf_bundle as admit  # noqa: E402

FAMILY = "quay.io/zuno/unifai-"
REF_RE = re.compile(r"^quay\.io/zuno/(unifai-[a-z-]+)(?::[^@]+)?@(sha256:[0-9a-f]{64})$")


def check_ref(ref: str, prefix: str, run: Callable[..., str] = admit.run) -> Dict:
    m = REF_RE.match(ref)
    if not m:
        return {"reference": ref, "ok": False, "reason": "not pinned by digest (repo@sha256:...), so it cannot be looked up in the registry"}
    repo, digest = m.groups()
    base = f"{prefix}/{repo}"
    oras = admit.require("oras")
    try:
        got = json.loads(run([oras, "manifest", "fetch", "--descriptor", f"{base}@{digest}"])).get("digest", "")
    except (admit.AdmissionError, ValueError):
        return {"reference": ref, "ok": False, "reason": f"{base}@{digest} is not in the registry"}
    if got != digest:
        return {"reference": ref, "ok": False, "reason": f"the registry answers {got} for {digest}"}
    try:
        run([oras, "manifest", "fetch", "--descriptor", f"{base}:{digest.replace(':', '-')}.sig"])
    except admit.AdmissionError:
        return {"reference": ref, "ok": False, "reason": f"{base} holds the image but not its signature tag {digest.replace(':', '-')}.sig"}
    return {"reference": ref, "ok": True, "reason": ""}


def check_refs(refs: List[str], prefix: str, run: Callable[..., str] = admit.run) -> List[Dict]:
    return [check_ref(r, prefix, run) for r in refs if r.startswith(FAMILY)]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--prefix", required=True, help="registry route host and organisation, e.g. quay.example/zuno")
    parser.add_argument("--refs-json", required=True, help="a JSON list of image references")
    args = parser.parse_args(argv)
    try:
        refs = json.loads(pathlib.Path(args.refs_json).read_text())
        results = check_refs(refs, args.prefix.rstrip("/"))
    except (admit.AdmissionError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "results": []}))
        return 1
    print(json.dumps({"results": results}))
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
