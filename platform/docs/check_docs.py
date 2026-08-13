#!/usr/bin/env python3
"""ADR-0323 policy-as-code check: "Establish canonical generated and
validated platform documentation." Validates that curated documentation
doesn't contradict the two levels ADR-0323 puts above it: ADRs (status/
title/index) and executable configuration (the Makefile's actual verb/
component contract, `platform_profile.yaml`'s declared version intent).
No live cluster or registry needed - pure static text/YAML inspection,
same style as `platform/supply-chain/check_build_matrix.py`.

Four checks, each independent (a failure in one doesn't block the others
from reporting):
  - make_commands: every literal `make day0|d0|day1|d1 ...` example in
    README.md uses a verb/component this repository's actual Makefile
    accepts;
  - adr_index: every docs/adr/NNNN-*.md file has a docs/adr/README.md
    index row, and that row's status matches the ADR's own `**Status:**`
    field (catches stale statuses, e.g. an ADR quietly downgraded to
    "Partially implemented" without its index row following);
  - day0_day1_roles: every Makefile DAY0_COMPONENTS/DAY1_RUN_COMPONENTS/
    DAY1_BUILD_COMPONENTS entry has a matching ansible/roles/<name> role;
  - version_consistency: README.md/MEMORY.md/docs/architecture/*.md/
    docs/platform/*.md/platform/*/README.md don't state an OpenShift or
    OpenShift AI version other than platform_profile.yaml's declared
    target/release train (ADR bodies are immutable and excluded; RAG
    fixture/test data is excluded - those are demo content, not platform
    documentation).

Run from the repository root:

    python3 platform/docs/check_docs.py
"""
from __future__ import annotations

import pathlib
import re
import sys
from dataclasses import dataclass
from typing import List

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "platform" / "docs" / "platform_profile.yaml"
MAKEFILE_PATH = REPO_ROOT / "Makefile"
README_PATH = REPO_ROOT / "README.md"
ADR_DIR = REPO_ROOT / "docs" / "adr"
ADR_README_PATH = ADR_DIR / "README.md"

# Documentation prose scanned for version consistency - deliberately not
# every *.md in the repo: ADR bodies are immutable historical records
# (excluded outright), and RAG fixture/test data contains arbitrary demo
# version strings that are content, not platform documentation.
VERSION_SCAN_FILES = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "MEMORY.md",
    REPO_ROOT / "docs" / "architecture" / "physical-architecture.md",
    REPO_ROOT / "docs" / "architecture" / "ai-architecture.md",
    REPO_ROOT / "docs" / "platform" / "prerequisites.md",
    REPO_ROOT / "platform" / "openshift-ai" / "README.md",
]

BACKTICK_SPAN_RE = re.compile(r"```(.*?)```|`([^`\n]+)`", re.DOTALL)
# [ \t]+, not \s+: must not cross a newline, or the optional trailing
# group can capture the *next* line's leading word (e.g. another "make").
MAKE_COMMAND_RE = re.compile(r"\bmake[ \t]+(d0|d1)[ \t]+(\S+)(?:[ \t]+(\S+))?")
OPENSHIFT_VERSION_RE = re.compile(r"OpenShift(?: Container Platform)? (\d+\.\d+)\b")
OPENSHIFT_AI_VERSION_RE = re.compile(r"OpenShift AI (\d+\.\d+(?: EA\d)?)\b")

# Roadmap container files (0100/0200/0300/0400) hold embedded/promoted
# ADR-0101.. / ADR-0201.. / ADR-0301.. / ADR-0401.. entries, each
# individually indexed via its own row or an anchor link into the
# container - the container file itself is not a numbered ADR and has no
# row of its own, by docs/adr/README.md's own convention (see its
# ADR-0101.. rows).
ADR_INDEX_EXCLUDED_FILES = {
    "0100-v1-roadmap.md",
    "0200-v2-roadmap.md",
    "0300-v3-roadmap.md",
    "0400-v4-roadmap.md",
}


@dataclass
class Finding:
    check: str
    message: str


def _load_profile() -> dict:
    return yaml.safe_load(PROFILE_PATH.read_text())


def _parse_makefile_lists() -> dict:
    text = MAKEFILE_PATH.read_text()
    lists = {}
    for name in ("DAY0_VERBS", "DAY0_COMPONENTS", "DAY1_VERBS", "DAY1_RUN_COMPONENTS", "DAY1_BUILD_COMPONENTS"):
        match = re.search(rf"^{name}\s*:=\s*(.*)$", text, re.MULTILINE)
        lists[name] = match.group(1).split() if match else []
    return lists


def check_make_commands() -> List[Finding]:
    findings: List[Finding] = []
    lists = _parse_makefile_lists()
    text = README_PATH.read_text()
    # Normalize the "day0|d0"/"day1|d1" alternation notation prose uses
    # for "either name dispatches identically" into a single literal form.
    text = text.replace("day0|d0", "d0").replace("day1|d1", "d1")

    for block, inline in BACKTICK_SPAN_RE.findall(text):
        span = block or inline
        for day, verb, component in MAKE_COMMAND_RE.findall(span):
            component = (component or "").split("#", 1)[0].strip().rstrip("`")
            verbs = lists["DAY0_VERBS"] if day == "d0" else lists["DAY1_VERBS"]
            if verb not in verbs:
                findings.append(Finding(
                    "make_commands",
                    f"README.md example 'make {day} {verb}' uses an unsupported verb "
                    f"(expected one of: {' '.join(verbs)})",
                ))
                continue
            if not component:
                continue
            if day == "d0":
                components = lists["DAY0_COMPONENTS"]
            elif verb == "build":
                components = lists["DAY1_BUILD_COMPONENTS"]
            else:
                components = lists["DAY1_RUN_COMPONENTS"]
            if component not in components and component != "all":
                findings.append(Finding(
                    "make_commands",
                    f"README.md example 'make {day} {verb} {component}' uses an "
                    f"unsupported component (expected one of: {' '.join(components)} or all)",
                ))
    return findings


