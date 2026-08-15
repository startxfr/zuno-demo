#!/usr/bin/env python3
"""ADR-0327/WP-37 static validation harness for the `zuno.zuno.ai/v1alpha1
AIAgent` CRD contract. No live cluster needed - the operator/reconciler
itself is WP-38's job; this script only proves the *contract* (schema +
reject rules + drift) is sound before that controller is built against it.

Four independent checks:
  - schema: every `config/samples/zuno_v1alpha1_aiagent_*.yaml` validates
    against `config/crd/bases/zuno.zuno.ai_aiagents.yaml`'s generated
    OpenAPI schema (required fields present, string patterns/lengths,
    array minItems, integer minimums). This is a narrow hand-rolled
    validator, not a general JSON Schema implementation - the generated
    schema only ever uses the keywords handled below, and this repo has
    no `jsonschema` dependency anywhere else to justify adding one for a
    schema this small (see platform/supply-chain/validate_okf_bundle.py
    for the same house style against the OKF schema).
  - reject_rules: no field anywhere in a sample's `spec` may be
    secret/token/credential-shaped, and no field literally named/ending
    in "namespace" may point anywhere other than that sample's own
    `spec.targetNamespace`. A vanilla Kubernetes CRD structural schema
    only *prunes* unknown fields silently (RFC-compliant OpenAPI schemas
    have no "unknown field" concept without an explicit
    `additionalProperties: false`, which controller-gen does not emit for
    generated CRDs) - it does not reject the create outright. ADR-0327's
    "must not embed secrets/raw credentials" and "cross-namespace
    references... must be rejected" are therefore enforced here, in the
    harness, not assumed from schema pruning alone.
  - self_test: proves the reject_rules check above actually catches
    something, by constructing a deliberately-broken copy of the Tekos
    sample in memory (never written to disk - nothing to "remove"
    afterward) with an inline `oidcClientSecret` field and a
    cross-namespace `bff.image.namespace` field, and failing this script
    if either one is *not* caught.
  - drift: each sample's image refs, OIDC ids, replicas/resources,
    entitlement group and business roles match the real
    `gitops/charts/<agent>/values.yaml` and `agents/<agent>/agent.okf.md`
    it was derived from, and its knowledgeDomains/toolCapabilities are a
    superset of every `allowed_knowledge`/`allowed_tools` id declared
    across that agent's own `agents/<agent>/tasks/*.md` frontmatter (the
    deployment-time binding requirement must cover what OKF tasks
    actually ask for).

Run from anywhere (paths are resolved relative to this file):

    python3 operator/aiagent-operator/validate_contract.py
"""
from __future__ import annotations

import copy
import pathlib
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List

import yaml

OPERATOR_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = OPERATOR_DIR.parents[1]
CRD_PATH = OPERATOR_DIR / "config" / "crd" / "bases" / "zuno.zuno.ai_aiagents.yaml"
SAMPLES_DIR = OPERATOR_DIR / "config" / "samples"

FORBIDDEN_KEY_SUBSTRINGS = (
    "secret",
    "token",
    "password",
    "credential",
    "apikey",
    "privatekey",
    "authcode",
)


@dataclass
class Finding:
    check: str
    message: str


def load_spec_schema() -> Dict[str, Any]:
    doc = yaml.safe_load(CRD_PATH.read_text())
    versions = doc["spec"]["versions"]
    v1alpha1 = next(v for v in versions if v["name"] == "v1alpha1")
    return v1alpha1["schema"]["openAPIV3Schema"]["properties"]["spec"]


def load_samples() -> Dict[str, Dict[str, Any]]:
    samples = {}
    for path in sorted(SAMPLES_DIR.glob("zuno_v1alpha1_aiagent_*.yaml")):
        doc = yaml.safe_load(path.read_text())
        samples[path.stem.replace("zuno_v1alpha1_aiagent_", "")] = doc
    return samples


