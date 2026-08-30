#!/usr/bin/env python3
"""ADR-0202/ADR-0203 policy-as-code check: "Introduce logical knowledge
domains" / "Enforce knowledge authorization as policy intersection".
Validates that the declarative `knowledge/` contract is well-formed and
that nothing in the repository references a knowledge domain that doesn't
exist. No live cluster or registry needed - pure static text/YAML
inspection, mirroring `platform/docs/check_docs.py`'s structure/output.

Two checks, each independent (a failure in one doesn't block the other
from reporting):
  - domain_descriptors: every `knowledge/<domain>/domain.yaml` is valid
    YAML, declares the required top-level fields, its `id` matches its
    directory name, and it carries no physical database name, service
    endpoint, secret or credential (ADR-0202: "must not contain physical
    database names, service endpoints, secrets or credentials"). Also
    validates `knowledge/metadata-schema.yaml`'s own shape.
  - knowledge_refs: every `knowledge.<domain>` reference under `agents/`
    and `policies/` resolves to a descriptor declared in `knowledge/`.

Run from the repository root:

    python3 platform/docs/check_knowledge_refs.py
"""
from __future__ import annotations

import pathlib
import re
import sys
from dataclasses import dataclass
from typing import List, Set

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = REPO_ROOT / "knowledge"
METADATA_SCHEMA_PATH = KNOWLEDGE_DIR / "metadata-schema.yaml"
AGENTS_DIR = REPO_ROOT / "agents"
POLICIES_DIR = REPO_ROOT / "policies"

REQUIRED_DESCRIPTOR_FIELDS = (
    "id",
    "title",
    "description",
    "taxonomy",
    "freshness",
    "classification",
    "policy_ref",
)

# ADR-0202: descriptors "must not contain physical database names, service
# endpoints, secrets or credentials". Same intent as this check's own
# acceptance command (`! grep -rn "postgresql|svc.cluster.local" knowledge/`),
# kept in the checker itself so a future descriptor edit is caught locally
# too, not only by a separate ad hoc grep.
PHYSICAL_IDENTIFIER_RE = re.compile(
    r"postgresql|postgres|svc\.cluster\.local|mysql|mariadb|https?://|"
    r"vault/|secretName|secretRef",
    re.IGNORECASE,
)

# WP-24 (ADR-0109): freshness.operation_classes shape - a duration like
# "7d"/"4h"/"5m" or the literal "none" (never/no computed window, the
# knowledge.sxa-legacy convention).
MAX_STALENESS_RE = re.compile(r"^(\d+[dhm]|none)$")
REQUIRED_OPERATION_CLASSES = ("semantic-read", "current-state-read")

# Excludes source-file references like `app/knowledge.py` (a "/" right
# before "knowledge" means a path component, not a domain reference) and
# common non-domain file extensions immediately after the dot - no real
# domain id collides with any of these.
KNOWLEDGE_REF_RE = re.compile(
    r"(?<![\w/])knowledge\.(?!py\b|md\b|yaml\b|yml\b|json\b|sql\b)[a-z][a-z0-9_-]*\b"
)


@dataclass
class Finding:
    check: str
    message: str


def _known_domains() -> Set[str]:
    domains: Set[str] = set()
    if not KNOWLEDGE_DIR.is_dir():
        return domains
    for descriptor in sorted(KNOWLEDGE_DIR.glob("*/domain.yaml")):
        try:
            doc = yaml.safe_load(descriptor.read_text()) or {}
        except yaml.YAMLError:
            continue
        domain_id = doc.get("id")
        if isinstance(domain_id, str):
            domains.add(domain_id)
    return domains