def check_adr_index() -> List[Finding]:
    findings: List[Finding] = []
    index_text = ADR_README_PATH.read_text()

    for adr_path in sorted(ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md")):
        if adr_path.name in ADR_INDEX_EXCLUDED_FILES:
            continue
        adr_number = adr_path.name[:4]
        row_match = re.search(rf"\[ADR-{adr_number}\]\({re.escape(adr_path.name)}\)[^\n]*", index_text)
        if not row_match:
            findings.append(Finding("adr_index", f"ADR-{adr_number} ({adr_path.name}) has no docs/adr/README.md index row linking directly to it"))
            continue

        body = adr_path.read_text()
        status_match = re.search(r"\*\*Status:\*\*\s*(.+)", body)
        if not status_match:
            continue
        # Strip a trailing parenthetical explanation (e.g. ADR-0055's
        # "Implemented (statuses below are tracked live in README.md...)")
        # before comparing - only the status word/phrase itself must
        # match, not any elaboration appended to it.
        body_status = status_match.group(1).split("(")[0].strip()

        row_cells = [c.strip() for c in row_match.group(0).split("|")]
        # row_match captures from the link onward: "[ADR-NNNN](file.md) | Target | Status | Decision"
        if len(row_cells) < 3:
            continue
        row_status = row_cells[2]
        if row_status != body_status:
            findings.append(Finding(
                "adr_index",
                f"ADR-{adr_number} status drift: docs/adr/README.md index says "
                f"'{row_status}', the ADR's own body says '{body_status}'",
            ))
    return findings


def check_day0_day1_roles() -> List[Finding]:
    findings: List[Finding] = []
    lists = _parse_makefile_lists()
    roles_dir = REPO_ROOT / "ansible" / "roles"
    existing_roles = {p.name for p in roles_dir.iterdir() if p.is_dir()}

    for component_list in ("DAY0_COMPONENTS", "DAY1_RUN_COMPONENTS", "DAY1_BUILD_COMPONENTS"):
        for component in lists[component_list]:
            role_name = component.replace("-", "_")
            # DAY1_BUILD_COMPONENTS roles are suffixed "_build" (mcp ->
            # mcp_build, ai-gateway -> ai_gateway_build) to distinguish
            # them from same-named DAY1_RUN_COMPONENTS roles (e.g. "mcp"
            # itself is also a run component with its own role).
            if component_list == "DAY1_BUILD_COMPONENTS":
                role_name += "_build"
            if role_name not in existing_roles:
                findings.append(Finding(
                    "day0_day1_roles",
                    f"Makefile {component_list} lists '{component}' but no "
                    f"ansible/roles/{role_name} directory exists",
                ))
    return findings


def check_version_consistency(profile: dict) -> List[Finding]:
    findings: List[Finding] = []
    target = profile["openshift"]["target"]
    release_train = profile["openshift_ai"]["release_train"]

    for path in VERSION_SCAN_FILES:
        if not path.is_file():
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            # Skip lines listing multiple doc-reference versions
            # (e.g. "official docs for 4.20, 4.21 and 4.22") - a
            # reference-material list, not a target-version claim.
            if len(OPENSHIFT_VERSION_RE.findall(line)) > 1:
                continue
            for found in OPENSHIFT_VERSION_RE.findall(line):
                if found != target:
                    findings.append(Finding(
                        "version_consistency",
                        f"{path.relative_to(REPO_ROOT)}:{lineno}: states OpenShift "
                        f"{found}, platform_profile.yaml declares {target}",
                    ))
            for found in OPENSHIFT_AI_VERSION_RE.findall(line):
                # A bare "3.5" is a legitimate shorthand for "3.5 EA2" in
                # headings/prose, not a contradiction - only flag a
                # genuinely different release (e.g. "3.4", "2.19").
                if found != release_train and not release_train.startswith(found):
                    findings.append(Finding(
                        "version_consistency",
                        f"{path.relative_to(REPO_ROOT)}:{lineno}: states OpenShift AI "
                        f"{found}, platform_profile.yaml declares {release_train}",
                    ))
    return findings


def main() -> int:
    profile = _load_profile()
    findings = (
        check_make_commands()
        + check_adr_index()
        + check_day0_day1_roles()
        + check_version_consistency(profile)
    )

    print("Checked README.md Make commands, docs/adr/README.md index, "
          "Makefile/ansible role consistency, and platform version prose "
          f"against {PROFILE_PATH.relative_to(REPO_ROOT)}.")
    if not findings:
        print("\nRESULT: PASS - no documentation drift detected.")
        return 0

    print(f"\n{len(findings)} documentation drift issue(s) found:")
    for f in findings:
        print(f"  ✗ [{f.check}] {f.message}")
    print("\nRESULT: FAIL - reconcile documentation with the Makefile/ADR/platform_profile.yaml source of truth (ADR-0323).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