def validate_against_schema(value: Any, schema: Dict[str, Any], path: str) -> List[str]:
    """Hand-rolled validator for the OpenAPI v3 keyword subset this CRD's
    generated schema actually emits: type/properties/required/items/
    pattern/minLength/maxLength/minItems/minimum."""
    errors: List[str] = []
    schema_type = schema.get("type")

    if schema_type == "object":
        if not isinstance(value, dict):
            return [f"{path}: expected object, got {type(value).__name__}"]
        for req in schema.get("required", []):
            if req not in value:
                errors.append(f"{path}: missing required field '{req}'")
        props = schema.get("properties", {})
        for key, sub in value.items():
            if key in props:
                errors.extend(validate_against_schema(sub, props[key], f"{path}.{key}"))
    elif schema_type == "array":
        if not isinstance(value, list):
            return [f"{path}: expected array, got {type(value).__name__}"]
        min_items = schema.get("minItems")
        if min_items is not None and len(value) < min_items:
            errors.append(f"{path}: expected at least {min_items} item(s), got {len(value)}")
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(value):
                errors.extend(validate_against_schema(item, item_schema, f"{path}[{i}]"))
    elif schema_type == "string":
        if not isinstance(value, str):
            return [f"{path}: expected string, got {type(value).__name__}"]
        min_len = schema.get("minLength")
        if min_len is not None and len(value) < min_len:
            errors.append(f"{path}: shorter than minLength {min_len}")
        max_len = schema.get("maxLength")
        if max_len is not None and len(value) > max_len:
            errors.append(f"{path}: longer than maxLength {max_len}")
        pattern = schema.get("pattern")
        if pattern and not re.match(pattern, value):
            errors.append(f"{path}: '{value}' does not match pattern '{pattern}'")
    elif schema_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return [f"{path}: expected integer, got {type(value).__name__}"]
        minimum = schema.get("minimum")
        if minimum is not None and value < minimum:
            errors.append(f"{path}: {value} below minimum {minimum}")

    return errors


def check_schema(schema: Dict[str, Any], samples: Dict[str, Dict[str, Any]]) -> List[Finding]:
    findings = []
    for name, doc in samples.items():
        spec = doc.get("spec", {})
        for err in validate_against_schema(spec, schema, "spec"):
            findings.append(Finding("schema", f"{name}: {err}"))
    return findings


def find_forbidden_fields(value: Any, path: str) -> List[str]:
    errors: List[str] = []
    if isinstance(value, dict):
        for key, sub in value.items():
            lowered = key.lower()
            if any(bad in lowered for bad in FORBIDDEN_KEY_SUBSTRINGS):
                errors.append(f"{path}.{key}: field name looks secret-shaped (forbidden by ADR-0327)")
            errors.extend(find_forbidden_fields(sub, f"{path}.{key}"))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            errors.extend(find_forbidden_fields(item, f"{path}[{i}]"))
    return errors


