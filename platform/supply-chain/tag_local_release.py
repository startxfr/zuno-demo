#!/usr/bin/env python3
"""ADR-0115 / WP-04 local-registry release tagging.

The operator's decision (2026-08-21): every `v*` tag still triggers
`.github/workflows/build-publish.yml`, which publishes signed, scanned,
SBOM-attested images to Quay - that pipeline is the supply-chain
provenance proof and is unchanged by this script. But deployment stays on
the in-cluster `zuno-ai-build` BuildConfig/ImageStream mechanism, which
only ever produces `:latest`. This script gives the *local* registry a
real immutable tag too, so `image.repository` never has to move to Quay
for `pin_release.py` (stage 3) to be safe: it rebuilds each component
in-cluster from the exact tagged commit and lands the result directly at
`<component>:<release_tag>` - never at `:latest`, which live pods pull
from and which `imagePullPolicy: Always` re-pulls on every restart.

How each component is retagged, in order, per component:

    1. Read the BuildConfig's current `spec.output.to.name` (must be
       `<component>:latest` - refuses to touch anything else).
    2. Patch `spec.output.to.name` to `<component>:<release_tag>`.
    3. `oc start-build <component> --commit=<release_tag> --wait` - builds
       from the exact tagged commit, output landing at the new tag, never
       at `:latest`.
    4. Patch `spec.output.to.name` back to `<component>:latest`,
       regardless of whether step 3 succeeded (a `finally`-equivalent) -
       `:latest` is never the build's output target during this whole
       operation, so live pods pulling `:latest` are undisturbed the
       entire time, even if a restart happens mid-run.

The only field with genuinely no in-cluster BuildConfig
(`rag-pipeline-compiler`, the chart's `images.compiler` field) is out of
scope - this script does not invent a build path for it; it stays on
`pin_release.py`'s (mothballed, see its own dated note) `skipped`
mechanism, and on `check_release_ledger.py`'s equivalent for the current
flow.

Note (2026-09-05, corrected): `mlops` was believed to have no
BuildConfig as of 2026-08-21 - that was wrong even at the time (see
ADR-0115's own 2026-08-22 correction note) and stayed wrong here until
now. `ansible/roles/mlops_build/tasks/build.yml` wires the identical
`apply_openshift_build.yml` mechanism every other component uses.
`diagram-render` (added by WP-102/ADR-0516, after this script's original
2026-08-21 component list was written) also has a real BuildConfig, via
`ansible/roles/mcp_build/tasks/build.yml`. Both are now in `COMPONENTS`.

Six chart values.yaml files (advantage, arkos, comage, finage, naveo,
tekos) share ONE `image.tag` field controlling both `frontendRepository`
(agent-frontend) and `bffRepository` (agent-bff) - both components are
retagged with the same release tag, and the single field is set once.

Modes:

    plan              (default) print the exact oc command sequence per
                       component; makes no cluster changes. Safe to run
                       anywhere, including without live cluster access.
    --apply            actually run the sequence against the live
                       cluster. Requires an authenticated `oc` session
                       with permission to patch BuildConfigs and start
                       builds in zuno-ai-build. Not invoked by this
                       repository's CI - an operator/session runs this by
                       hand at release time, same as build-publish.yml's
                       gap-7 credentialed run.
    --emit-manifest    read the *already-tagged* live ImageStreamTags
                       (no cluster mutation) and print a manifest in
                       pin_release.py's exact expected format
                       (chart_values/path/tag/digest). Historical -
                       pin_release.py is mothballed for the in-cluster
                       flow (ADR-0549); kept for the ADR-0353 scenario
                       its own docstring describes.
    --list-components   print COMPONENTS as a JSON list - lets
                       `ansible/playbooks/day3_release.yml` loop over
                       exactly this script's own component set instead of
                       duplicating it in YAML.
    --resolve-digests   read the *already-tagged* live ImageStreamTags
                       (no cluster mutation) and print `{component:
                       digest}` for every COMPONENTS entry; fails loudly
                       (non-zero exit, stderr) if any is unresolvable.
    --emit-verify-refs  same resolution as --resolve-digests, printed
                       instead as `[{"name", "repository", "digest"}, ...]`
                       - the exact shape `verify_signatures.py
                       --list-refs` also produces, so the same
                       `verify-images` Job mechanism
                       (`ansible/tasks/verify_image_signatures.yml`) can
                       verify a release's images too.
    --record-release    (ADR-0549/WP-134) read a `--refs-file` (JSON,
                       `{component: digest}` - exactly `--resolve-digests`'
                       own output shape) and append one entry to
                       `pinned-releases.yaml` via `release_ledger.py`.
                       Every pin is recorded `signed: true` - by the time
                       this mode runs, `day3_release.yml`'s signing loop
                       has already failed the whole play if any component
                       didn't sign successfully, so reaching this step at
                       all is the proof. Never touches any `values.yaml`.
                       This is the mode `make d3 release TAG=<tag>`
                       actually uses, last.

Run from the repository root:

    python3 platform/supply-chain/tag_local_release.py --release-tag v0.1.0
    python3 platform/supply-chain/tag_local_release.py --release-tag v0.1.0 --apply
    python3 platform/supply-chain/tag_local_release.py --release-tag v0.1.0 --resolve-digests
    python3 platform/supply-chain/tag_local_release.py --release-tag v0.1.0 --record-release --refs-file /tmp/v0.1.0-digests.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import release_ledger

NAMESPACE = "zuno-ai-build"

# Components with a real in-cluster BuildConfig/ImageStream. `mlops` and
# `diagram-render` added 2026-09-05 (ADR-0549) - both were wrongly absent
# (see the docstring's corrected note).
COMPONENTS = [
    "agent-bff",
    "agent-frontend",
    "agent-runtime",
    "ai-gateway",
    "aiagent-operator",
    "diagram-render",
    "mcp-aap",
    "mcp-confluence",
    "mcp-gateway",
    "mcp-git-forge",
    "mcp-salesforce",
    "mlops",
    "rag-ingestion",
    "rag-service",
]

# (chart_values, path) -> component name, or a tuple of component names
# when one field controls more than one image (the six agent-portal
# charts sharing agent-frontend + agent-bff).
CHART_FIELD_COMPONENT: Dict[Tuple[str, str], object] = {
    ("gitops/charts/agent-runtime/values.yaml", "image.tag"): "agent-runtime",
    ("gitops/charts/ai-gateway/values.yaml", "image.tag"): "ai-gateway",
    ("gitops/charts/aiagent-operator/values.yaml", "image.tag"): "aiagent-operator",
    ("gitops/charts/mcp-aap/values.yaml", "image.tag"): "mcp-aap",
    ("gitops/charts/mcp-confluence/values.yaml", "image.tag"): "mcp-confluence",
    ("gitops/charts/mcp-gateway/values.yaml", "image.tag"): "mcp-gateway",
    ("gitops/charts/mcp-git-forge/values.yaml", "image.tag"): "mcp-git-forge",
    ("gitops/charts/mcp-salesforce/values.yaml", "image.tag"): "mcp-salesforce",
    ("gitops/charts/diagram-render/values.yaml", "image.tag"): "diagram-render",
    ("gitops/charts/mlops/values.yaml", "images.mlops.tag"): "mlops",
    ("gitops/charts/rag-service/values.yaml", "image.tag"): "rag-service",
    ("gitops/charts/rag-ingestion/values.yaml", "images.ingestion.tag"): "rag-ingestion",
    ("gitops/charts/advantage/values.yaml", "image.tag"): ("agent-frontend", "agent-bff"),
    ("gitops/charts/arkos/values.yaml", "image.tag"): ("agent-frontend", "agent-bff"),
    ("gitops/charts/comage/values.yaml", "image.tag"): ("agent-frontend", "agent-bff"),
    ("gitops/charts/finage/values.yaml", "image.tag"): ("agent-frontend", "agent-bff"),
    ("gitops/charts/naveo/values.yaml", "image.tag"): ("agent-frontend", "agent-bff"),
    ("gitops/charts/tekos/values.yaml", "image.tag"): ("agent-frontend", "agent-bff"),
}

# Deliberately out of scope - no BuildConfig exists for this one field.
# (mlops was wrongly listed here until 2026-09-05 - see the docstring's
# corrected note; it's a real COMPONENTS entry now.)
NOT_LOCALLY_BUILDABLE = [
    ("gitops/charts/rag-ingestion/values.yaml", "images.compiler.tag",
     "rag-pipeline-compiler has no BuildConfig - unused by any template today per the chart's own comment"),
]


def _oc(args: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["oc", *args], capture_output=True, text=True)


def _run_or_die(args: List[str]) -> str:
    result = _oc(args)
    if result.returncode != 0:
        raise RuntimeError(f"oc {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def plan_commands(component: str, release_tag: str) -> List[str]:
    return [
        f"oc patch buildconfig {component} -n {NAMESPACE} --type=json "
        f"-p '[{{\"op\":\"replace\",\"path\":\"/spec/output/to/name\",\"value\":\"{component}:{release_tag}\"}}]'",
        f"oc start-build {component} -n {NAMESPACE} --commit={release_tag} --wait",
        f"oc patch buildconfig {component} -n {NAMESPACE} --type=json "
        f"-p '[{{\"op\":\"replace\",\"path\":\"/spec/output/to/name\",\"value\":\"{component}:latest\"}}]'",
    ]


def apply_component(component: str, release_tag: str) -> None:
    current = _run_or_die(["get", "buildconfig", component, "-n", NAMESPACE,
                            "-o", "jsonpath={.spec.output.to.name}"])
    expected = f"{component}:latest"
    if current != expected:
        raise RuntimeError(
            f"{component}: spec.output.to.name is {current!r}, expected {expected!r} - "
            "refusing to touch a BuildConfig whose output isn't the plain :latest target"
        )

    release_target = f"{component}:{release_tag}"
    patch_to = lambda name: _run_or_die([  # noqa: E731
        "patch", "buildconfig", component, "-n", NAMESPACE, "--type=json",
        "-p", json.dumps([{"op": "replace", "path": "/spec/output/to/name", "value": name}]),
    ])

    patch_to(release_target)
    try:
        result = _oc(["start-build", component, "-n", NAMESPACE, f"--commit={release_tag}", "--wait"])
        if result.returncode != 0:
            raise RuntimeError(f"{component}: build failed: {result.stderr.strip()}")
        print(f"  {component}: built {release_tag} -> {release_target}")
    finally:
        patch_to(expected)  # always revert, even if the build failed


def resolve_digest(component: str, tag: str) -> Optional[str]:
    result = _oc(["get", "imagestreamtag", f"{component}:{tag}", "-n", NAMESPACE,
                  "-o", "jsonpath={.image.metadata.name}"])
    return result.stdout.strip() or None


REGISTRY_PREFIX = "image-registry.openshift-image-registry.svc:5000/zuno-ai-build"


def resolve_all_digests(release_tag: str) -> Dict[str, Optional[str]]:
    return {component: resolve_digest(component, release_tag) for component in COMPONENTS}


def resolve_digests_mode(release_tag: str) -> int:
    digests = resolve_all_digests(release_tag)
    print(json.dumps(digests))
    missing = [c for c, d in digests.items() if not d]
    if missing:
        sys.stderr.write(
            f"RESULT: FAIL - no resolvable :{release_tag} ImageStreamTag for: {', '.join(sorted(missing))}\n"
        )
        return 1
    return 0


def emit_verify_refs_mode(release_tag: str) -> int:
    digests = resolve_all_digests(release_tag)
    missing = [c for c, d in digests.items() if not d]
    if missing:
        sys.stderr.write(
            f"RESULT: FAIL - no resolvable :{release_tag} ImageStreamTag for: {', '.join(sorted(missing))}\n"
        )
        return 1
    refs = [
        {"name": component, "repository": f"{REGISTRY_PREFIX}/{component}", "digest": digest}
        for component, digest in sorted(digests.items())
    ]
    print(json.dumps(refs))
    return 0


def record_release(release_tag: str, refs_path: str) -> int:
    with open(refs_path, encoding="utf-8") as fh:
        digests: Dict[str, str] = json.load(fh)

    missing_refs = [c for c in COMPONENTS if not digests.get(c)]
    if missing_refs:
        print(f"RESULT: FAIL - refs file {refs_path} is missing a digest for: {', '.join(sorted(missing_refs))}")
        return 1

    signed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pins: List[Dict[str, object]] = []
    for (chart_values, path), component in sorted(CHART_FIELD_COMPONENT.items()):
        components = component if isinstance(component, tuple) else (component,)
        # For fields shared by two components (agent-frontend + agent-bff),
        # the primary component's digest represents the pair - same
        # precedent --emit-manifest already used.
        pins.append({
            "chart_values": chart_values,
            "path": path,
            "tag": release_tag,
            "digest": digests[components[0]],
            "signed": True,
            "signed_at": signed_at,
        })

    skipped = [
        {"chart_values": chart_values, "path": path, "reason": reason}
        for chart_values, path, reason in NOT_LOCALLY_BUILDABLE
    ]

    release_ledger.append_entry(release_tag, pins, skipped)
    print(f"RESULT: PASS - recorded release {release_tag}: {len(pins)} pin(s), {len(skipped)} skipped. "
          f"Ledger updated at {release_ledger.LEDGER_PATH.relative_to(release_ledger.REPO_ROOT)}. "
          "No values.yaml or targetRevision was touched.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--release-tag", help="release tag to build from and land at, e.g. v0.1.0 (not needed with --list-components)")
    parser.add_argument("--apply", action="store_true", help="actually mutate the cluster (default: print the plan)")
    parser.add_argument("--emit-manifest", action="store_true",
                         help="read already-tagged live ImageStreamTags and print a pin_release.py manifest")
    parser.add_argument("--list-components", action="store_true",
                         help="print COMPONENTS as a JSON list (no cluster access, ignores --release-tag)")
    parser.add_argument("--resolve-digests", action="store_true",
                         help="print {component: digest} for every COMPONENTS entry at --release-tag")
    parser.add_argument("--emit-verify-refs", action="store_true",
                         help="print [{name, repository, digest}, ...] for verify_image_signatures.yml's Job")
    parser.add_argument("--record-release", action="store_true",
                         help="append a ledger entry from --refs-file (ADR-0549) - no cluster access, no values.yaml edits")
    parser.add_argument("--refs-file", help="JSON {component: digest} (== --resolve-digests' output) - required with --record-release")
    args = parser.parse_args()

    if args.list_components:
        print(json.dumps(COMPONENTS))
        return 0

    if not args.release_tag:
        print("RESULT: FAIL - --release-tag is required (except with --list-components)")
        return 1

    if args.resolve_digests:
        return resolve_digests_mode(args.release_tag)

    if args.emit_verify_refs:
        return emit_verify_refs_mode(args.release_tag)

    if args.record_release:
        if not args.refs_file:
            print("RESULT: FAIL - --record-release requires --refs-file")
            return 1
        return record_release(args.release_tag, args.refs_file)

    if args.emit_manifest:
        print(f"release_tag: {args.release_tag}")
        print("pins:")
        for (chart_values, path), component in sorted(CHART_FIELD_COMPONENT.items()):
            components = component if isinstance(component, tuple) else (component,)
            digest = resolve_digest(components[0], args.release_tag)
            print(f"  - chart_values: {chart_values}")
            print(f"    path: {path}")
            print(f"    tag: {args.release_tag}")
            if digest:
                print(f"    digest: {digest}")
        print("skipped:")
        for chart_values, path, reason in NOT_LOCALLY_BUILDABLE:
            print(f"  - chart_values: {chart_values}")
            print(f"    path: {path}")
            print(f"    reason: >-")
            print(f"      {reason}")
        return 0

    if args.apply:
        for component in COMPONENTS:
            apply_component(component, args.release_tag)
        print(f"\nDone - {len(COMPONENTS)} component(s) now have a local :{args.release_tag} tag, "
              ":latest untouched throughout. Next: re-run with --emit-manifest, then feed the "
              "result to pin_release.py.")
        return 0

    print(f"Plan for release tag {args.release_tag} ({len(COMPONENTS)} component(s)), "
          ":latest is never the build output at any point:\n")
    for component in COMPONENTS:
        print(f"# {component}")
        for cmd in plan_commands(component, args.release_tag):
            print(f"  {cmd}")
        print()
    print("Run with --apply to execute, or --emit-manifest after tagging to produce "
          "pin_release.py's input.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
