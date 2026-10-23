#!/usr/bin/env python3
"""The frozen mirror: zuno-demo's agents/ must match the admitted release (ADR-0576 clause 6, WP-158).

Until the cutover (WP-165), agents and their corp policies are edited in
startxfr/zuno-demo-agents only; zuno-demo keeps a copy because components
still bake it into images. This check fails when that copy says something
the admitted release (platform/okf/agents.lock) does not:

- every runtime file of every agent (tasks/, prompts/, skills/, tools/,
  rag/, policies/; never README.md) is byte-identical;
- agent.okf.md has the same frontmatter (its body is the generated
  authorization matrix, documentation only, which the agents repository
  regenerates from its own catalog);
- the corp policy files the release carries are byte-identical, for those
  zuno-demo still has.

The copy is not rewritten here: agent-runtime verifies a Transit signature
over every file of a bundle at start (ADR-0106/0420), so changing it means
re-signing; a divergence is reported, and fixed by a reviewed sync plus
`make d3 sign agents`.

Run from the repository root (needs cosign and oras, as admission does):
    python3 platform/okf/check_agents_mirror.py
    python3 platform/okf/check_agents_mirror.py --release-dir DIR
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import tempfile
from typing import List, Optional

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "platform" / "supply-chain"))

import admit_okf_bundle as admit  # noqa: E402

RUNTIME_DIRS = ("tasks", "prompts", "skills", "tools", "rag", "policies")


def runtime_files(agent_dir: pathlib.Path) -> List[str]:
    out = []
    for name in RUNTIME_DIRS:
        root = agent_dir / name
        if root.is_dir():
            out += [p.relative_to(agent_dir).as_posix() for p in root.rglob("*")
                    if p.is_file() and p.name != "README.md"]
    return sorted(out)


def compare(release: pathlib.Path, local_root: pathlib.Path = REPO_ROOT) -> List[str]:
    problems: List[str] = []
    local_agents = local_root / "agents"
    released = sorted(p.parent.name for p in (release / "agents").glob("*/agent.okf.md"))
    present = sorted(p.parent.name for p in local_agents.glob("*/agent.okf.md"))
    for name in sorted(set(released) - set(present)):
        problems.append(f"agents/{name}: in the release, missing here")
    for name in sorted(set(present) - set(released)):
        problems.append(f"agents/{name}: here, not in the release (agents are added in zuno-demo-agents)")
    for name in sorted(set(released) & set(present)):
        mine, theirs = local_agents / name, release / "agents" / name
        if admit.frontmatter(mine / "agent.okf.md") != admit.frontmatter(theirs / "agent.okf.md"):
            problems.append(f"agents/{name}/agent.okf.md: frontmatter differs from the release")
        a, b = runtime_files(mine), runtime_files(theirs)
        for rel in sorted(set(a) - set(b)):
            problems.append(f"agents/{name}/{rel}: here, not in the release")
        for rel in sorted(set(b) - set(a)):
            problems.append(f"agents/{name}/{rel}: in the release, missing here")
        for rel in sorted(set(a) & set(b)):
            if (mine / rel).read_bytes() != (theirs / rel).read_bytes():
                problems.append(f"agents/{name}/{rel}: differs from the release")
    for path in sorted(p for p in (release / "policies").rglob("*") if p.is_file()):
        rel = path.relative_to(release).as_posix()
        local = local_root / rel
        if local.is_file() and local.read_bytes() != path.read_bytes():
            problems.append(f"{rel}: differs from the release")
    return problems


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--release-dir", type=pathlib.Path, help="an already extracted release")
    args = parser.parse_args(argv)
    try:
        if args.release_dir:
            problems = compare(args.release_dir)
        else:
            reference = admit.read_lock()
            if reference is None:
                print("RESULT: PASS - no release pinned yet, nothing to mirror.")
                return 0
            with tempfile.TemporaryDirectory() as tmp:
                admit.extract(reference, pathlib.Path(tmp))
                problems = compare(pathlib.Path(tmp))
    except admit.AdmissionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if problems:
        print(f"{len(problems)} divergence(s) between agents/ and the admitted release:")
        for p in problems:
            print(f"  ✗ {p}")
        print("\nRESULT: FAIL - agents are edited in startxfr/zuno-demo-agents only (ADR-0576 clause 6).")
        return 1
    print("RESULT: PASS - agents/ mirrors the admitted release.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
