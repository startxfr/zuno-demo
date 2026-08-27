#!/usr/bin/env python3
"""ADR-0323 policy-as-code check: "Establish canonical generated and
validated platform documentation." Validates that curated documentation
doesn't contradict the two levels ADR-0323 puts above it: ADRs (status/
title/index) and executable configuration (the Makefile's actual verb/
component contract, `platform_profile.yaml`'s declared version intent).
No live cluster or registry needed - pure static text/YAML inspection,
same style as `platform/supply-chain/check_build_matrix.py`.

Six checks, each independent (a failure in one doesn't block the others
from reporting):
  - make_commands: every literal `make day0|d0|day1|d1 ...` example in
    README.md uses a verb/component this repository's actual Makefile
    accepts;
  - adr_index: every docs/adr/NNNN-*.md file has a docs/adr/README.md
    index row, and that row's status matches the ADR's own `**Status:**`
    field (catches stale statuses, e.g. an ADR quietly downgraded to
    "Partially implemented" without its index row following);
  - wp_state: every docs/roadmap/work-packages/wp-*.md brief has a tracker
    row, and that row's State matches the brief's own `- **State:**` line
    (the WP half of adr_index - the roadmap's rule wants five copies moved
    together, and this pair was the one nothing validated);
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
MAKE_COMMAND_RE = re.compile(r"\bmake[ \t]+(?:day)?(d?[0-3])[ \t]+(\S+)(?:[ \t]+(\S+))?")
# Ansible blocked-findings carry an `auto_fix:` string telling the operator
# which make command repairs the finding. Nothing executes it, so until it
# is linted it can name a command the Makefile rejects - which is exactly
# what happened to `make d0 reconcile openshift-ai` (a Day 0 verb applied
# to a Day 1 component), printed by nine findings and runnable by none.
AUTO_FIX_RE = re.compile(r"^\s*auto_fix:\s*[\"']?(.+?)[\"']?\s*$", re.MULTILINE)
OPENSHIFT_VERSION_RE = re.compile(r"OpenShift(?: Container Platform)? (\d+\.\d+)\b")
OPENSHIFT_AI_VERSION_RE = re.compile(r"OpenShift AI (\d+\.\d+(?: EA\d)?)\b")

# Roadmap container files (0100/0200/0300/0400) hold embedded/promoted
# ADR-0101.. / ADR-0201.. / ADR-0301.. / ADR-0401.. entries, each
# individually indexed via its own row or an anchor link into the
# container - the container file itself is not a numbered ADR and has no
# row of its own, by docs/adr/README.md's own convention (see its
# ADR-0101.. rows).
ADR_INDEX_EXCLUDED_FILES = {
    "0100-v0.1-roadmap.md",
    "0200-v0.2-roadmap.md",
    "0300-v0.3-roadmap.md",
    "0400-v0.4-roadmap.md",
}

WP_DIR = REPO_ROOT / "docs" / "roadmap" / "work-packages"
# Both roadmap files carry WP tracker tables with the identical 6-column
# header; there is no third one (verified across docs/roadmap/*.md).
WP_TRACKER_PATHS = [
    REPO_ROOT / "docs" / "roadmap" / "v0.1-v0.3-implementation-roadmap.md",
    REPO_ROOT / "docs" / "roadmap" / "okf-roadmap.md",
]

# The declared state machine plus the three terminal states real work
# actually reaches (both roadmap files document all eight). A WP that
# merged code and was then superseded is `Abandoned` - see WP-066.
WP_STATES = {
    "not started",
    "repo work in review",
    "repo work merged",
    "operator pending",
    "done",
    "abandoned",
    "cancelled",
    "closed — deferred",
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
    for name in ("DAY0_VERBS", "DAY0_COMPONENTS",
                 "DAY1_VERBS", "DAY1_RUN_COMPONENTS", "DAY1_BUILD_COMPONENTS",
                 "DAY2_VERBS", "DAY2_RUN_COMPONENTS", "DAY2_BUILD_COMPONENTS",
                 "DAY3_VERBS", "DAY3_TEST_COMPONENTS", "DAY3_BACKUP_COMPONENTS"):
        match = re.search(rf"^{name}\s*:=\s*(.*)$", text, re.MULTILINE)
        lists[name] = match.group(1).split() if match else []
    return lists


def _normalize_day(day: str) -> str:
    """`make day1 ...` and `make d1 ...` are the same Makefile target."""
    return day if day.startswith("d") else f"d{day}"


def _verbs_for(day: str, lists: dict) -> List[str]:
    return lists.get(f"DAY{_normalize_day(day)[1]}_VERBS", [])


def _components_for(day: str, verb: str, lists: dict) -> List[str]:
    """Which component list a given day+verb validates against.

    Day 0 shares one list across every verb; Day 1 and Day 2 split
    build-only components from run components; Day 3's verbs each own a
    narrower list, so it unions them rather than rejecting a valid pair.
    """
    day = _normalize_day(day)
    if day == "d0":
        return lists["DAY0_COMPONENTS"]
    if day in ("d1", "d2"):
        key = "BUILD" if verb == "build" else "RUN"
        return lists[f"DAY{day[1]}_{key}_COMPONENTS"]
    return lists["DAY3_TEST_COMPONENTS"] + lists["DAY3_BACKUP_COMPONENTS"]


def _check_one_make_command(day: str, verb: str, component: str,
                            lists: dict, origin: str, check: str) -> List[Finding]:
    findings: List[Finding] = []
    day = _normalize_day(day)
    verbs = _verbs_for(day, lists)
    if verb not in verbs:
        findings.append(Finding(
            check,
            f"{origin} names 'make {day} {verb}' which is an unsupported verb "
            f"(expected one of: {' '.join(verbs)})",
        ))
        return findings
    if not component or component == "all":
        return findings
    components = _components_for(day, verb, lists)
    if component not in components:
        findings.append(Finding(
            check,
            f"{origin} names 'make {day} {verb} {component}' which is an "
            f"unsupported component (expected one of: {' '.join(components)} or all)",
        ))
    return findings

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
            # README prose puts trailing `# explanation` comments and a
            # closing backtick inside the captured group.
            component = (component or "").split("#", 1)[0].strip().rstrip("`")
            findings += _check_one_make_command(
                day, verb, component, lists, "README.md example", "make_commands")
    return findings


def check_auto_fix_commands() -> List[Finding]:
    """Every Ansible blocked-finding's `auto_fix` must name a real command.

    `auto_fix` is printed by ansible/tasks/report_blocked_findings.yml as
    the remedy for a blocked resource, and an operator types it verbatim.
    Nothing executes it during a run, so an unrunnable string survives
    indefinitely while looking authoritative - `make d0 reconcile
    openshift-ai` (a Day 0 verb applied to a Day 1 component) sat in nine
    findings and was rejected by the Makefile every single time, which is
    why ADR-0201's payload-processing sidecar remediation was written,
    tested, documented and never once applied.

    Values beginning "manual only" are prose by convention, not commands.
    A component that is a Jinja expression cannot be resolved statically,
    but its day and verb still can - and those are what broke.
    """
    findings: List[Finding] = []
    lists = _parse_makefile_lists()
    for path in sorted((REPO_ROOT / "ansible").rglob("*.yml")):
        rel = path.relative_to(REPO_ROOT)
        for value in AUTO_FIX_RE.findall(path.read_text(encoding="utf-8")):
            # An unquoted-capture artefact leaves a stray quote behind for
            # `auto_fix: ""`, which means "no automatic fix" - the finding's
            # own `solution` field carries the human instruction there.
            value = value.strip().strip("\"'").strip()
            if not value or value.lower().startswith("manual only"):
                continue
            matches = MAKE_COMMAND_RE.findall(value)
            if not matches:
                # A value whose *day* is a Jinja expression is resolved at
                # runtime from the playbook's zuno_day, so there is nothing
                # static to check. That indirection is the fix for this whole
                # bug class, not an instance of it - the shared tasks are
                # reached from every day and cannot name one.
                if "{{" in value:
                    continue
                findings.append(Finding(
                    "auto_fix",
                    f"{rel}: auto_fix {value!r} names no 'make dN <verb>' command; "
                    "use a runnable command or prefix the string with 'manual only - '",
                ))
                continue
            for day, verb, component in matches:
                component = (component or "").strip().strip("`\"'")
                # Jinja-templated component: day+verb are still checkable.
                if "{{" in component or "{{" in verb:
                    component = ""
                findings += _check_one_make_command(
                    day, verb, component, lists, f"{rel}: auto_fix", "auto_fix")
    return findings


def _normalize_adr_status(text: str) -> str:
    # Markdown links compare as their label ("Superseded by
    # [ADR-0332](0332-...md)" == "Superseded by ADR-0332").
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # A superseded status may scope what remains in effect (ADR-0320,
    # ADR-0328); only the "Superseded by ADR-NNNN" phrase must match.
    superseded = re.match(r"Superseded by ADR-\d{4}", text)
    if superseded:
        return superseded.group(0)
    # Strip " - see `...`" elaborations and trailing parenthetical
    # explanations (e.g. ADR-0055) - only the status phrase itself must
    # match, not any evidence pointer appended to it.
    text = text.split(" - ", 1)[0]
    return text.split("(", 1)[0].strip()


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
        body_status = _normalize_adr_status(status_match.group(1))

        row_cells = [c.strip() for c in row_match.group(0).split("|")]
        # row_match captures from the link onward: "[ADR-NNNN](file.md) | Target | Status | Decision"
        if len(row_cells) < 3:
            continue
        row_status = _normalize_adr_status(row_cells[2])
        if row_status != body_status:
            findings.append(Finding(
                "adr_index",
                f"ADR-{adr_number} status drift: docs/adr/README.md index says "
                f"'{row_status}', the ADR's own body says '{body_status}'",
            ))
    return findings


def _normalize_wp_state(text: str) -> str:
    """Reduce a WP State value to its bare state phrase.

    Deliberately NOT _normalize_adr_status: WP values carry four shapes that
    one never does - `**bold**` wrappers, a date glued to the state with no
    parenthesis (`Abandoned 2026-08-26`), a `.` sentence break instead of a
    parenthetical (`Done. Live-verified ...`), and both em-dash and ASCII
    hyphen as the clause separator, sometimes in the same file. Three
    spellings of one state (`Done`, `Done — live-verified`, `Done. Live-...`)
    must all reduce to `done`.
    """
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)   # markdown links -> label
    text = text.replace("**", "")
    # `Closed — deferred` is one two-word state, not a state plus an
    # elaboration, so it has to be recognised before the clause split would
    # cut it at the em-dash (same shape as _normalize_adr_status's
    # "Superseded by ADR-NNNN" special case).
    compound = re.match(r"\s*Closed\s*[-\u2014\u2013]\s*deferred", text, re.IGNORECASE)
    if compound:
        return "closed — deferred"
    # First clause boundary wins. The date alternative comes first so
    # "Abandoned 2026-08-26" loses the date rather than keeping it.
    text = re.split(r"\s+\d{4}-\d{2}-\d{2}|[(;.]|\s[-\u2014\u2013]\s", text)[0]
    return " ".join(text.split()).casefold().strip(" .:,")


def _wp_tracker_rows() -> dict:
    """brief filename -> (row line, tracker path, cell count).

    Keyed on the filename from the row's own link, never on the WP id:
    `WP-57` and `WP-057` are two different work packages (likewise 58/058),
    so any int() or zero-stripping would silently merge them.
    """
    rows = {}
    for tracker_path in WP_TRACKER_PATHS:
        for line in tracker_path.read_text().splitlines():
            if not line.startswith("| WP-"):
                continue
            link = re.search(r"work-packages/(wp-[^)]+\.md)", line)
            if not link:
                # WP-00 is recorded as executed inline and has no brief.
                continue
            rows[link.group(1)] = (line, tracker_path, len(line.split("|")))
    return rows


def check_wp_state() -> List[Finding]:
    """Every WP brief has a tracker row, and the two agree on the state.

    The WP half of what check_adr_index does for ADRs. The roadmap's own
    rule requires five copies to move together (ADR body + index + tracker +
    brief + MEMORY.md); until this check existed only the first two were
    validated, and the brief/tracker pair drifted repeatedly - WP-085 went
    stale within a day of being written.
    """
    findings: List[Finding] = []
    rows = _wp_tracker_rows()

    for brief_path in sorted(WP_DIR.glob("wp-*.md")):
        name = brief_path.name
        if name not in rows:
            findings.append(Finding("wp_state", f"{name} has no tracker row linking to it in docs/roadmap/"))
            continue
        row_line, tracker_path, cell_count = rows[name]
        tracker_rel = tracker_path.relative_to(REPO_ROOT)

        # 6 columns -> 8 fields once the leading/trailing empties are counted.
        # A State value containing a literal `|` would shift every index, so
        # report the row rather than compare the wrong cell (5 brief State
        # lines already contain `|`; it is one copy-paste from a tracker cell).
        if cell_count != 8:
            findings.append(Finding(
                "wp_state",
                f"{tracker_rel}: the row for {name} has {cell_count - 2} columns, expected 6 - "
                f"a `|` inside a cell would silently shift the State column",
            ))
            continue

        body = brief_path.read_text()
        # Anchored on the exact `- **State:**` bullet and consuming its
        # indented continuation lines: 39 of 85 briefs wrap the value, and a
        # dated variant (`- **State (2026-08-26):**`) must NOT match.
        state_match = re.search(r"^- \*\*State:\*\*\s*(.+?)(?=\n- \*\*|\n\n|\Z)", body, re.MULTILINE | re.DOTALL)
        if not state_match:
            findings.append(Finding("wp_state", f"{name} has no `- **State:**` line"))
            continue

        brief_state = _normalize_wp_state(state_match.group(1))
        row_state = _normalize_wp_state(row_line.split("|")[5])

        if brief_state != row_state:
            findings.append(Finding(
                "wp_state",
                f"{name} state drift: {tracker_rel} says '{row_state}', the brief says '{brief_state}'",
            ))
        for value, where in ((brief_state, name), (row_state, f"{tracker_rel} row for {name}")):
            if value not in WP_STATES:
                findings.append(Finding(
                    "wp_state",
                    f"{where}: '{value}' is not a declared WP state ({', '.join(sorted(WP_STATES))})",
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
        + check_auto_fix_commands()
        + check_adr_index()
        + check_wp_state()
        + check_day0_day1_roles()
        + check_version_consistency(profile)
    )

    print("Checked README.md Make commands, Ansible auto_fix commands, "
          "docs/adr/README.md index, work-package state vs the roadmap trackers, "
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
