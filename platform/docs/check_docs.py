#!/usr/bin/env python3
"""ADR-0323 policy-as-code check: "Establish canonical generated and
validated platform documentation." Validates that curated documentation
doesn't contradict the two levels ADR-0323 puts above it: ADRs (status/
title/index) and executable configuration (the Makefile's actual verb/
component contract, `platform_profile.yaml`'s declared version intent).
No live cluster or registry needed - pure static text/YAML inspection,
same style as `platform/supply-chain/check_build_matrix.py`.

Ten checks, each independent (a failure in one doesn't block the others
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
  - agent_status_vs_adr: for every wp-NN-<agent>-slice.md brief, if
    agents/<agent>/agent.okf.md declares `zuno.status: active`, its own
    WP's governing ADR(s) (title + `- **ADRs:**` bullet) must be
    `Implemented`, not still `Partially implemented`/`Proposed` (caught a
    real drift live 2026-08-30 - see ADR-0326/WP-31);
  - day0_day1_roles: every Makefile DAY0_COMPONENTS/DAY1_RUN_COMPONENTS/
    DAY1_BUILD_COMPONENTS entry has a matching ansible/roles/<name> role;
  - debug_make_commands: every `make dN <verb> <component>` a debug task
    prints to the operator is one the Makefile accepts - the auto_fix check
    one surface further out (an operator types a printed instruction
    verbatim; five were unrunnable when this was added, including the
    mariadb role's own "how to enable backups" message);
  - gitops_values_clobber: no role's gitops_app_extra_helm_values dict drops
    a key its Application manifest declares - that variable REPLACES
    spec.source.helm.values wholesale (a YAML string key combine() cannot
    merge into), so a missing key silently falls back to the chart default
    while the Application still reports Synced/Healthy. This deleted
    ADR-0211's entire ACME track from demo222 for nine days, found
    2026-09-02 only by reading the live Application;
  - version_consistency: README.md/MEMORY.md/docs/architecture/*.md/
    docs/platform/*.md/platform/*/README.md don't state an OpenShift or
    OpenShift AI version other than platform_profile.yaml's declared
    target/release train (ADR bodies are immutable and excluded; RAG
    fixture/test data is excluded - those are demo content, not platform
    documentation).
  - model_roles: every provider-routing.yaml entry declares an
    architectural `role`, exactly one local model id holds `default`, and
    every task an agent bundle declares has an explicit
    model-routing-policy.yaml entry. ADR-0518 named qwen3.6-27b-instruct
    the chat model and ADR-0531 named qwen3.5-9b the fleet default five
    days later, neither recording a supersession; the coverage half found
    `arkos/structure-demo` still riding the file-order default that
    ADR-0531 decision 1 claims no task rides.

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

PROVIDER_ROUTING_PATH = REPO_ROOT / "platform" / "ai-gateway" / "provider-routing.yaml"
MODEL_ROUTING_POLICY_PATH = (
    REPO_ROOT / "policies" / "model-routing" / "model-routing-policy.yaml"
)

# The architectural roles provider-routing.yaml's `role` key may hold, and
# which that file's own header block documents at length. Kept in sync by
# check_model_roles rather than by hand: an unlisted role fails the check.
MODEL_ROLES = {
    "default",
    "quality",
    "reasoning",
    "specialized",
    "reasoning-external",
    "code",
    "general-external",
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


DEBUG_PLACEHOLDER_RE = re.compile(r"[<\[{|]")


def _debug_tasks(tasks) -> List[dict]:
    """Every debug task in a playbook, including inside block/rescue/always."""
    found: List[dict] = []
    for task in tasks or []:
        if not isinstance(task, dict):
            continue
        debug = task.get("ansible.builtin.debug") or task.get("debug")
        if isinstance(debug, dict):
            found.append(debug)
        for key in ("block", "rescue", "always"):
            if isinstance(task.get(key), list):
                found += _debug_tasks(task[key])
    return found


def check_debug_make_commands() -> List[Finding]:
    """Every `make dN <verb> <component>` printed by a debug task must be runnable.

    Same rationale as check_auto_fix_commands, one surface further out: a
    debug `msg` is printed straight to the operator mid-run, and they type it
    verbatim. Nothing executes it, so a wrong day survives indefinitely while
    looking authoritative.

    Found five live instances when added 2026-09-02, all rejected by the
    Makefile with "Unsupported dayN component": the mariadb role told the
    operator to run `make d0 install mariadb` (Day 1) in the very message
    printed when its S3 backup keys are unset - so the one instruction an
    operator would follow to enable backups could not work. Also
    `make d0 install smtp` (Day 1), `make d1 install mlops` and
    `make d1 install rag-ingestion` (both Day 2), and `make d0 configure
    keycloak` (no such verb).

    Deliberately NOT extended to role READMEs: prose there is full of
    placeholders (`<component>`, `[agents|platform|all]`, `make d1 build X`)
    and alternation notation, which drowns the signal - a scan of them
    produced 124 hits, nearly all punctuation artefacts. A component
    containing a placeholder character is skipped here for the same reason.
    """
    findings: List[Finding] = []
    lists = _parse_makefile_lists()
    for path in sorted((REPO_ROOT / "ansible").rglob("*.yml")):
        if path.name == "confidential.yml":
            continue
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(document, list):
            continue
        rel = path.relative_to(REPO_ROOT)
        for debug in _debug_tasks(document):
            text = f"{debug.get('msg', '')} {debug.get('var', '')}"
            for day, verb, component in MAKE_COMMAND_RE.findall(text):
                if "{{" in day or "{{" in verb:
                    continue
                component = (component or "").split("#", 1)[0].strip().strip("`\"',.:;)").strip()
                if DEBUG_PLACEHOLDER_RE.search(component) or "{{" in component:
                    component = ""
                findings += _check_one_make_command(
                    day, verb, component, lists, f"{rel}: debug msg", "debug_make_commands")
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


AGENTS_DIR = REPO_ROOT / "agents"
# Matches the naming convention the ADR-0326 slice WPs use
# (wp-31-arkos-slice.md, wp-33-comage-slice.md, ...) - deliberately not
# every WP maps to exactly one agent, so this scopes the check to the
# briefs that do rather than trying to cover the whole tracker.
SLICE_WP_RE = re.compile(r"^wp-\d+-([a-z0-9]+)-slice\.md$")


def _wp_governing_adrs(wp_path: pathlib.Path) -> List[str]:
    """ADR ids this WP brief's title and `- **ADRs:**` bullet name.

    Deliberately NOT a scan of the whole brief body - a brief's narrative
    State field mentions dozens of ADRs in passing (security/policy ADRs
    its own checks cover), only a small fraction of which are the ADR(s)
    that actually gate this agent's `zuno.status`.
    """
    text = wp_path.read_text()
    title_line = text.splitlines()[0] if text else ""
    adrs_bullet = re.search(r"^- \*\*ADRs:\*\*\s*(.+?)(?=\n- \*\*|\n\n|\Z)", text, re.MULTILINE | re.DOTALL)
    scoped_text = title_line + "\n" + (adrs_bullet.group(1) if adrs_bullet else "")
    return sorted(set(re.findall(r"ADR-(\d{4})", scoped_text)))


def check_agent_status_vs_adr() -> List[Finding]:
    """An agent bundle's `zuno.status: active` implies its slice WP's
    governing ADR(s) are genuinely `Implemented`, not still `Partially
    implemented`/`Proposed`.

    ADR-0326/WP-31 found this drift live 2026-08-30: Arkos and Comage had
    both been flipped to `active` by explicit operator direction days
    before ADR-0326's own `**Status:**` field caught up to
    `Partially implemented` -> `Implemented` - and nothing else in this
    script checks the OKF-bundle/ADR pair the way check_adr_index checks
    the ADR/index pair or check_wp_state checks the WP/tracker pair.
    """
    findings: List[Finding] = []

    for wp_path in sorted(WP_DIR.glob("wp-*.md")):
        match = SLICE_WP_RE.match(wp_path.name)
        if not match:
            continue
        agent = match.group(1)
        okf_path = AGENTS_DIR / agent / "agent.okf.md"
        if not okf_path.is_file():
            continue

        status_match = re.search(r"^\s*status:\s*(\S+)", okf_path.read_text(), re.MULTILINE)
        if not status_match or status_match.group(1) != "active":
            continue

        for adr_id in _wp_governing_adrs(wp_path):
            adr_matches = sorted(ADR_DIR.glob(f"{adr_id}-*.md"))
            if not adr_matches:
                continue
            status_line = re.search(r"\*\*Status:\*\*\s*(.+)", adr_matches[0].read_text())
            if not status_line:
                continue
            adr_status = _normalize_adr_status(status_line.group(1))
            # A superseded ADR's replacement is out of this check's scope -
            # only flag a governing ADR that is still open/partial on its
            # own terms.
            if adr_status != "Implemented" and not adr_status.startswith("Superseded"):
                findings.append(Finding(
                    "agent_status_vs_adr",
                    f"agents/{agent}/agent.okf.md declares zuno.status: active, but "
                    f"{wp_path.relative_to(REPO_ROOT)}'s governing ADR-{adr_id} status is "
                    f"'{adr_status}', not Implemented - a promotion flip should not outrun "
                    f"its own gate ADR.",
                ))
    return findings


def _okf_frontmatter(path: pathlib.Path) -> dict:
    """Parse an OKF bundle's leading `---` YAML frontmatter block.

    Same shape platform/okf/generate_authorization_matrix.py's
    `_split_document` reads; duplicated here for the same reason that
    file duplicates validate_okf_bundle.py's parsing - small,
    well-specified logic with an independent lifecycle.
    """
    parts = path.read_text(encoding="utf-8").split("---", 2)
    if len(parts) < 3 or parts[0].strip():
        return {}
    return yaml.safe_load(parts[1]) or {}


def check_model_roles() -> List[Finding]:
    """Every provider declares an architectural role, exactly one local
    model holds `default`, and every declared (agent, task) pair has an
    explicit routing entry.

    ADR-0518 decision 1 made `qwen3.6-27b-instruct` the chat/agents model
    and classed `Qwen3.5-9B` as a training base only; ADR-0531 made
    `qwen3.5-9b` the fleet-wide default five days later. Neither ADR
    recorded a supersession, and nothing here validated the pair - the
    same blind spot check_adr_index and check_wp_state each close for
    their own document pair.

    The third invariant is the one with teeth. ADR-0531 decision 1 states
    that "every declared (agent, task) pair across all eight agents now
    carries an explicit `preferred:` entry - no more implicit
    provider-routing.yaml file-order default for any task". That was
    false when written: ADR-0531 decision 7 counted "all three of Arkos's
    declared tasks" where the bundle declares four, so
    `arkos/structure-demo` was left riding the file-order default while
    two other documents claimed it rode the fleet default instead. Only
    the generated authorization matrix was right. Asserting the invariant
    the ADR already claims is what keeps the next task from slipping
    through the same gap.
    """
    findings: List[Finding] = []

    providers_doc = yaml.safe_load(PROVIDER_ROUTING_PATH.read_text(encoding="utf-8")) or {}
    providers = providers_doc.get("providers") or []

    by_name = {}
    default_models = set()
    for provider in providers:
        name = provider.get("name")
        role = provider.get("role")
        by_name[name] = provider
        if role not in MODEL_ROLES:
            findings.append(Finding(
                "model_roles",
                f"provider-routing.yaml's '{name}' declares role "
                f"{role!r}, which is not one of: {', '.join(sorted(MODEL_ROLES))}",
            ))
            continue
        if role == "default":
            if provider.get("kind") != "local":
                findings.append(Finding(
                    "model_roles",
                    f"provider-routing.yaml's '{name}' holds role 'default' but is "
                    f"kind {provider.get('kind')!r} - the fleet default must be a local "
                    f"model (ADR-0021: a C3 turn must still reach it).",
                ))
            default_models.add(provider.get("model"))

    if len(default_models) != 1:
        findings.append(Finding(
            "model_roles",
            f"provider-routing.yaml declares {len(default_models)} distinct model id(s) "
            f"with role 'default' ({', '.join(sorted(default_models)) or 'none'}) - "
            f"ADR-0531 decision 1 defines exactly one fleet-wide default.",
        ))

    policy_doc = yaml.safe_load(MODEL_ROUTING_POLICY_PATH.read_text(encoding="utf-8")) or {}
    preferences = policy_doc.get("preferences") or []

    declared = set()
    for entry in preferences:
        declared.add((entry.get("agent"), entry.get("task")))
        for key in ("preferred", "prefer"):
            for provider_name in entry.get(key) or []:
                if provider_name not in by_name:
                    findings.append(Finding(
                        "model_roles",
                        f"model-routing-policy.yaml's {entry.get('agent')}/{entry.get('task')} "
                        f"names provider '{provider_name}', which provider-routing.yaml does "
                        f"not declare (routing.py warns and ignores it at runtime, so the "
                        f"chain silently loses a candidate).",
                    ))

    for okf_path in sorted(AGENTS_DIR.glob("*/agent.okf.md")):
        zuno = (_okf_frontmatter(okf_path).get("zuno") or {})
        agent = zuno.get("name", okf_path.parent.name)
        for task in zuno.get("tasks") or []:
            if (agent, task) not in declared:
                findings.append(Finding(
                    "model_roles",
                    f"agents/{okf_path.parent.name}/agent.okf.md declares task '{task}', but "
                    f"model-routing-policy.yaml has no preferences entry for {agent}/{task} - "
                    f"it falls through to provider-routing.yaml file order, which ADR-0531 "
                    f"decision 1 states no task does.",
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


def check_gitops_values_clobber() -> List[Finding]:
    """Catch roles whose gitops_app_extra_helm_values silently drops manifest keys.

    apply_gitops_app.yml injects that variable as spec.source.helm.values, which
    is a YAML *string* key - so combine(recursive=True) cannot merge into it and
    the dict REPLACES the Application manifest's own values wholesale. Any key
    declared in gitops/apps/<c>/application-<phase>.yaml but absent from the
    role's dict therefore falls back to the chart default, with no error and the
    Application still reporting Synced/Healthy.

    This is not theoretical. It deleted ADR-0211's entire ACME track from
    demo222 for nine days (cert_manager dropped certmanager.enabled and the acme
    block; prune+selfHeal removed the ClusterIssuers, the Certificates and the
    IngressController/APIServer patches), and separately kept the Keycloak
    Ingress on its Vault-issued certificate by dropping ingress.acmeWildcardTLS.
    Both were found on 2026-09-02 only by reading the live Application.

    A role that passes a string instead of a dict is exempt: that is the fixed
    form, which reads the manifest and merges in runtime-discovered values.
    """
    findings: List[Finding] = []
    for tasks_file in sorted((REPO_ROOT / "ansible" / "roles").glob("*/tasks/*.yml")):
        try:
            tasks = yaml.safe_load(tasks_file.read_text())
        except Exception:
            continue
        if not isinstance(tasks, list):
            continue
        for task in tasks:
            if not isinstance(task, dict):
                continue
            include = task.get("ansible.builtin.include_tasks") or task.get("include_tasks") or ""
            if "apply_gitops_app.yml" not in str(include):
                continue
            task_vars = task.get("vars") or {}
            extra = task_vars.get("gitops_app_extra_helm_values")
            # None: the manifest is applied verbatim, nothing can be dropped.
            # str: the fixed form (a Jinja expression reading the manifest).
            if extra is None or isinstance(extra, str):
                continue
            component = task_vars.get("gitops_component_name")
            phase = task_vars.get("gitops_app_phase")
            if not component or not phase or "{{" in str(component) or "{{" in str(phase):
                continue
            manifest = REPO_ROOT / "gitops" / "apps" / str(component) / f"application-{phase}.yaml"
            if not manifest.exists():
                continue
            try:
                declared = yaml.safe_load(
                    yaml.safe_load(manifest.read_text())["spec"]["source"]["helm"]["values"]
                )
            except Exception:
                continue
            if not isinstance(declared, dict):
                continue
            dropped = [key for key in declared if key not in extra]
            if dropped:
                findings.append(Finding(
                    "gitops_values_clobber",
                    f"{tasks_file.relative_to(REPO_ROOT)}: the {component}/{phase} apply's "
                    f"gitops_app_extra_helm_values drops {', '.join(sorted(dropped))} declared in "
                    f"gitops/apps/{component}/application-{phase}.yaml - that dict REPLACES "
                    f"spec.source.helm.values, so those keys silently fall back to chart defaults. "
                    f"Read the manifest and merge in only runtime-discovered values instead "
                    f"(see ansible/roles/cert_manager/tasks/install.yml)",
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
                # The startswith() arm let a bare "3.5" pass while the
                # profile declared "3.5 EA2" - a legitimate shorthand in
                # headings/prose. Since 2026-09-03 the profile declares a
                # bare "3.5" (ADR-0002 as amended: the EA pin reached GA),
                # so that arm is now inert and the check is exact: a
                # leftover "OpenShift AI 3.5 EA2" is flagged, which is the
                # point. Only a genuinely different release (e.g. "3.4",
                # "2.19") would otherwise be caught.
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
        + check_agent_status_vs_adr()
        + check_day0_day1_roles()
        + check_debug_make_commands()
        + check_gitops_values_clobber()
        + check_version_consistency(profile)
        + check_model_roles()
    )

    print("Checked README.md Make commands, Ansible auto_fix commands, "
          "docs/adr/README.md index, work-package state vs the roadmap trackers, "
          "agent zuno.status vs its governing ADR(s), Makefile/ansible role "
          "consistency, make commands printed by debug tasks, GitOps Application values against the roles that replace them, "
          f"platform version prose against {PROFILE_PATH.relative_to(REPO_ROOT)}, "
          "and model architectural roles against provider-routing.yaml/"
          "model-routing-policy.yaml.")
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