def check_domain_descriptors() -> List[Finding]:
    findings: List[Finding] = []

    if not METADATA_SCHEMA_PATH.is_file():
        findings.append(Finding("domain_descriptors", f"{METADATA_SCHEMA_PATH.relative_to(REPO_ROOT)} does not exist"))
    else:
        try:
            schema = yaml.safe_load(METADATA_SCHEMA_PATH.read_text()) or {}
        except yaml.YAMLError as exc:
            findings.append(Finding("domain_descriptors", f"{METADATA_SCHEMA_PATH.relative_to(REPO_ROOT)}: invalid YAML ({exc})"))
            schema = {}
        if "common" not in schema or not isinstance(schema.get("common"), list):
            findings.append(Finding("domain_descriptors", f"{METADATA_SCHEMA_PATH.relative_to(REPO_ROOT)}: missing or malformed top-level 'common' list"))
        if "domains" not in schema or not isinstance(schema.get("domains"), dict):
            findings.append(Finding("domain_descriptors", f"{METADATA_SCHEMA_PATH.relative_to(REPO_ROOT)}: missing or malformed top-level 'domains' mapping"))

    if not KNOWLEDGE_DIR.is_dir():
        findings.append(Finding("domain_descriptors", f"{KNOWLEDGE_DIR.relative_to(REPO_ROOT)} does not exist"))
        return findings

    descriptor_dirs = sorted(p for p in KNOWLEDGE_DIR.iterdir() if p.is_dir())
    if not descriptor_dirs:
        findings.append(Finding("domain_descriptors", f"{KNOWLEDGE_DIR.relative_to(REPO_ROOT)} has no domain subdirectories"))

    for domain_dir in descriptor_dirs:
        descriptor_path = domain_dir / "domain.yaml"
        label = str(descriptor_path.relative_to(REPO_ROOT))
        if not descriptor_path.is_file():
            findings.append(Finding("domain_descriptors", f"{domain_dir.relative_to(REPO_ROOT)} has no domain.yaml"))
            continue

        text = descriptor_path.read_text()
        try:
            doc = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            findings.append(Finding("domain_descriptors", f"{label}: invalid YAML ({exc})"))
            continue

        for field in REQUIRED_DESCRIPTOR_FIELDS:
            if field not in doc:
                findings.append(Finding("domain_descriptors", f"{label}: missing required field '{field}'"))

        expected_id = f"knowledge.{domain_dir.name}"
        if doc.get("id") != expected_id:
            findings.append(Finding("domain_descriptors", f"{label}: id {doc.get('id')!r} does not match directory-derived id {expected_id!r}"))

        # WP-24 (ADR-0109): every domain's freshness block must declare an
        # allowed-staleness window per operation class - the thresholds
        # Agent Runtime's live-read trigger and rag-service's ingestion-
        # side enforcement are meant to come from (not code, per this
        # WP's ADR-0109 binding addition).
        freshness = doc.get("freshness")
        if isinstance(freshness, dict):
            operation_classes = freshness.get("operation_classes")
            if not isinstance(operation_classes, dict):
                findings.append(Finding("domain_descriptors", f"{label}: freshness.operation_classes is missing or not a mapping"))
            else:
                for op_class in REQUIRED_OPERATION_CLASSES:
                    entry = operation_classes.get(op_class)
                    if not isinstance(entry, dict) or "max_staleness" not in entry:
                        findings.append(Finding("domain_descriptors", f"{label}: freshness.operation_classes.{op_class}.max_staleness is missing"))
                        continue
                    value = entry["max_staleness"]
                    if not isinstance(value, str) or not MAX_STALENESS_RE.match(value):
                        findings.append(Finding("domain_descriptors", f"{label}: freshness.operation_classes.{op_class}.max_staleness={value!r} must be '<int>d', '<int>h', '<int>m', or 'none'"))

            # WP-100 (ADR-0105 amendment): an optional, additive per-source
            # cadence override for domains whose sources no longer share one
            # objective (knowledge.tech: product-doc weekly, confluence
            # hours-scale). freshness.objective above stays the domain-wide
            # aggregate/fallback. Each key here must name a real declared
            # source_class - the same typo-guard REQUIRED_OPERATION_CLASSES
            # gives operation_classes.
            by_source_class = freshness.get("by_source_class")
            if by_source_class is not None:
                if not isinstance(by_source_class, dict):
                    findings.append(Finding("domain_descriptors", f"{label}: freshness.by_source_class must be a mapping"))
                else:
                    taxonomy = doc.get("taxonomy")
                    declared_classes = set(taxonomy.get("source_classes") or []) if isinstance(taxonomy, dict) else set()
                    for source_class, entry in by_source_class.items():
                        if source_class not in declared_classes:
                            findings.append(Finding("domain_descriptors", f"{label}: freshness.by_source_class.{source_class} is not a declared taxonomy.source_classes entry"))
                        if not isinstance(entry, dict) or "objective" not in entry:
                            findings.append(Finding("domain_descriptors", f"{label}: freshness.by_source_class.{source_class}.objective is missing"))

        for lineno, line in enumerate(text.splitlines(), start=1):
            # Only the YAML content is checked, never comment text - a
            # descriptor's `related_adrs:` list legitimately references
            # other ADRs by their real historical titles (e.g. ADR-0016,
            # "Migrate the legacy SXA schema to PostgreSQL"), which is
            # commentary, not a physical binding.
            code = line.split("#", 1)[0]
            if not code.strip():
                continue
            match = PHYSICAL_IDENTIFIER_RE.search(code)
            if match:
                findings.append(Finding("domain_descriptors", f"{label}:{lineno}: contains a physical identifier ({match.group(0)!r}) - domain descriptors must stay logical (ADR-0202)"))

    return findings


def check_knowledge_refs() -> List[Finding]:
    findings: List[Finding] = []
    known_domains = _known_domains()

    for scan_root in (AGENTS_DIR, POLICIES_DIR):
        if not scan_root.is_dir():
            continue
        for path in sorted(scan_root.rglob("*")):
            if not path.is_file() or path.suffix not in (".md", ".yaml", ".yml"):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), start=1):
                for match in KNOWLEDGE_REF_RE.finditer(line):
                    ref = match.group(0)
                    if ref not in known_domains:
                        findings.append(Finding(
                            "knowledge_refs",
                            f"{path.relative_to(REPO_ROOT)}:{lineno}: unknown knowledge domain reference "
                            f"'{ref}' (not declared under knowledge/)",
                        ))
    return findings


def main() -> int:
    findings = check_domain_descriptors() + check_knowledge_refs()

    print("Checked knowledge/ domain descriptors against knowledge/metadata-schema.yaml, "
          "and scanned agents/ and policies/ for undeclared knowledge.* references.")
    if not findings:
        print("\nRESULT: PASS - no knowledge-domain contract issues found.")
        return 0

    print(f"\n{len(findings)} knowledge-domain issue(s) found:")
    for f in findings:
        print(f"  ✗ [{f.check}] {f.message}")
    print("\nRESULT: FAIL - reconcile knowledge/ descriptors and references (ADR-0202/ADR-0203).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
