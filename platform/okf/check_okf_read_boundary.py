#!/usr/bin/env python3
"""OKF read boundary lint (ADR-0508 clause 2, WP-51).

OKF bundles are parsed by per-component hooks, never ad hoc. This grep-level
check finds code that names a bundle file as a string literal
(`"agent.okf.md"`, `"okf-index.json"`, a `"tasks" / ...` path) under
components/, platform/ and evaluations/ and fails when the file is neither a
hook nor on the explicit baseline below.

HOOKS are the designated readers. BASELINE is the reads that predate the
check: each is a known gap to migrate into a hook or retire, and the list may
only shrink. A new file reading OKF directly fails here; adding it to
BASELINE needs a reason a reviewer accepts.

Run from the repository root:
    python3 platform/okf/check_okf_read_boundary.py
"""
from __future__ import annotations

import pathlib
import re
import sys
from typing import Dict, Iterable, List

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCAN_DIRS = ("components", "platform", "evaluations")
SUFFIXES = {".py", ".go"}
READ = re.compile(r"""agent\.okf\.md["']|okf-index\.json["']|["']tasks["']\s*/\s*f?["']""")

HOOKS: Dict[str, str] = {
    "components/mcp-gateway/app/agent_declarations.py": "mcp-gateway hook",
    "platform/supply-chain/admit_okf_bundle.py": "admission hook (agents_view)",
    "platform/supply-chain/okf_narrowing.py": "admission hook (v0.3 narrowing rule)",
    "platform/okf/generate_stack_config.py": "ADR-0581 generator hook",
    "platform/okf/release_cache.py": "release access point",
    "components/mlops/src/mlops.py": "mlops hook (_task_system_prompt)",
}

BASELINE: Dict[str, str] = {
    "evaluations/tekos/gate_checks.py": "reads agent frontmatter for a gate; move behind the evaluations reader",
    "evaluations/tekos/run_scenarios.py": "reads agent frontmatter; move behind the evaluations reader",
    "platform/docs/check_docs.py": "documentation drift checks read the admitted release",
    "platform/testing/day2_contract_attribution.py": "reads okf-index.json for attribution",
}


def _sources() -> Iterable[pathlib.Path]:
    for name in SCAN_DIRS:
        for path in sorted((REPO_ROOT / name).rglob("*")):
            if path.suffix in SUFFIXES and path.is_file() and "tests" not in path.relative_to(REPO_ROOT).parts \
                    and ".cache" not in path.parts and path.name != pathlib.Path(__file__).name \
                    and not path.name.startswith("test_"):
                yield path


def find_reads(paths: Iterable[pathlib.Path], root: pathlib.Path = REPO_ROOT) -> Dict[str, List[int]]:
    found: Dict[str, List[int]] = {}
    for path in paths:
        lines = [n for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
                 if READ.search(line) and not line.lstrip().startswith(("#", "//"))]
        if lines:
            found[path.relative_to(root).as_posix()] = lines
    return found


def violations(found: Dict[str, List[int]]) -> List[str]:
    out = [f"{rel}:{lines[0]}: reads OKF outside a hook; use the component's hook or add a reasoned BASELINE entry"
           for rel, lines in sorted(found.items()) if rel not in HOOKS and rel not in BASELINE]
    out += [f"{rel}: listed in BASELINE but no longer reads OKF directly; remove it from the list"
            for rel in sorted(BASELINE) if rel not in found]
    out += [f"{rel}: listed in HOOKS but does not exist or no longer reads OKF"
            for rel in sorted(HOOKS) if rel not in found]
    return out


def main() -> int:
    findings = violations(find_reads(_sources()))
    print(f"Scanned {', '.join(SCAN_DIRS)} for direct OKF bundle reads "
          f"({len(HOOKS)} hooks, {len(BASELINE)} baseline).")
    for finding in findings:
        print(f"  ✗ {finding}")
    print("RESULT: " + ("FAIL" if findings else "PASS - OKF reads stay within the hooks and the baseline."))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
