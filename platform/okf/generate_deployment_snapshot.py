#!/usr/bin/env python3
"""ADR-0503 (roadmap WP-45) per-agent deployment snapshot generator.

Fills agents/<name>/deployment/ with a generated, validated mirror of
the agent's real deployment surface, replacing the historical one-line
stub READMEs. gitops/ remains the sole applied source (ADR-0022) - the
snapshot follows the chart, never the reverse; drift fails CI via
--check.

Two output shapes, auto-detected from `helm template gitops/charts/<n>`:
  - CR-managed chart (renders a zuno.zuno.ai AIAgent document, e.g.
    arkos): deployment/aiagent-snapshot.yaml - the CR spec verbatim,
    with a generated-file header.
  - raw-manifest chart (tekos, comage, advantage, finage):
    deployment/manifest-summary.md - every rendered object's kind/name,
    with container images for Deployments.

Scope: agents that have BOTH a deployment/ directory (the Stage-2 /
reserved-structure shapes, ADR-0502) and a chart. Naveo is CR-managed
but Stage-1 (no deployment/ directory) - deliberately skipped; its
directory is born at promotion (PROMOTION.md step 4).

Usage (from the repository root; needs `helm` on PATH):

    python3 platform/okf/generate_deployment_snapshot.py           # regenerate
    python3 platform/okf/generate_deployment_snapshot.py --check   # CI drift gate
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
from typing import Dict, List, Tuple

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "agents"
CHARTS_DIR = REPO_ROOT / "gitops" / "charts"

REGEN_CMD = "python3 platform/okf/generate_deployment_snapshot.py"

# Tekos's chart is deployed by the legacy-named zuno-api Application pair
# (gitops/apps/api - "api" predates the per-agent naming convention).
APP_DIR_OVERRIDES = {"tekos": "api"}


def _helm_template(name: str) -> List[Dict]:
    chart = CHARTS_DIR / name
    result = subprocess.run(
        ["helm", "template", f"zuno-{name}-d1", str(chart)],
        capture_output=True, text=True, check=True,
    )
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def _render_cr_snapshot(name: str, cr: Dict) -> str:
    header = (
        f"# GENERATED FILE (ADR-0503/WP-45) - do not edit.\n"
        f"# Source: helm template gitops/charts/{name} (the AIAgent CR the\n"
        f"# aiagent-operator reconciles, ADR-0327/ADR-0308). Regenerate with:\n"
        f"#   {REGEN_CMD}\n"
    )
    return header + yaml.safe_dump(cr, sort_keys=False)


def _render_manifest_summary(name: str, docs: List[Dict]) -> str:
    lines = [
        f"<!-- GENERATED FILE (ADR-0503/WP-45) - do not edit. Source: helm",
        f"template gitops/charts/{name}. Regenerate with: {REGEN_CMD} -->",
        "",
        f"# {name.capitalize()} rendered deployment surface",
        "",
        f"Every object `gitops/charts/{name}` renders (raw-manifest chart - "
        f"not CR-managed; see `README.md` in this directory for what that "
        f"means for this agent):",
        "",
        "| Kind | Name | Container images |",
        "|---|---|---|",
    ]
    for doc in docs:
        kind = doc.get("kind", "?")
        obj_name = (doc.get("metadata") or {}).get("name", "?")
        images = []
        if kind == "Deployment":
            containers = (((doc.get("spec") or {}).get("template") or {})
                          .get("spec") or {}).get("containers") or []
            images = [c.get("image", "?") for c in containers]
        lines.append(f"| {kind} | `{obj_name}` | {', '.join(f'`{i}`' for i in images) or '—'} |")
    lines.append("")
    return "\n".join(lines)


def _expected_files(name: str) -> Dict[pathlib.Path, str]:
    docs = _helm_template(name)
    deployment_dir = AGENTS_DIR / name / "deployment"
    cr_docs = [d for d in docs if d.get("kind") == "AIAgent"]
    if cr_docs:
        return {deployment_dir / "aiagent-snapshot.yaml": _render_cr_snapshot(name, cr_docs[0])}
    return {deployment_dir / "manifest-summary.md": _render_manifest_summary(name, docs)}


def _target_agents() -> List[str]:
    return sorted(
        p.name for p in AGENTS_DIR.iterdir()
        if (p / "deployment").is_dir() and (CHARTS_DIR / p.name).is_dir()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-0503 deployment snapshot generator")
    parser.add_argument("--check", action="store_true",
                        help="verify committed snapshots match regeneration; never writes")
    args = parser.parse_args()

    failures: List[str] = []
    written: List[str] = []
    for name in _target_agents():
        for path, expected in _expected_files(name).items():
            rel = path.relative_to(REPO_ROOT)
            current = path.read_text(encoding="utf-8") if path.is_file() else None
            if args.check:
                if current != expected:
                    failures.append(f"{rel}: {'missing' if current is None else 'differs from regeneration'}")
                continue
            if current != expected:
                path.write_text(expected, encoding="utf-8")
                written.append(str(rel))

    if args.check:
        if failures:
            print(f"{len(failures)} deployment-snapshot drift issue(s):")
            for f in failures:
                print(f"  ✗ {f} (run: {REGEN_CMD})")
            print("\nRESULT: FAIL - snapshots must match the chart (ADR-0503).")
            return 1
        print("RESULT: PASS - every committed deployment snapshot matches its chart.")
        return 0

    print(f"Regenerated {len(written)} snapshot file(s): {', '.join(written) or '(none - all current)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
