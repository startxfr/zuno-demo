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

`make d2 install unifai` runs it on the catalog and the five application images before it applies anything. The pin scripts
(`pin_operator_catalog.py`, `pin_unifai_images.py`) run it too, through `pin_gate`, before they write a pin (WP-282): on every
digest of the release they pin, the operator and its bundle included, which the install step does not see. With `--mirror-to`
they copy what is missing first.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Callable, Dict, List, Optional

import yaml

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import admit_okf_bundle as admit  # noqa: E402

FAMILY = "quay.io/zuno/unifai-"
REF_RE = re.compile(r"^quay\.io/zuno/(unifai-[a-z-]+)(?::[^@]+)?@(sha256:[0-9a-f]{64})$")
HOST_KEY = "zuno_unifai_signature_mirror_host"


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


def mirror_prefix(cluster_file: pathlib.Path) -> str:
    """`<host>/zuno` when the cluster's admission policies read the UnifAI signatures from the internal registry, else ""."""
    data = yaml.safe_load(cluster_file.read_text(encoding="utf-8")) or {}
    host = str(data.get(HOST_KEY) or "").strip().rstrip("/")
    return f"{host}/zuno" if host else ""


def gate(prefix: str, copy: Optional[Callable[[List[str]], object]] = None,
         run: Callable[..., str] = admit.run) -> Callable[[List[str]], List[Dict]]:
    """The check for a pin script: the results for `refs`; with `copy`, what is missing is copied, then checked again."""
    def check(refs: List[str]) -> List[Dict]:
        results = check_refs(refs, prefix, run)
        missing = [r["reference"] for r in results if not r["ok"]]
        if missing and copy:
            copy(missing)
            results = check_refs(refs, prefix, run)
        return results
    return check


def pin_gate(cluster_file: pathlib.Path, mirror_to: Optional[str] = None, dry_run: bool = False, accept_dev: bool = False,
             log: Callable[[str], None] = lambda m: print(m, file=sys.stderr)) -> Optional[Callable[[List[str]], List[Dict]]]:
    """Copy before pin (WP-248, WP-282) for `cluster_file`, or None with a notice when its admission reads quay.io.

    `mirror_to` (the push robot's DOCKER_CONFIG) copies what is missing, with its signatures, before the check; a dry run
    never copies, so it lists what the real run would have to copy.
    """
    prefix = mirror_prefix(cluster_file)
    if not prefix:
        log(f"{cluster_file.parent.name if cluster_file.name == 'cluster.yml' else cluster_file.name} has no {HOST_KEY}: the admission reads the signatures from quay.io, no internal registry check")
        return None
    copy = None
    if mirror_to and not dry_run:
        import mirror_unifai_images as mirror  # noqa: E402 (it imports this module's neighbours, not this module)

        def copy(refs: List[str]) -> None:
            mirror.mirror_all({ref.split("@", 1)[0].rsplit("/", 1)[1]: ref for ref in refs}, mirror_to.rstrip("/"), accept_dev)
    return gate(prefix, copy)


def refusal(missing: List[Dict]) -> str:
    """The pin scripts' error when images are missing: each reference with its reason, then what to do."""
    listed = "; ".join(f"{r['reference']}: {r['reason']}" for r in missing)
    return (f"{len(missing)} image(s) not in the internal registry, nothing was written (the admission policies read the "
            f"signatures there, so the pods would be refused): {listed}. Copy them first: rerun with "
            f"--mirror-to <registry>/zuno (the push robot's DOCKER_CONFIG)")


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
