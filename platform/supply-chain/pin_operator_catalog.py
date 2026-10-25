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

    python3 platform/supply-chain/pin_operator_catalog.py latest --version 0.1.40
    python3 platform/supply-chain/pin_operator_catalog.py sha256:889d88be... [--dry-run]

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
        verifier: Optional[Callable[[List[str]], List[v.Result]]] = None) -> dict:
    if version is not None and not VERSION_RE.match(version):
        raise PinError(f"{version}: expected X.Y.Z")
    digest = resolver(CATALOG, "latest") if target == "latest" else target
    if not DIGEST.match(digest):
        raise PinError(f"{target}: expected `latest` or sha256:<64 hex>")
    refs = {"catalog": f"{CATALOG}@{digest}"}
    if version:
        refs["operator"] = f"{OPERATOR}@{resolver(OPERATOR, 'v' + version)}"
        refs["bundle"] = f"{BUNDLE}@{resolver(BUNDLE, 'v' + version)}"
    results = (verifier or (lambda r: v.verify_all(r, accept_dev=False)))(list(refs.values()))
    refused = [r for r in results if not r.ok]
    if refused:
        raise PinError("; ".join(f"{r.reference}: {r.reason[:200]}" for r in refused))
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
    args = parser.parse_args(argv)
    try:
        refs = pin(args.target, args.version, dry_run=args.dry_run)
    except (PinError, admit.AdmissionError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps({"ok": True, "written": not args.dry_run, "verified": refs}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
