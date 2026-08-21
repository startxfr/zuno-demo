#!/usr/bin/env python3
"""ADR-0115 release-pinning helper, stage 1 of WP-04 (docs/roadmap/
work-packages/wp-04-supply-chain-completion.md): once a real release
exists (RELEASING.md steps 1-3: tag pushed, `build-publish.yml` builds,
scans, SBOMs and signs every image), this script mechanically rewrites
every chart's `tag: latest`/`tag: ""` field that
`check_no_latest_tags.py` currently flags to the real immutable tag the
release produced - "so stage 3 is mechanical" (the WP-04 brief's own
words), not a second round of manual editing.

Deliberately narrow in scope, on purpose:

- rewrites `tag` fields only, never `repository`/`frontendRepository`/
  `bffRepository` - RELEASING.md step 4 notes charts MAY also need to move
  off the in-cluster-registry placeholder coordinates to `quay.io/...` for
  a real release, but that is an explicit, reviewed decision for the
  operator to make chart-by-chart, not something this tool should infer or
  automate.
- edits the raw text of each `values.yaml` line by line rather than
  round-tripping through `yaml.safe_load`/`yaml.dump`, so every existing
  comment in these files (several are load-bearing, e.g. "Built by the
  'agent' build component...") survives untouched. `yaml.safe_load` is
  used only to VALIDATE the resulting file is still well-formed YAML after
  the edit, never to regenerate it.
- refuses to run unless the manifest's `pins` plus its `skipped` cover
  EXACTLY the set of fields `check_no_latest_tags.py` currently reports (no
  more, no less) - a stale/incomplete manifest is a loud error, not a
  partial, silent fix. `skipped` exists for fields a given release
  genuinely cannot pin (e.g. `rag-ingestion` is built exclusively by the
  in-cluster OpenShift BuildConfig, never by `build-publish.yml` - no real
  Quay artifact for it exists from a GitHub Actions release) - each entry
  requires a `reason`, is written to the audit ledger alongside the real
  pins, and does NOT silence `check_no_latest_tags.py` itself: a skipped
  field still fails that check, honestly, until its own release path pins
  it for real.
- records each pin's optional digest in a small audit ledger
  (`platform/supply-chain/pinned-releases.yaml`) rather than embedding it
  in `values.yaml`: every chart's Deployment template renders
  `"{{ .Values.image.repository }}:{{ .Values.image.tag }}"` (tag only,
  no digest syntax) - adding real digest-pinned deployment is a template
  change, tracked separately, not silently done here.

Manifest format (YAML, produced by the operator from the real release's
build-publish.yml run output):

    release_tag: v0.1.0
    pins:
      - chart_values: gitops/charts/agent-runtime/values.yaml
        path: image.tag
        tag: v0.1.0
        digest: sha256:...          # optional, audit-only (see above)
    skipped:                        # optional - see above
      - chart_values: gitops/charts/rag-ingestion/values.yaml
        path: images.ingestion.tag
        reason: >-
          built exclusively by the in-cluster OpenShift BuildConfig
          (ansible/roles/rag_ingestion_build), never by build-publish.yml -
          no real Quay artifact from this release to pin to

Run from the repository root:

    python3 platform/supply-chain/pin_release.py --manifest <path> [--dry-run]
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
LEDGER_PATH = REPO_ROOT / "platform" / "supply-chain" / "pinned-releases.yaml"

# Kept identical to check_no_latest_tags.py's own definition on purpose -
# this tool must find exactly the same gaps that check reports, or a
# manifest built against one script's output could silently miss a field
# the other considers unresolved.
FORBIDDEN_TAG_VALUES = {"latest", ""}

TAG_LINE_RE = re.compile(r"^(\s*)tag:\s*(.*?)\s*$")


@dataclass
class TagFinding:
    chart_values: str  # repo-relative path, e.g. "gitops/charts/agent-runtime/values.yaml"
    path: str  # dotted YAML path, e.g. "image.tag" or "images.ingestion.tag"
    current_value: str


def _walk(node: Any, path: str, findings: List[TagFinding], file_label: str) -> None:
    """Identical shape to check_no_latest_tags.py's `_walk` - see that
    file for why this exact recursion (dict/list, `tag` key by name) is
    the authoritative definition of "a non-immutable image tag field"."""
    if isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}" if path else str(key)
            if key == "tag" and isinstance(value, str) and value in FORBIDDEN_TAG_VALUES:
                findings.append(TagFinding(file_label, child_path, value))
            else:
                _walk(value, child_path, findings, file_label)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _walk(item, f"{path}[{i}]", findings, file_label)


def _current_findings() -> List[TagFinding]:
    findings: List[TagFinding] = []
    for values_path in sorted((REPO_ROOT / "gitops" / "charts").glob("*/values.yaml")):
        doc = yaml.safe_load(values_path.read_text()) or {}
        _walk(doc, "", findings, str(values_path.relative_to(REPO_ROOT)))
    return findings


def _load_manifest(manifest_path: pathlib.Path) -> Dict[str, Any]:
    doc = yaml.safe_load(manifest_path.read_text()) or {}
    if "pins" not in doc or not isinstance(doc["pins"], list):
        raise ValueError(f"manifest {manifest_path} has no top-level 'pins' list")
    for pin in doc["pins"]:
        for required in ("chart_values", "path", "tag"):
            if required not in pin:
                raise ValueError(f"manifest pin {pin!r} is missing required field '{required}'")
    skipped = doc.get("skipped", [])
    if not isinstance(skipped, list):
        raise ValueError(f"manifest {manifest_path}'s 'skipped' must be a list")
    for skip in skipped:
        for required in ("chart_values", "path", "reason"):
            if required not in skip:
                raise ValueError(f"manifest skip {skip!r} is missing required field '{required}'")
    return doc


def _apply_pins_to_file(
    chart_values: str, ordered_pins: List[Dict[str, Any]], all_paths_in_order: List[str], dry_run: bool
) -> str:
    """`ordered_pins` must be in the same top-to-bottom order as the
    file's own literal `tag:` lines that are actually PINNED - guaranteed
    by the caller, which zips each file's pins against
    `_current_findings()`'s walk order (itself provably identical to file
    order: `yaml.safe_load` preserves key order, and `_walk` iterates
    `dict.items()` in that order).

    `all_paths_in_order` is that same file's FULL document-order path
    list, including paths this manifest chose to `skip` rather than pin
    (e.g. rag-ingestion's `images.compiler.tag` sits between other
    charts' single `image.tag` line and would otherwise be miscounted) -
    needed to correlate each literal `tag:` line to its YAML path so a
    skipped line in the middle of a file doesn't shift every pin below it
    by one line. `len(all_paths_in_order)` must equal the file's total
    literal `tag:` line count; a file with only pinned fields (the common
    case) has `all_paths_in_order == [p["path"] for p in ordered_pins]`.
    """
    file_path = REPO_ROOT / chart_values
    lines = file_path.read_text().splitlines(keepends=True)

    tag_line_indices = [i for i, line in enumerate(lines) if TAG_LINE_RE.match(line)]
    if len(tag_line_indices) != len(all_paths_in_order):
        raise ValueError(
            f"{chart_values}: found {len(tag_line_indices)} literal 'tag:' line(s) but "
            f"{len(all_paths_in_order)} pinned+skipped path(s) are known for this file - "
            "refusing to guess which is which"
        )
    pinned_paths = {p["path"] for p in ordered_pins}
    pinned_line_indices = [
        line_index
        for line_index, path in zip(tag_line_indices, all_paths_in_order)
        if path in pinned_paths
    ]
    if len(pinned_line_indices) != len(ordered_pins):
        raise ValueError(
            f"{chart_values}: matched {len(pinned_line_indices)} pinned 'tag:' line(s) but "
            f"{len(ordered_pins)} pin(s) target this file - refusing to guess which is which"
        )

    for line_index, pin in zip(pinned_line_indices, ordered_pins):
        match = TAG_LINE_RE.match(lines[line_index])
        assert match is not None
        indent = match.group(1)
        old_value = match.group(2)
        new_line = f"{indent}tag: {pin['tag']}\n"
        print(
            f"  {chart_values}:{line_index + 1} [{pin['path']}] "
            f"tag: {old_value!r} -> {pin['tag']!r}"
        )
        lines[line_index] = new_line

    new_text = "".join(lines)
    if not dry_run:
        file_path.write_text(new_text)
        # Validate the result is still well-formed YAML - this tool edits
        # text, not a parsed structure, so this is the only thing standing
        # between a regex slip and a broken chart.
        yaml.safe_load(new_text)
    return new_text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True, type=pathlib.Path, help="release manifest YAML path")
    parser.add_argument("--dry-run", action="store_true", help="print the intended edits without writing files")
    args = parser.parse_args()

    try:
        manifest = _load_manifest(args.manifest)
    except (OSError, ValueError) as exc:
        print(f"RESULT: FAIL - {exc}")
        return 1

    current = _current_findings()
    current_keys = {(f.chart_values, f.path) for f in current}
    manifest_keys = {(p["chart_values"], p["path"]) for p in manifest["pins"]}
    skipped = manifest.get("skipped", [])
    skipped_keys = {(s["chart_values"], s["path"]) for s in skipped}

    overlap = manifest_keys & skipped_keys
    stale_skips = skipped_keys - current_keys
    missing = current_keys - manifest_keys - skipped_keys
    extra = manifest_keys - current_keys
    if missing or extra or overlap or stale_skips:
        if missing:
            print(f"{len(missing)} non-immutable tag field(s) have no pin or skip in the manifest:")
            for chart_values, path in sorted(missing):
                print(f"  ✗ {chart_values}: {path}")
        if extra:
            print(f"{len(extra)} manifest pin(s) do not match any current non-immutable field:")
            for chart_values, path in sorted(extra):
                print(f"  ✗ {chart_values}: {path} (already pinned, wrong path, or typo)")
        if overlap:
            print(f"{len(overlap)} field(s) are both pinned and skipped - pick one:")
            for chart_values, path in sorted(overlap):
                print(f"  ✗ {chart_values}: {path}")
        if stale_skips:
            print(f"{len(stale_skips)} skipped field(s) are not actually non-immutable anymore:")
            for chart_values, path in sorted(stale_skips):
                print(f"  ✗ {chart_values}: {path} (already pinned, wrong path, or stale skip)")
        print(
            "\nRESULT: FAIL - the manifest's pins plus skipped fields must cover exactly "
            "the fields check_no_latest_tags.py currently reports, no more and no less."
        )
        return 1

    if skipped:
        print(f"{len(skipped)} field(s) deliberately skipped (still non-immutable, not pinned by this release):")
        for skip in sorted(skipped, key=lambda s: (s["chart_values"], s["path"])):
            print(f"  ○ {skip['chart_values']}: {skip['path']} - {skip['reason']}")
        print()

    print(f"Manifest covers all {len(current)} non-immutable tag field(s) "
          f"({len(manifest_keys)} pinned, {len(skipped_keys)} skipped). Applying pins"
          + (" (dry run - no files will be written):" if args.dry_run else ":"))

    pins_by_file: Dict[str, List[Dict[str, Any]]] = {}
    for pin in manifest["pins"]:
        pins_by_file.setdefault(pin["chart_values"], []).append(pin)

    ledger_entries: List[Dict[str, Any]] = []
    for chart_values, pins in sorted(pins_by_file.items()):
        # Order this file's pins the same way `_current_findings()` found
        # them (file/document order), regardless of manifest authoring
        # order.
        order = [f.path for f in current if f.chart_values == chart_values]
        ordered_pins = sorted(pins, key=lambda p: order.index(p["path"]))
        _apply_pins_to_file(chart_values, ordered_pins, order, args.dry_run)
        for pin in ordered_pins:
            ledger_entries.append(
                {
                    "chart_values": chart_values,
                    "path": pin["path"],
                    "tag": pin["tag"],
                    "digest": pin.get("digest"),
                }
            )

    if not args.dry_run:
        _update_ledger(manifest.get("release_tag"), ledger_entries, skipped)
        print(f"\nRESULT: PASS - pinned {len(ledger_entries)} field(s), skipped {len(skipped)}. "
              f"Ledger updated at {LEDGER_PATH.relative_to(REPO_ROOT)}. Run check_no_latest_tags.py "
              "to confirm (skipped fields will still show as non-immutable, as expected).")
    else:
        print(f"\nRESULT: PASS (dry run) - {len(manifest_keys)} field(s) would be pinned, "
              f"{len(skipped)} skipped; no files written.")
    return 0


def _update_ledger(release_tag: Any, entries: List[Dict[str, Any]], skipped: List[Dict[str, Any]]) -> None:
    ledger: Dict[str, Any] = {"releases": []}
    if LEDGER_PATH.exists():
        ledger = yaml.safe_load(LEDGER_PATH.read_text()) or {"releases": []}
    entry: Dict[str, Any] = {
        "release_tag": release_tag,
        "pinned_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pins": entries,
    }
    if skipped:
        entry["skipped"] = skipped
    ledger.setdefault("releases", []).append(entry)
    LEDGER_PATH.write_text(
        "# ADR-0115 release-pinning audit ledger - append-only, written by "
        "pin_release.py.\n# Each entry records one pin_release.py run: which "
        "chart values.yaml/path fields were\n# repointed to which immutable "
        "tag (and digest, when the release manifest supplied\n# one - see "
        "pin_release.py's own docstring for why the digest isn't also\n"
        "# embedded in values.yaml). This is evidence for ADR-0115's "
        "completion criterion\n# \"at least one real release proves source "
        "-> build -> SBOM -> scan -> signature\n# -> immutable GitOps "
        "reference -> deployment traceability\", not a mechanism consumed\n"
        "# by any deployment - never hand-edit.\n\n"
        + yaml.dump(ledger, sort_keys=False, default_flow_style=False)
    )


if __name__ == "__main__":
    sys.exit(main())