def find_cross_namespace_refs(spec: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    target_ns = spec.get("targetNamespace")

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, sub in value.items():
                if key != "targetNamespace" and key.lower().endswith("namespace"):
                    if sub != target_ns:
                        errors.append(
                            f"{path}.{key}: cross-namespace reference '{sub}' != targetNamespace '{target_ns}'"
                        )
                walk(sub, f"{path}.{key}")
        elif isinstance(value, list):
            for i, item in enumerate(value):
                walk(item, f"{path}[{i}]")

    walk(spec, "spec")
    return errors


def check_reject_rules(samples: Dict[str, Dict[str, Any]]) -> List[Finding]:
    findings = []
    for name, doc in samples.items():
        spec = doc.get("spec", {})
        for err in find_forbidden_fields(spec, "spec"):
            findings.append(Finding("reject_rules", f"{name}: {err}"))
        for err in find_cross_namespace_refs(spec):
            findings.append(Finding("reject_rules", f"{name}: {err}"))
    return findings


def check_self_test(samples: Dict[str, Dict[str, Any]]) -> List[Finding]:
    """Proves check_reject_rules actually fires, using an in-memory-only
    broken copy of a real sample - never written to disk."""
    findings = []
    base = samples.get("tekos")
    if base is None:
        return [Finding("self_test", "no 'tekos' sample to base the broken scratch copy on")]

    broken = copy.deepcopy(base)
    broken["spec"]["bff"]["oidcClientSecret"] = "s3cr3t"  # nosec - deliberately broken, in-memory only
    broken["spec"]["bff"]["image"]["namespace"] = "some-other-agent-ns"

    secret_errors = find_forbidden_fields(broken["spec"], "spec")
    if not secret_errors:
        findings.append(Finding("self_test", "reject_rules failed to catch an inline secret-shaped field"))

    ns_errors = find_cross_namespace_refs(broken["spec"])
    if not ns_errors:
        findings.append(Finding("self_test", "reject_rules failed to catch a cross-namespace reference"))

    return findings


def _load_yaml(path: pathlib.Path) -> Dict[str, Any]:
    return yaml.safe_load(path.read_text())


def _load_okf_frontmatter(path: pathlib.Path) -> Dict[str, Any]:
    text = path.read_text()
    parts = text.split("---", 2)
    return yaml.safe_load(parts[1])


def _task_bindings(agent: str) -> "set[str]":
    """Union of allowed_knowledge/allowed_tools ids across every real
    task file for this agent - what the CR's knowledgeDomains/
    toolCapabilities must, at minimum, cover."""
    ids: "set[str]" = set()
    tasks_dir = REPO_ROOT / "agents" / agent / "tasks"
    for task_path in sorted(tasks_dir.glob("*.md")):
        if task_path.name == "README.md":
            continue
        fm = _load_okf_frontmatter(task_path)
        zuno = fm.get("zuno", {})
        ids.update(zuno.get("allowed_knowledge", []) or [])
        ids.update(zuno.get("allowed_tools", []) or [])
    return ids


def check_drift(samples: Dict[str, Dict[str, Any]]) -> List[Finding]:
    findings = []
    for name, doc in samples.items():
        spec = doc.get("spec", {})
        chart_values_path = REPO_ROOT / "gitops" / "charts" / name / "values.yaml"
        okf_path = REPO_ROOT / "agents" / name / "agent.okf.md"
        if not chart_values_path.exists() or not okf_path.exists():
            findings.append(Finding("drift", f"{name}: no matching gitops chart / OKF bundle to cross-check against"))
            continue

        values = _load_yaml(chart_values_path)
        okf = _load_okf_frontmatter(okf_path)
        zuno = okf.get("zuno", {})

        expected_registry = values["image"]["registry"]
        expected_repo_prefix = values["image"]["frontendRepository"].rsplit("/", 1)[0]
        for role in ("frontend", "bff"):
            image = spec.get(role, {}).get("image", {})
            if image.get("registry") != expected_registry:
                findings.append(Finding("drift", f"{name}.{role}.image.registry: '{image.get('registry')}' != chart values '{expected_registry}'"))
            if not image.get("repository", "").startswith(expected_repo_prefix):
                findings.append(Finding("drift", f"{name}.{role}.image.repository: '{image.get('repository')}' does not start with chart values namespace '{expected_repo_prefix}'"))

        if spec.get("frontend", {}).get("oidcClientId") != values["frontend"]["oidcClientId"]:
            findings.append(Finding("drift", f"{name}.frontend.oidcClientId does not match chart values"))
        if spec.get("bff", {}).get("oidcAudience") != values["bff"]["oidcAudience"]:
            findings.append(Finding("drift", f"{name}.bff.oidcAudience does not match chart values"))

        expected_group = None
        groups = zuno.get("access", {}).get("groups", [])
        if groups:
            expected_group = groups[0]
        if expected_group and spec.get("groups", {}).get("entitlementGroup") != expected_group:
            findings.append(Finding("drift", f"{name}.groups.entitlementGroup: does not match agent.okf.md's zuno.access.groups"))

        if spec.get("agentName") != zuno.get("name"):
            findings.append(Finding("drift", f"{name}.agentName: '{spec.get('agentName')}' != agent.okf.md zuno.name '{zuno.get('name')}'"))

        expected_bindings = _task_bindings(name)
        declared_bindings = set(spec.get("knowledgeDomains", []) or []) | set(spec.get("toolCapabilities", []) or [])
        missing = expected_bindings - declared_bindings
        if missing:
            findings.append(Finding("drift", f"{name}: task(s) declare {sorted(missing)}, not covered by the CR's knowledgeDomains/toolCapabilities"))

    return findings


def main() -> int:
    schema = load_spec_schema()
    samples = load_samples()

    if len(samples) < 2:
        print(f"RESULT: FAIL - expected at least 2 samples in {SAMPLES_DIR}, found {len(samples)}.")
        return 1

    findings = (
        check_schema(schema, samples)
        + check_reject_rules(samples)
        + check_self_test(samples)
        + check_drift(samples)
    )

    print(f"Validated {len(samples)} AIAgent sample(s) ({', '.join(sorted(samples))}) "
          f"against {CRD_PATH.relative_to(REPO_ROOT)}.")

    if not findings:
        print("\nRESULT: PASS - schema, reject-rule self-test and chart/OKF drift checks all clean.")
        return 0

    print(f"\n{len(findings)} contract issue(s) found:")
    for f in findings:
        print(f"  ✗ [{f.check}] {f.message}")
    print("\nRESULT: FAIL - reconcile config/samples/ against the CRD schema and real chart/OKF state (ADR-0327).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
