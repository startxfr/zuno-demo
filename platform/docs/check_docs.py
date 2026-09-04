#!/usr/bin/env python3
"""ADR-0323 policy-as-code check: "Establish canonical generated and
validated platform documentation." Validates that curated documentation
doesn't contradict the two levels ADR-0323 puts above it: ADRs (status/
title/index) and executable configuration (the Makefile's actual verb/
component contract, `platform_profile.yaml`'s declared version intent).
No live cluster or registry needed - pure static text/YAML inspection,
same style as `platform/supply-chain/check_build_matrix.py`.

Fourteen checks, each independent (a failure in one doesn't block the others
from reporting):
  - make_commands: every literal `make day0|d0|day1|d1 ...` example in
    README.md uses a verb/component this repository's actual Makefile
    accepts;
  - adr_index / adr_target / adr_section / adr_status_vocab: every
    docs/adr/NNNN-*.md file has exactly one docs/adr/README.md
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
  - model_context_windows: every local provider's max_model_len (ADR-0544)
    matches gitops/charts/models/values.yaml's real maxModelLen for that
    served model, every SaaS provider omits the field, and -maas/direct
    siblings of one model agree - the cross-reference that never existed
    while a fleet-default model served a narrower window than the budget
    written against it assumed.

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
# Relative markdown links naming a 4-digit-prefixed ADR/WP file. Absolute
# URLs and bare anchors are deliberately out of scope - this catches the
# one mistake that actually recurs: a path correct for the wrong depth.
DOC_LINK_RE = re.compile(r"\]\((?!https?:)([^)\s]*?\d{4}-[^)\s]*?\.md(?:#[^)\s]*)?)\)")
OPENSHIFT_VERSION_RE = re.compile(r"OpenShift(?: Container Platform)? (\d+\.\d+)\b")
OPENSHIFT_AI_VERSION_RE = re.compile(r"OpenShift AI (\d+\.\d+(?: EA\d)?)\b")

WP_DIR = REPO_ROOT / "docs" / "roadmap" / "work-packages"
# One tracker since 2026-09-03: okf-roadmap.md's three phases folded into
# the platform roadmap as phases 33-35 and its tracker became a pointer, so
# it no longer carries WP rows. The file was also renamed from
# v0.1-v0.3-implementation-roadmap.md, having long since outgrown that title.
WP_TRACKER_PATHS = [
    REPO_ROOT / "docs" / "roadmap" / "implementation-roadmap.md",
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
MODELS_VALUES_PATH = REPO_ROOT / "gitops" / "charts" / "models" / "values.yaml"

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


def _debug_tasks(tasks, modules=("debug",)) -> List[dict]:
    """Every debug (or fail) task in a playbook, including inside block/rescue/always.

    `modules` exists because a `fail` msg is the same operator surface as a
    `debug` msg, only louder: it is the last thing printed before the run stops,
    so it is the message an operator is most likely to act on verbatim. ADR-0344
    is the cost of not checking it - `make d0 reconcile openshift-ai` was
    published as the authoritative remedy by nine findings and had never once
    worked, because reconcile was a Day 0 verb and openshift-ai is a Day 1
    component. WP-132 then found the same wrong day surviving in
    discover_channel.yml's own fail message.
    """
    found: List[dict] = []
    for task in tasks or []:
        if not isinstance(task, dict):
            continue
        for module in modules:
            body = task.get(f"ansible.builtin.{module}") or task.get(module)
            if isinstance(body, dict):
                found.append(body)
        for key in ("block", "rescue", "always"):
            if isinstance(task.get(key), list):
                found += _debug_tasks(task[key], modules)
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
        for debug in _debug_tasks(document, ("debug", "fail")):
            text = f"{debug.get('msg', '')} {debug.get('var', '')}"
            for day, verb, component in MAKE_COMMAND_RE.findall(text):
                if "{{" in day or "{{" in verb:
                    continue
                component = (component or "").split("#", 1)[0].strip().strip("`\"',.:;)").strip()
                if DEBUG_PLACEHOLDER_RE.search(component) or "{{" in component:
                    component = ""
                findings += _check_one_make_command(
                    day, verb, component, lists, f"{rel}: debug/fail msg", "debug_make_commands")
    return findings


# The closed status vocabulary docs/adr/README.md's Conventions section
# declares. Anything else is drift: before 2026-09-03 the index carried
# free-text variants ("Implemented (CA source corrected by ADR-0347)") that
# hid whether a record was live, and one status - "Superseded by X" - was
# being used for both full and partial supersessions, which is what let
# ADR-0002 sit at `Implemented` while ADR-0319 superseded half of it.
ADR_STATUS_VOCAB = {
    "Proposed",
    "Accepted",
    "Partially implemented",
    "Implemented",
    "Deferred",
    "Deprecated",
}

# "Superseded by ADR-0219", "Superseded in part by ADR-0526",
# "Superseded by ADR-0332 and ADR-0349".
_ADR_SUPERSEDED_PREFIX = re.compile(
    r"Superseded (?:in part )?by ADR-\d{4}(?: and ADR-\d{4})*")
_ADR_SUPERSEDED_STATUS = re.compile(_ADR_SUPERSEDED_PREFIX.pattern + r"$")

# Sections of the index that are version bands, plus the one that is not.
ADR_RETIRED_SECTION = "Retired"


def _adr_status_valid(status: str) -> bool:
    return status in ADR_STATUS_VOCAB or bool(_ADR_SUPERSEDED_STATUS.match(status))


def _adr_status_retired(status: str) -> bool:
    """Fully superseded or deprecated - belongs in the Retired section.

    `Superseded in part` deliberately does NOT count: part of that decision
    is still in force, so the record stays in its version band.
    """
    return status == "Deprecated" or status.startswith("Superseded by ADR-")


def _normalize_adr_status(text: str) -> str:
    # Markdown links compare as their label ("Superseded by
    # [ADR-0332](0332-...md)" == "Superseded by ADR-0332").
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # A superseded status may scope what remains in effect (ADR-0320,
    # ADR-0328); only the "Superseded by ADR-NNNN" phrase must match.
    superseded = _ADR_SUPERSEDED_PREFIX.match(text)
    if superseded:
        return superseded.group(0)
    # Strip " - see `...`" elaborations and trailing parenthetical
    # explanations (e.g. ADR-0055) - only the status phrase itself must
    # match, not any evidence pointer appended to it.
    text = text.split(" - ", 1)[0]
    return text.split("(", 1)[0].strip()


def _adr_body_fields(adr_path) -> dict:
    """Status, Target and the Supersedes field of one ADR file."""
    body = adr_path.read_text()
    out = {}
    for key in ("Status", "Target", "Supersedes"):
        m = re.search(rf"^- \*\*{key}:\*\*\s*(.+?)(?=\n- \*\*|\n\n|\Z)",
                      body, re.S | re.M)
        out[key] = " ".join(m.group(1).split()) if m else None
    return out


def _adr_index_rows() -> dict:
    """ADR number -> list of parsed index rows (a list, so duplicates show).

    Active sections carry `| ADR | Status | Decision |`; the Retired section
    carries a `Target` column too, because it has no version heading to
    derive one from. Rows are keyed by number and collected per section, so
    a row can be checked against the section it actually sits in - the drift
    class that put ADR-0352 (Target v0.9) inside the v0.7 table.
    """
    rows = {}
    section = None
    for line in ADR_README_PATH.read_text().splitlines():
        heading = re.match(r"^## (.+?)\s*$", line)
        if heading:
            section = heading.group(1)
            continue
        m = re.match(r"^\| \[ADR-(\d{4})\]\(([^)]+)\)(\s*\*\(stub\)\*)? \| (.*) \|\s*$", line)
        if not m:
            continue
        cells = [c.strip() for c in m.group(4).split("|")]
        if section == ADR_RETIRED_SECTION:
            target, status = (cells + ["", ""])[0], (cells + ["", ""])[1]
        else:
            target, status = section, (cells + [""])[0]
        rows.setdefault(m.group(1), []).append({
            "section": section, "link": m.group(2).strip(),
            "stub": bool(m.group(3)), "target": target, "status": status,
        })
    return rows


def check_adr_index() -> List[Finding]:
    """The index agrees with the records it indexes.

    Until 2026-09-03 this compared exactly one pair - the index Status cell
    against the ADR body's Status - and reported PASS while 33 rows sat in a
    section contradicting their own Target, ten rows pointed at no file, and
    nine declared supersessions had never been written back. Target, section
    placement, the status vocabulary and row-level integrity are all checked
    here now.
    """
    findings: List[Finding] = []
    rows = _adr_index_rows()
    files = {p.name[:4]: p for p in sorted(ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md"))}

    for number, entries in sorted(rows.items()):
        if len(entries) > 1:
            findings.append(Finding(
                "adr_index",
                f"ADR-{number} has {len(entries)} index rows "
                f"(sections: {', '.join(e['section'] or '?' for e in entries)}); "
                "each record is indexed exactly once"))
        row = entries[0]
        if number not in files and not row["stub"]:
            findings.append(Finding(
                "adr_index",
                f"ADR-{number} has an index row but no docs/adr/{number}-*.md file; "
                "a row whose record lives in the roadmap must be marked *(stub)*"))

    for number, adr_path in files.items():
        entries = rows.get(number)
        if not entries:
            findings.append(Finding(
                "adr_index",
                f"ADR-{number} ({adr_path.name}) has no docs/adr/README.md index row"))
            continue
        row = entries[0]
        if row["link"] != adr_path.name:
            findings.append(Finding(
                "adr_index",
                f"ADR-{number} index row links to '{row['link']}', "
                f"the file is '{adr_path.name}'"))

        fields = _adr_body_fields(adr_path)
        if fields["Status"] is None:
            continue
        body_status = _normalize_adr_status(fields["Status"])
        row_status = _normalize_adr_status(row["status"])

        if row_status != body_status:
            findings.append(Finding(
                "adr_index",
                f"ADR-{number} status drift: docs/adr/README.md index says "
                f"'{row_status}', the ADR's own body says '{body_status}'"))

        if not _adr_status_valid(row_status):
            findings.append(Finding(
                "adr_status_vocab",
                f"ADR-{number} index status '{row_status}' is outside the declared "
                f"vocabulary ({', '.join(sorted(ADR_STATUS_VOCAB))}, "
                "'Superseded by ADR-NNNN', 'Superseded in part by ADR-NNNN')"))

        # Section placement. A fully superseded or deprecated record belongs
        # in Retired; everything else belongs under its own Target.
        body_target = (fields["Target"] or "").split(" (")[0].strip()
        if _adr_status_retired(body_status):
            if row["section"] != ADR_RETIRED_SECTION:
                findings.append(Finding(
                    "adr_section",
                    f"ADR-{number} is '{body_status}' but sits in section "
                    f"'{row['section']}'; fully superseded and deprecated records "
                    f"belong in '{ADR_RETIRED_SECTION}'"))
            elif row["target"] != body_target:
                findings.append(Finding(
                    "adr_target",
                    f"ADR-{number} Retired-row Target says '{row['target']}', "
                    f"the ADR's own body says '{body_target}'"))
        else:
            if row["section"] == ADR_RETIRED_SECTION:
                findings.append(Finding(
                    "adr_section",
                    f"ADR-{number} is '{body_status}' but sits in "
                    f"'{ADR_RETIRED_SECTION}'; a record still partly in force stays "
                    "in its version band"))
            elif row["section"] != body_target:
                findings.append(Finding(
                    "adr_target",
                    f"ADR-{number} sits in section '{row['section']}' but targets "
                    f"'{body_target}'; the section heading is the target"))
    return findings


# ADR-0527 supersedes ADR-0213 and then *extends* ADR-0209/ADR-0212 in the
# same field; only the clause before the extends/refines/amends verb is a
# supersession claim.
_SUPERSEDES_CUT = re.compile(r"\b(?:Extends|extends|Refines|refines|Amends|amends)\b")


def check_adr_supersede() -> List[Finding]:
    """A declared supersession is written back to the record it supersedes.

    Keyed strictly on the `- **Supersedes:**` field, never inferred from two
    ADRs disagreeing: ADR-0518/ADR-0526/ADR-0531 contradict each other on the
    fleet default model and are deliberately reconciled by dated correction
    notes rather than a supersession, and must not be flagged.

    Only the forward direction is checked. A record whose Status names a
    superseder that has no `Supersedes:` field of its own is legitimate - the
    claim is often made in the superseding ADR's Decision prose instead
    (ADR-0317, ADR-0349) - and ADR-0526's body cannot be amended to name
    ADR-0303 because an ADR body is immutable outside its Status line.
    """
    findings: List[Finding] = []
    fields = {p.name[:4]: _adr_body_fields(p)
              for p in sorted(ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md"))}

    for number, f in sorted(fields.items()):
        if not f["Supersedes"]:
            continue
        claim = _SUPERSEDES_CUT.split(re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", f["Supersedes"]))[0]
        for target in sorted(set(re.findall(r"ADR-(\d{4})", claim))):
            if target not in fields:
                findings.append(Finding(
                    "adr_supersede",
                    f"ADR-{number} declares it supersedes ADR-{target}, which has no file"))
                continue
            target_status = _normalize_adr_status(fields[target]["Status"] or "")
            if f"ADR-{number}" not in target_status:
                findings.append(Finding(
                    "adr_supersede",
                    f"ADR-{number} declares it supersedes ADR-{target}, but ADR-{target}'s "
                    f"status is '{target_status}' and never names ADR-{number}"))
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


ADR_VERSIONS = ["v0", "v0.1", "v0.2", "v0.3", "v0.4", "v0.5", "v0.6",
                "v0.7", "v0.8", "v0.9", "OKF v0.1"]
WP_OPEN_EXCLUDED = {"done", "abandoned", "cancelled", "closed — deferred"}


def check_wp_version_view() -> List[Finding]:
    """The roadmap's "Work packages by version" table is derived, not typed.

    It exists because phase headings used to assert a version and 36 rows
    disagreed with their ADRs' Target. That only helps while the table stays
    true, so it is recomputed here from the ADR bodies and the tracker rows
    rather than trusted.
    """
    findings: List[Finding] = []
    roadmap = WP_TRACKER_PATHS[0]
    text = roadmap.read_text()
    rel = roadmap.relative_to(REPO_ROOT)

    rows = {}
    for line in text.splitlines():
        m = re.match(r"^\| (v[\d.]+|OKF v[\d.]+) \| (\d+) \| ([^|]*) \| (\d+) \| ([^|]*) \|\s*$", line)
        if m:
            rows[m.group(1)] = (int(m.group(2)), m.group(3).strip(),
                                int(m.group(4)), m.group(5).strip())
    if not rows:
        return [Finding("wp_version_view",
                        f"{rel} has no 'Work packages by version' table rows")]

    targets, statuses = {}, {}
    for path in sorted(ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md")):
        f = _adr_body_fields(path)
        targets[path.name[:4]] = (f["Target"] or "").split(" (")[0].strip()
        statuses[path.name[:4]] = _normalize_adr_status(f["Status"] or "")
    for number, entries in _adr_index_rows().items():   # stubs have no file
        if number not in targets and entries[0]["stub"]:
            targets[number] = entries[0]["target"]
            statuses[number] = _normalize_adr_status(entries[0]["status"])

    tracker = []
    for line in text.splitlines():
        if not line.startswith("| WP-"):
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) >= 7:
            tracker.append((cells[1], re.findall(r"(\d{4})", cells[3]), cells[5]))

    for version in ADR_VERSIONS:
        version_adrs = [n for n, v in targets.items() if v == version]
        open_adrs = [n for n in version_adrs
                     if statuses[n] in ("Proposed", "Accepted", "Deferred",
                                        "Partially implemented")]
        wps = [(w, _normalize_wp_state(s)) for w, a, s in tracker
               if any(n in version_adrs for n in a)]
        open_wps = sorted({w for w, s in wps if s not in WP_OPEN_EXCLUDED})

        if version not in rows:
            findings.append(Finding(
                "wp_version_view",
                f"{rel}'s by-version table has no row for {version} "
                f"({len(version_adrs)} ADRs, {len(wps)} WPs)"))
            continue
        n_adr, open_adr_cell, n_wp, open_wp_cell = rows[version]
        if n_adr != len(version_adrs):
            findings.append(Finding(
                "wp_version_view",
                f"{rel}: {version} row says {n_adr} ADRs, the ADR bodies say "
                f"{len(version_adrs)}"))
        if n_wp != len(wps):
            findings.append(Finding(
                "wp_version_view",
                f"{rel}: {version} row says {n_wp} WPs, the tracker rows say "
                f"{len(wps)}"))
        listed = sorted(re.findall(r"WP-[\w-]+", open_wp_cell))
        if listed != open_wps:
            findings.append(Finding(
                "wp_version_view",
                f"{rel}: {version} open WPs listed as {listed or ['—']}, "
                f"the tracker states say {open_wps or ['—']}"))
        stated_open = open_adr_cell.strip()
        actual_open = str(len(open_adrs)) if open_adrs else "—"
        if stated_open != actual_open:
            findings.append(Finding(
                "wp_version_view",
                f"{rel}: {version} open-ADR count says '{stated_open}', "
                f"the ADR statuses say '{actual_open}'"))
    return findings


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


def check_doc_links() -> List[Finding]:
    """Every relative markdown link to an ADR resolves from the file that
    writes it.

    Work-package briefs live two directories below `docs/adr/`, so a link
    written as `](0309-....md)` - the shape that is correct inside an ADR
    body - silently points at a sibling that does not exist. Nothing
    rendered these as errors, so 15 of them across 11 briefs survived at
    HEAD until a 2026-09-03 audit. Cheap to assert, and the failure mode
    is invisible in review: the link text reads correctly either way.
    """
    findings: List[Finding] = []
    roots = [WP_DIR, ADR_DIR, REPO_ROOT / "docs" / "roadmap"]
    seen = set()

    for root in roots:
        for path in sorted(root.glob("*.md")):
            if path in seen:
                continue
            seen.add(path)
            for link in DOC_LINK_RE.findall(path.read_text(encoding="utf-8")):
                target = link.split("#", 1)[0]
                if not target:
                    continue
                if not (path.parent / target).resolve().is_file():
                    findings.append(Finding(
                        "doc_links",
                        f"{path.relative_to(REPO_ROOT)} links to '{target}', which does not "
                        f"resolve from that file's own directory.",
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


def _served_model_context_windows() -> Dict[str, int]:
    """model id (`servedModelName`) -> its real `--max-model-len`.

    Scans gitops/charts/models/values.yaml for every mapping - root
    included - that carries BOTH `servedModelName` and `maxModelLen`,
    rather than naming the four known keys (`gptOssModel`, `weshModel`,
    `qwen35Model`, the root qwen entry): hardcoding key names is exactly
    the drift this check exists to prevent, since a fifth model added
    under a new key would silently be invisible to a name-keyed scan.
    """
    doc = yaml.safe_load(MODELS_VALUES_PATH.read_text(encoding="utf-8")) or {}
    windows: Dict[str, int] = {}

    def _walk(node: object) -> None:
        if not isinstance(node, dict):
            return
        if "servedModelName" in node and "maxModelLen" in node:
            windows[node["servedModelName"]] = node["maxModelLen"]
        for value in node.values():
            _walk(value)

    _walk(doc)
    return windows


def check_model_context_windows() -> List[Finding]:
    """Every local provider's `max_model_len` (ADR-0544) matches the
    served model's real `--max-model-len`, every SaaS provider omits the
    field, and `-maas`/direct siblings of one served model agree.

    provider-routing.yaml and gitops/charts/models/values.yaml have
    independent lifecycles and nothing else keeps them honest - exactly
    the gap that let a 6000-token history budget go unnoticed against an
    8192-token model for as long as it did (ADR-0531's `qwen3.5-9b`,
    role `default`, is a structurally always-reachable fallback per that
    ADR's decision 1, while the other three local models serve 32768).
    components/agent-runtime/app/graph/prompt_budget.py reads this same
    max_model_len field to clamp the assembled prompt before sending -
    this check is what keeps that clamp honest.
    """
    findings: List[Finding] = []

    providers_doc = yaml.safe_load(PROVIDER_ROUTING_PATH.read_text(encoding="utf-8")) or {}
    providers = providers_doc.get("providers") or []
    chart_windows = _served_model_context_windows()

    by_model_declared: Dict[str, set] = {}
    for provider in providers:
        name = provider.get("name")
        model = provider.get("model")
        declared = provider.get("max_model_len")
        kind = provider.get("kind")

        if kind == "local":
            if declared is None:
                findings.append(Finding(
                    "model_context_windows",
                    f"provider-routing.yaml's '{name}' is kind 'local' but declares no "
                    f"max_model_len - agent-runtime's prompt clamp cannot see its real window.",
                ))
            elif model not in chart_windows:
                findings.append(Finding(
                    "model_context_windows",
                    f"provider-routing.yaml's '{name}' names model '{model}', which no "
                    f"servedModelName/maxModelLen pair in gitops/charts/models/values.yaml "
                    f"resolves - was the model renamed on one side only?",
                ))
            elif declared != chart_windows[model]:
                findings.append(Finding(
                    "model_context_windows",
                    f"provider-routing.yaml's '{name}' declares max_model_len={declared} for "
                    f"'{model}', but gitops/charts/models/values.yaml's own maxModelLen for "
                    f"that servedModelName is {chart_windows[model]} - the two have drifted.",
                ))
            by_model_declared.setdefault(model, set()).add(declared)
        elif kind == "saas" and declared is not None:
            findings.append(Finding(
                "model_context_windows",
                f"provider-routing.yaml's '{name}' is kind 'saas' but declares "
                f"max_model_len={declared} - SaaS windows are never the binding constraint "
                f"and nothing in this repo can cross-verify a SaaS value, so the field is "
                f"local-only by convention; remove it.",
            ))

    for model, values in by_model_declared.items():
        if len(values) > 1:
            findings.append(Finding(
                "model_context_windows",
                f"provider-routing.yaml's providers for model '{model}' disagree on "
                f"max_model_len ({sorted(values)}) - the -maas and direct entries for one "
                f"served model front the same runtime and must agree.",
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


def check_confidential_var_loaders() -> List[Finding]:
    """Catch roles that read an ansible/confidential.yml variable without loading it.

    This repo has no vars_files and no global include_vars: every role that reads
    an operator-supplied variable loads ansible/confidential.yml itself (stat,
    then include_vars when present). A role that reads one of those variables and
    skips the loader does not error - the variable is simply undefined, so the
    role's `| default(<chart value>)` fallback wins silently.

    That is exactly how cert_manager broke. WP-118 B6 moved the ACME DNS-01
    identity out of gitops/charts/cert-manager/values.yaml into
    ansible/confidential.yml and flipped the chart defaults to `mycluster-*`
    placeholders, but never added the loader - so the three variables were always
    undefined and the identity resolved to the placeholders. The apply that
    proved B6 inert was measured while the chart still carried the real values,
    so `changed=0` was true for the wrong reason, and the next
    `make d0 install cert-manager` would have written MYCLUSTERHOSTEDZONEID into
    the live Application and stopped DNS-01 from solving on demo222. Found
    2026-09-04 by WP-132, recorded as ADR-0517 B13.

    Commented-out keys in confidential.example.yml count as documented: an
    optional variable is exactly the case where the fallback hides the gap.
    """
    findings: List[Finding] = []
    example = REPO_ROOT / "ansible" / "confidential.example.yml"
    if not example.exists():
        return findings
    raw = example.read_text()
    try:
        documented = set(yaml.safe_load(raw) or {})
    except Exception:
        documented = set()
    documented |= set(re.findall(r"^#\s*(zuno_[a-z0-9_]+)\s*:", raw, re.M))
    if not documented:
        return findings

    for role_dir in sorted((REPO_ROOT / "ansible" / "roles").iterdir()):
        tasks_dir = role_dir / "tasks"
        if not tasks_dir.is_dir():
            continue
        text = "".join(f.read_text() for f in sorted(tasks_dir.rglob("*.yml")))
        loads = "confidential.yml" in text and "include_vars" in text
        if loads:
            continue
        used = sorted(
            key for key in documented
            if re.search(r"\b" + re.escape(key) + r"\b", text)
        )
        if used:
            findings.append(Finding(
                "confidential_loader",
                f"ansible/roles/{role_dir.name} reads {', '.join(used)} from "
                "ansible/confidential.yml but never loads the file - the "
                "variable stays undefined and any `| default(...)` fallback "
                "wins silently. Add the stat + include_vars pair the other "
                "roles use (see ansible/roles/mariadb/tasks/install.yml).",
            ))
    return findings


def main() -> int:
    profile = _load_profile()
    findings = (
        check_make_commands()
        + check_auto_fix_commands()
        + check_adr_index()
        + check_adr_supersede()
        + check_wp_state()
        + check_wp_version_view()
        + check_agent_status_vs_adr()
        + check_day0_day1_roles()
        + check_debug_make_commands()
        + check_gitops_values_clobber()
        + check_confidential_var_loaders()
        + check_version_consistency(profile)
        + check_model_roles()
        + check_doc_links()
        + check_model_context_windows()
    )

    print("Checked README.md Make commands, Ansible auto_fix commands, "
          "docs/adr/README.md index (status, target, section placement, row integrity), "
          "declared ADR supersessions, work-package state vs the roadmap tracker, "
          "the roadmap's by-version table against the ADR bodies, "
          "agent zuno.status vs its governing ADR(s), Makefile/ansible role "
          "consistency, make commands printed by debug tasks, GitOps Application values against the roles that replace them, "
          "roles reading ansible/confidential.yml variables without loading the file, "
          f"platform version prose against {PROFILE_PATH.relative_to(REPO_ROOT)}, "
          "model architectural roles against provider-routing.yaml/"
          "model-routing-policy.yaml, relative ADR links in ADR/roadmap/"
          "work-package markdown, and model context windows against "
          "gitops/charts/models/values.yaml.")
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
