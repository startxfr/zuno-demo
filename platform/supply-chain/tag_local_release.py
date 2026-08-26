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

Components without an in-cluster BuildConfig (confirmed live 2026-08-21:
`mlops` has none at all; `rag-pipeline-compiler`, the chart's `images.
compiler` field, has never been wired to one) are out of scope - this
script does not invent a build path for them; they stay on `pin_release.
py`'s existing `skipped` mechanism.

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
                       (chart_values/path/tag/digest), ready to feed
                       straight into `pin_release.py --manifest <path>`.

Run from the repository root:

    python3 platform/supply-chain/tag_local_release.py --release-tag v0.1.0
    python3 platform/supply-chain/tag_local_release.py --release-tag v0.1.0 --apply
    python3 platform/supply-chain/tag_local_release.py --release-tag v0.1.0 --emit-manifest > /tmp/local-v0.1.0-manifest.yaml
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

NAMESPACE = "zuno-ai-build"

# Components with a real in-cluster BuildConfig/ImageStream, confirmed
# live 2026-08-21 (`oc get buildconfig -n zuno-ai-build`).
COMPONENTS = [
    "agent-bff",
    "agent-frontend",
    "agent-runtime",
    "ai-gateway",
    "aiagent-operator",
    "mcp-confluence",
    "mcp-gateway",
    "mcp-git-forge",
    "mcp-salesforce",
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
    ("gitops/charts/mcp-confluence/values.yaml", "image.tag"): "mcp-confluence",
    ("gitops/charts/mcp-gateway/values.yaml", "image.tag"): "mcp-gateway",
    ("gitops/charts/mcp-git-forge/values.yaml", "image.tag"): "mcp-git-forge",
    ("gitops/charts/mcp-salesforce/values.yaml", "image.tag"): "mcp-salesforce",
    ("gitops/charts/rag-service/values.yaml", "image.tag"): "rag-service",
    ("gitops/charts/rag-ingestion/values.yaml", "images.ingestion.tag"): "rag-ingestion",
    ("gitops/charts/advantage/values.yaml", "image.tag"): ("agent-frontend", "agent-bff"),
    ("gitops/charts/arkos/values.yaml", "image.tag"): ("agent-frontend", "agent-bff"),
    ("gitops/charts/comage/values.yaml", "image.tag"): ("agent-frontend", "agent-bff"),
    ("gitops/charts/finage/values.yaml", "image.tag"): ("agent-frontend", "agent-bff"),
    ("gitops/charts/naveo/values.yaml", "image.tag"): ("agent-frontend", "agent-bff"),
    ("gitops/charts/tekos/values.yaml", "image.tag"): ("agent-frontend", "agent-bff"),
}

# Deliberately out of scope - no BuildConfig exists for either, confirmed
# live 2026-08-21. Left for pin_release.py's own `skipped` mechanism.
NOT_LOCALLY_BUILDABLE = [
    ("gitops/charts/mlops/values.yaml", "images.mlops.tag",
     "no in-cluster BuildConfig/ImageStream exists for mlops at all - a separate, pre-existing gap"),
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--release-tag", required=True, help="release tag to build from and land at, e.g. v0.1.0")
    parser.add_argument("--apply", action="store_true", help="actually mutate the cluster (default: print the plan)")
    parser.add_argument("--emit-manifest", action="store_true",
                         help="read already-tagged live ImageStreamTags and print a pin_release.py manifest")
    args = parser.parse_args()

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
