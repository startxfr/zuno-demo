#!/usr/bin/env python3
"""Move the claw-operator and OpenClaw pins of gitops/charts/openclaw together (ADR-0590 decision 5).

claw-operator publishes no releases: `quay.io/codeready-toolchain/claw-operator-catalog:latest` is rebuilt on
every upstream commit and holds one bundle, whose CSV name carries the commit
(`claw-operator.v0.0.227-commit-f5aa592`) and whose manager and proxy images are referenced by tag. Nothing is
signed, so the chart pins digests and `make d2 check openclaw` compares the running image IDs with them. One
upgrade therefore changes four values at once: `operator.catalogImage`, `operator.startingCSV`,
`operator.pinnedImageDigests.{manager,proxy}`, plus `images.openclaw` and the chart's `appVersion`.

This resolves the catalog digest, reads the catalog's file-based config in memory (layers are read as data,
nothing from the image is run or written to disk), checks it has exactly one entry on the pinned channel,
resolves the manager and proxy tags to digests, resolves the OpenClaw image, and only then rewrites the chart.

    python3 platform/supply-chain/pin_claw_catalog.py --dry-run             # newest catalog, OpenClaw pin kept
    python3 platform/supply-chain/pin_claw_catalog.py --openclaw 2026.7.1-2 # a given OpenClaw tag
    python3 platform/supply-chain/pin_claw_catalog.py --catalog sha256:... --openclaw latest-stable

OpenClaw follows the operator, not its own release train: the operator writes and owns openclaw.json, and a newer
OpenClaw can refuse that config (2026.10.9 against operator f5aa592: moved and retired keys, plus a state-database
migration; tested on demo333 2026-11-02). So the OpenClaw pin is kept unless `--openclaw` names a tag, normally the
image the operator's CRD defaults to (`oc explain claw.spec.image`); `latest-stable` is for a deliberate test.

When the CSV changes, re-read the operator source at the new commit before installing (owned config keys,
passthrough domains, Route; see ansible/roles/openclaw/README.md). Exit 0 on success, 1 when something cannot be
resolved or the catalog is not the expected shape, 2 for a usage error.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import pathlib
import re
import subprocess
import sys
import tarfile
import tempfile
from typing import Callable, Dict, List, Optional

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CHART = REPO_ROOT / "gitops" / "charts" / "openclaw"
CATALOG = "quay.io/codeready-toolchain/claw-operator-catalog"
OPENCLAW = "ghcr.io/openclaw/openclaw"
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
STABLE_TAG = re.compile(r"^\d{4}\.\d+\.\d+(?:-\d+)?$")  # 2026.10.9, 2026.7.1-2; never -beta.N, -slim, -browser
IMAGE_ROLES = ("manager", "proxy")


class PinError(ValueError):
    pass


def resolve(repository: str, tag: str) -> str:
    out = subprocess.run(["skopeo", "inspect", "--no-creds", "--format", "{{.Digest}}", f"docker://{repository}:{tag}"],
                         capture_output=True, text=True)
    digest = out.stdout.strip()
    if out.returncode != 0 or not DIGEST.match(digest):
        raise PinError(f"{repository}:{tag}: cannot resolve a digest ({out.stderr.strip()[:200] or 'no output'})")
    return digest


def list_tags(repository: str) -> List[str]:
    out = subprocess.run(["skopeo", "list-tags", "--no-creds", f"docker://{repository}"], capture_output=True, text=True)
    if out.returncode != 0:
        raise PinError(f"{repository}: cannot list tags ({out.stderr.strip()[:200]})")
    return json.loads(out.stdout)["Tags"]


def newest_stable(tags: List[str]) -> str:
    stable = [t for t in tags if STABLE_TAG.match(t)]
    if not stable:
        raise PinError(f"{OPENCLAW}: no stable tag")
    return max(stable, key=lambda t: [int(p) for p in re.split(r"[.-]", t)])


def read_catalog_configs(reference: str) -> List[dict]:
    """The FBC documents under configs/ of an image, read from its layers as data."""
    with tempfile.TemporaryDirectory() as tmp:
        out = subprocess.run(["skopeo", "copy", "-q", "--src-no-creds", f"docker://{reference}", f"dir:{tmp}"],
                             capture_output=True, text=True)
        if out.returncode != 0:
            raise PinError(f"{reference}: cannot download ({out.stderr.strip()[:200]})")
        manifest = json.loads((pathlib.Path(tmp) / "manifest.json").read_text())
        docs: List[dict] = []
        for layer in manifest["layers"]:
            blob = (pathlib.Path(tmp) / layer["digest"].split(":", 1)[1]).read_bytes()
            raw = gzip.decompress(blob) if blob[:2] == b"\x1f\x8b" else blob
            with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
                for member in tar.getmembers():
                    name = member.name.lstrip("./")
                    if not member.isfile() or not name.startswith("configs/"):
                        continue
                    text = tar.extractfile(member).read().decode("utf-8")
                    if name.endswith(".json"):
                        docs.extend(json.loads(chunk) for chunk in re.split(r"(?<=\})\s*(?=\{)", text.strip()) if chunk)
                    elif name.endswith((".yaml", ".yml")):
                        docs.extend(d for d in yaml.safe_load_all(text) if d)
        return docs


def bundle_of(docs: List[dict], package: str, channel: str) -> dict:
    channels = [d for d in docs if d.get("schema") == "olm.channel" and d.get("package") == package
                and d.get("name") == channel]
    if len(channels) != 1 or len(channels[0].get("entries", [])) != 1:
        raise PinError(f"catalog: expected one channel {package}/{channel} with exactly one entry, found "
                       f"{[[e.get('name') for e in c.get('entries', [])] for c in channels]}")
    csv = channels[0]["entries"][0]["name"]
    bundles = [d for d in docs if d.get("schema") == "olm.bundle" and d.get("name") == csv]
    if len(bundles) != 1:
        raise PinError(f"catalog: no olm.bundle named {csv}")
    return bundles[0]


def related(bundle: dict) -> Dict[str, str]:
    images = {r.get("name"): r["image"] for r in bundle.get("relatedImages", [])}
    missing = [role for role in IMAGE_ROLES if role not in images]
    if missing:
        raise PinError(f"bundle {bundle['name']}: no relatedImages {missing}")
    return {role: images[role] for role in IMAGE_ROLES}


def split_ref(ref: str):
    if "@" in ref:
        repo, digest = ref.split("@", 1)
        return repo, None, digest
    repo, tag = ref.rsplit(":", 1)
    return repo, tag, None


def set_line(text: str, pattern: str, value: str, what: str) -> str:
    new, count = re.subn(pattern, lambda m: m.group(1) + value, text, count=1, flags=re.M)
    if count != 1:
        raise PinError(f"no `{what}` line to rewrite")
    return new


def rewrite_values(text: str, pins: dict) -> str:
    text = set_line(text, r"^(\s*catalogImage: )\S+$", f"{CATALOG}@{pins['catalog']}", "operator.catalogImage")
    text = set_line(text, r"^(\s*startingCSV: )\S+$", pins["csv"], "operator.startingCSV")
    for role in IMAGE_ROLES:
        text = set_line(text, rf"^(\s*{role}: )sha256:[0-9a-f]{{64}}$", pins[role], f"pinnedImageDigests.{role}")
    text = set_line(text, r"^(\s*openclaw: )\S+$", f"{OPENCLAW}@{pins['openclaw']}", "images.openclaw")
    return text


def pin(catalog: str = "latest", openclaw: str = "keep", chart: pathlib.Path = CHART,
        dry_run: bool = False, resolver: Callable[[str, str], str] = resolve,
        tags: Callable[[str], List[str]] = list_tags,
        configs: Callable[[str], List[dict]] = read_catalog_configs) -> dict:
    values_path, chart_path = chart / "values.yaml", chart / "Chart.yaml"
    values = yaml.safe_load(values_path.read_text(encoding="utf-8"))
    op = values["operator"]
    digest = resolver(CATALOG, "latest") if catalog == "latest" else catalog
    if not DIGEST.match(digest):
        raise PinError(f"{catalog}: expected `latest` or sha256:<64 hex>")
    bundle = bundle_of(configs(f"{CATALOG}@{digest}"), op["package"], op["channel"])
    pins = {"catalog": digest, "csv": bundle["name"]}
    for role, ref in related(bundle).items():
        repo, tag, ref_digest = split_ref(ref)
        pins[role] = ref_digest or resolver(repo, tag)
        pins[f"{role}_ref"] = ref
    if openclaw == "keep":
        current = values["images"]["openclaw"]
        if not current.startswith(OPENCLAW + "@sha256:"):
            raise PinError(f"images.openclaw is not pinned by digest: {current}")
        pins["openclaw_tag"] = None
        pins["openclaw"] = current.split("@", 1)[1]
    else:
        oc_tag = newest_stable(tags(OPENCLAW)) if openclaw == "latest-stable" else openclaw
        pins["openclaw_tag"] = oc_tag
        pins["openclaw"] = resolver(OPENCLAW, oc_tag)
    version = next((p["value"]["version"] for p in bundle.get("properties", []) if p.get("type") == "olm.package"), None)
    new_values = rewrite_values(values_path.read_text(encoding="utf-8"), pins)
    yaml.safe_load(new_values)
    new_chart = chart_path.read_text(encoding="utf-8")
    if version:
        new_chart = set_line(new_chart, r'^(appVersion: )\S+$', f'"{version}"', "appVersion")
    pins["csv_changed"] = pins["csv"] != op["startingCSV"]
    if not dry_run:
        values_path.write_text(new_values, encoding="utf-8")
        chart_path.write_text(new_chart, encoding="utf-8")
    return pins


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--catalog", default="latest", help="`latest` (default) or the catalog digest sha256:...")
    parser.add_argument("--openclaw", default="keep",
                        help="OpenClaw tag, `latest-stable`, or `keep` (default: the current pin)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        pins = pin(args.catalog, args.openclaw, dry_run=args.dry_run)
    except (PinError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps({"ok": True, "written": not args.dry_run, "pins": pins}, indent=2))
    if pins["csv_changed"]:
        print(f"note: the operator moved to {pins['csv']}: re-read its source at that commit before installing "
              "(ansible/roles/openclaw/README.md)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
