#!/usr/bin/env python3
"""Move the UnifAI operator catalog pin of the d0 chart to a released, signed catalog (ADR-0586).

Each operator release publishes a catalog image whose repository only has a moving `latest` tag, so the
d0 chart pins it by digest (`operator.catalogImage` in gitops/charts/unifai/values.yaml) and the
`unifai` role moves a hand-applied CatalogSource to that digest. Every release therefore needs one pin
bump. This resolves the digest, verifies it with the same policy as the role (the operator release
workflow's identity, never the development one: `verify_unifai_images.verify_image`, signature, provenance,
signed SBOM) and only then rewrites the `catalogImage` line of the chart.

With `--version X.Y.Z` it also verifies the operator image `quay.io/zuno/unifai-operator:vX.Y.Z` and the
bundle `quay.io/zuno/unifai-operator-bundle:vX.Y.Z` (resolved to digests) and updates the "Current: ..."
comment. Nothing is written if anything is refused.

Copy before pin (WP-248, WP-282): when the cluster's admission policies read the signatures from the internal Quay
(`zuno_unifai_signature_mirror_host` in `ansible/clusters/<cluster>.yml`), every digest must be there, with its `.sig` tag,
before the pin is written; the missing ones are listed and nothing is written. `--mirror-to <registry>/zuno` copies them
first (the push robot's DOCKER_CONFIG). A dry run copies nothing: it lists what the real run has to copy.

    python3 platform/supply-chain/pin_operator_catalog.py latest --version 0.1.40
    python3 platform/supply-chain/pin_operator_catalog.py sha256:889d88be... --version 0.1.40 [--dry-run] \\
        [--mirror-to quay-quay-zuno-registry.apps.demo333.startx.fr/zuno] [--cluster demo333]

`latest` is resolved at the time of the call (the catalog of the newest release). Exit 0 on success, 1 when
an image is refused or cannot be resolved, 2 for a usage error.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from typing import Callable, List, Optional

import yaml

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import admit_okf_bundle as admit  # noqa: E402
import admission_preflight  # noqa: E402
import check_unifai_in_registry as registry_check  # noqa: E402
import verify_unifai_images as v  # noqa: E402

REPO_ROOT = HERE.parents[1]
CHART_VALUES = REPO_ROOT / "gitops" / "charts" / "unifai" / "values.yaml"
CATALOG = "quay.io/zuno/unifai-operator-catalog"
OPERATOR = "quay.io/zuno/unifai-operator"
BUNDLE = "quay.io/zuno/unifai-operator-bundle"
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
LINE_RE = re.compile(r"^(\s*catalogImage: )quay\.io/zuno/unifai-operator-catalog(?:[:@]\S+)?\s*$")


class PinError(ValueError):
    pass


def resolve(repository: str, tag: str) -> str:
    out = subprocess.run(["skopeo", "inspect", "--no-creds", "--format", "{{.Digest}}", f"docker://{repository}:{tag}"],
                         capture_output=True, text=True)
    digest = out.stdout.strip()
    if out.returncode != 0 or not DIGEST.match(digest):
        raise PinError(f"{repository}:{tag}: cannot resolve a digest ({out.stderr.strip()[:200] or 'no output'})")
    return digest


def rewrite(text: str, digest: str, version: Optional[str]) -> str:
    lines = text.splitlines(keepends=True)
    done = False
    for i, line in enumerate(lines):
        m = LINE_RE.match(line.rstrip("\n"))
        if m and not done:
            lines[i] = f"{m.group(1)}{CATALOG}@{digest}\n"
            done = True
    if not done:
        raise PinError("no `catalogImage: quay.io/zuno/unifai-operator-catalog...` line to rewrite")
    out = "".join(lines)
    if version:
        out = re.sub(r"(Current: )\d+\.\d+\.\d+", rf"\g<1>{version}", out, count=1)
    return out


def pin(target: str, version: Optional[str], values: pathlib.Path = CHART_VALUES, dry_run: bool = False,
        resolver: Callable[[str, str], str] = resolve,
        verifier: Optional[Callable[[List[str]], List[v.Result]]] = None,
        admission: Optional[Callable[[List[str]], List[v.Result]]] = None,
        warn: Callable[[str], None] = lambda m: print(f"warning: {m}", file=sys.stderr),
        registry: Optional[Callable[[List[str]], List[dict]]] = None) -> dict:
    if version is not None and not VERSION_RE.match(version):
        raise PinError(f"{version}: expected X.Y.Z")
    digest = resolver(CATALOG, "latest") if target == "latest" else target
    if not DIGEST.match(digest):
        raise PinError(f"{target}: expected `latest` or sha256:<64 hex>")
    refs = {"catalog": f"{CATALOG}@{digest}"}
    if version:
        refs["operator"] = f"{OPERATOR}@{resolver(OPERATOR, 'v' + version)}"
        refs["bundle"] = f"{BUNDLE}@{resolver(BUNDLE, 'v' + version)}"
    if version:
        # A digest that only carries `latest` is garbage-collected by quay, signatures included, when `latest` moves
        # on (found 2026-10-31): without a v<version> tag on it no rollback is possible later. A warning, not a refusal.
        try:
            tagged = resolver(CATALOG, "v" + version)
        except PinError:
            tagged = None
        if tagged != digest:
            warn(f"{CATALOG}@{digest} has no v{version} tag: quay will garbage-collect it, with its signatures, "
                 f"when `latest` moves; ask for the tag (docs/platform/operations.md, catalog tags)")
    results = (verifier or (lambda r: v.verify_all(r, accept_dev=False)))(list(refs.values()))
    refused = [r for r in results if not r.ok]
    if refused:
        raise PinError("; ".join(f"{r.reference}: {r.reason[:200]}" for r in refused))
    if registry:  # copy before pin (WP-282), before the webhook: it would refuse a missing image with less to say
        missing = [r for r in registry(list(refs.values())) if not r["ok"]]
        if missing:
            raise PinError(registry_check.refusal(missing))
    if admission:  # the cluster's admission webhook on the same digests (WP-178)
        blocked = [r for r in admission(list(refs.values())) if not r.ok]
        if blocked:
            raise PinError("; ".join(f"{r.reference}: {r.reason[:300]}" for r in blocked))
    new = rewrite(values.read_text(encoding="utf-8"), digest, version)
    yaml.safe_load(new)
    if not dry_run:
        values.write_text(new, encoding="utf-8")
    return refs


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("target", help="`latest` or the catalog digest sha256:...")
    parser.add_argument("--version", help="X.Y.Z of the release: also verify the operator and bundle images")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-admission-preflight", action="store_true",
                        help="do not ask the cluster's admission webhook about the digests (WP-178)")
    parser.add_argument("--cluster", default="demo333",
                        help="the cluster whose internal registry must hold the digests before the pin (WP-282)")
    parser.add_argument("--mirror-to", metavar="PREFIX",
                        help="copy the missing digests with their signatures into the internal Quay before the check, e.g. "
                             "quay-quay-zuno-registry.apps.demo333.startx.fr/zuno (push robot in DOCKER_CONFIG; ADR-0612)")
    args = parser.parse_args(argv)
    cluster_file = REPO_ROOT / "ansible" / "clusters" / f"{args.cluster}.yml"
    if not cluster_file.is_file():
        parser.error(f"{cluster_file} does not exist")
    try:
        refs = pin(args.target, args.version, dry_run=args.dry_run,
                   admission=None if args.no_admission_preflight else admission_preflight.run_or_skip,
                   registry=registry_check.pin_gate(cluster_file, args.mirror_to, args.dry_run))
    except (PinError, admit.AdmissionError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps({"ok": True, "written": not args.dry_run, "verified": refs,
                      "mirrored_to": args.mirror_to if not args.dry_run else None}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
