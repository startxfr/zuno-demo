#!/usr/bin/env python3
"""ADR-0324 policy-as-code check: "Reconcile the CI build inventory with
the repository component lifecycle." Validates
`.github/workflows/build-publish.yml`'s build matrix against the
repository's actual `components/**/Dockerfile` inventory, without needing
registry credentials or a live cluster - the ADR's Operational
considerations require this preflight to fail fast on a PR, before any
image build/publish/SBOM/scan/sign step (governed separately by
ADR-0115) even starts.

Two failure modes:
  - a matrix entry's `dockerfile`/`context` path doesn't exist, its
    `name` collides with another entry, or it doesn't correspond to any
    tracked first-party Dockerfile (a stale/removed-component entry -
    exactly the `postgresql-pgvector` bug this ADR fixes: Postgres is
    now a Crunchy PGO-managed operand, not a first-party built image);
  - a first-party `components/**/Dockerfile` exists but has no matrix
    entry at all (a build artifact silently missing from the inventory).

ADR-0119 (WP-057): `components/mcp-servers/*/Dockerfile` is deliberately
excluded from the second check above - those are built by the
`discover-mcp-servers`/`build-publish-sign-mcp-servers` job pair instead
of a hand-listed matrix entry (every MCP server shares the same
context/build_args shape). This script instead verifies that discovery
job still actually targets `components/mcp-servers`, so the exclusion
can't quietly turn into a real silent gap if that job is ever edited
away.

Run from the repository root:

    python3 platform/supply-chain/check_build_matrix.py
"""
from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass
from typing import Any, List

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "build-publish.yml"
MATRIX_JOB = "build-publish-sign"
MCP_DISCOVERY_JOB = "discover-mcp-servers"
MCP_MATRIX_JOB = "build-publish-sign-mcp-servers"
MCP_SERVERS_DIR = "components/mcp-servers"


@dataclass
class Finding:
    message: str


def _load_workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text())


def _load_matrix_entries(doc: dict) -> List[dict]:
    job = doc["jobs"][MATRIX_JOB]
    return job["strategy"]["matrix"]["include"]


def _check_matrix_entries(entries: List[dict]) -> List[Finding]:
    findings: List[Finding] = []
    seen_names: dict[str, int] = {}

    for entry in entries:
        name = entry.get("name", "<unnamed>")
        seen_names[name] = seen_names.get(name, 0) + 1

        dockerfile = REPO_ROOT / entry["dockerfile"]
        if not dockerfile.is_file():
            findings.append(
                Finding(f"{name}: dockerfile '{entry['dockerfile']}' does not exist")
            )

        context = REPO_ROOT / entry["context"]
        if not context.is_dir():
            findings.append(
                Finding(f"{name}: context '{entry['context']}' is not a directory")
            )

    for name, count in seen_names.items():
        if count > 1:
            findings.append(Finding(f"{name}: appears {count} times in the matrix (must be unique)"))

    return findings


def _check_orphaned_dockerfiles(entries: List[dict]) -> List[Finding]:
    matrix_dockerfiles = {
        pathlib.Path(entry["dockerfile"]).resolve() for entry in entries
    }
    actual_dockerfiles = (REPO_ROOT / "components").glob("**/Dockerfile")
    mcp_servers_dir = (REPO_ROOT / MCP_SERVERS_DIR).resolve()

    findings: List[Finding] = []
    for dockerfile in actual_dockerfiles:
        resolved = dockerfile.resolve()
        if mcp_servers_dir in resolved.parents:
            continue  # covered by discover-mcp-servers instead - see _check_mcp_discovery_job
        if resolved not in matrix_dockerfiles:
            rel = dockerfile.relative_to(REPO_ROOT)
            findings.append(
                Finding(
                    f"'{rel}' is a first-party Dockerfile with no matching "
                    "entry in the build-publish.yml matrix"
                )
            )
    return findings


def _check_mcp_discovery_job(doc: dict) -> List[Finding]:
    findings: List[Finding] = []
    jobs = doc.get("jobs", {})

    discovery = jobs.get(MCP_DISCOVERY_JOB)
    if discovery is None:
        findings.append(Finding(f"workflow has no '{MCP_DISCOVERY_JOB}' job (ADR-0119)"))
    else:
        run_steps = " ".join(step.get("run", "") for step in discovery.get("steps", []))
        if MCP_SERVERS_DIR not in run_steps:
            findings.append(
                Finding(
                    f"'{MCP_DISCOVERY_JOB}' job no longer discovers '{MCP_SERVERS_DIR}' - "
                    "components/mcp-servers/*/Dockerfile would silently stop being built"
                )
            )

    consumer = jobs.get(MCP_MATRIX_JOB)
    if consumer is None:
        findings.append(Finding(f"workflow has no '{MCP_MATRIX_JOB}' job (ADR-0119)"))
    else:
        matrix_name = (
            consumer.get("strategy", {}).get("matrix", {}).get("name", "")
        )
        if f"needs.{MCP_DISCOVERY_JOB}.outputs.servers" not in str(matrix_name):
            findings.append(
                Finding(
                    f"'{MCP_MATRIX_JOB}' job's matrix no longer consumes "
                    f"'{MCP_DISCOVERY_JOB}' outputs"
                )
            )

    return findings


def main() -> int:
    doc = _load_workflow()
    entries = _load_matrix_entries(doc)
    findings = (
        _check_matrix_entries(entries)
        + _check_orphaned_dockerfiles(entries)
        + _check_mcp_discovery_job(doc)
    )

    print(f"Checked {len(entries)} build-matrix entries against {WORKFLOW_PATH.relative_to(REPO_ROOT)}.")
    if not findings:
        print("\nRESULT: PASS - every matrix entry is valid and every first-party Dockerfile is tracked.")
        return 0

    print(f"\n{len(findings)} build-inventory issue(s) found:")
    for f in findings:
        print(f"  ✗ {f.message}")
    print(
        "\nRESULT: FAIL - fix the build matrix (ADR-0324): remove stale/"
        "non-buildable entries, add missing first-party components, or "
        "correct the broken path/name."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
