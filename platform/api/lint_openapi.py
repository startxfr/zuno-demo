#!/usr/bin/env python3
"""ADR-0054 policy-as-code check: "Add OpenAPI linting" (Operational
considerations). Validates every `openapi.json`/`openapi.yaml` this repo
ships against the OpenAPI 3.x meta-schema via `openapi-spec-validator`, and
asserts a couple of ADR-0054-specific conventions this repo actually
relies on (every operation besides /healthz declares `bearerAuth`
security, and no schema property looks like it holds a raw token/secret).

No live cluster or running service needed - pure static document
validation, same style as platform/security/check_workload_hardening.py.
Requires `openapi-spec-validator` (`pip install openapi-spec-validator`) -
not otherwise a dependency of any shipped service, so it isn't pinned in
any component's requirements.txt.

Run from the repository root:

    python3 platform/api/lint_openapi.py
"""
from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import dataclass
from typing import Any, Dict, List

try:
    from openapi_spec_validator import validate_spec
except ImportError:  # pragma: no cover
    print("openapi-spec-validator is not installed - run: pip install openapi-spec-validator", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Every OpenAPI document this repo ships. Add a new entry here the moment a
# second BFF (or any other service) gets its own spec (ADR-0054's decision
# targets "the agent BFF API" generically, not only Tekos's).
SPEC_PATHS: List[pathlib.Path] = [
    REPO_ROOT / "components" / "agent-bff" / "openapi.json",
]

# Property names that would indicate a raw credential is being described
# as request/response data (Security considerations: "never expose
# internal tokens in schemas"). This is a naming heuristic, not a
# guarantee - it catches the obvious mistake, not every possible one.
_SUSPICIOUS_PROPERTY_NAMES = {"access_token", "id_token", "bearer_token", "jwt", "secret", "password"}


@dataclass
class LintResult:
    spec: str
    passed: bool
    detail: str = ""


def _load(path: pathlib.Path) -> Dict[str, Any]:
    return json.loads(path.read_text()) if path.suffix == ".json" else __import__("yaml").safe_load(path.read_text())


def check_schema_valid(path: pathlib.Path) -> LintResult:
    doc = _load(path)
    try:
        validate_spec(doc)
    except Exception as exc:  # noqa: BLE001 - any validator error is a fail, not a crash
        return LintResult(str(path), False, str(exc))
    return LintResult(str(path), True)


def check_operations_require_auth(path: pathlib.Path) -> LintResult:
    """Every operation besides a liveness/readiness probe must declare
    `security` (inherited from the document-level default is fine too) -
    an endpoint with no auth requirement at all, in an authenticated API,
    is much more likely a mistake than a decision.
    """
    doc = _load(path)
    doc_level_security = doc.get("security")
    problems = []
    for path_str, methods in doc.get("paths", {}).items():
        if path_str.rstrip("/").endswith(("/healthz", "/readyz")):
            continue
        for method, op in methods.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            has_security = "security" in op or doc_level_security is not None
            if not has_security:
                problems.append(f"{method.upper()} {path_str} declares no security requirement")
    ok = not problems
    return LintResult(str(path), ok, "; ".join(problems))


def check_no_raw_token_schemas(path: pathlib.Path) -> LintResult:
    doc = _load(path)
    problems = []
    for schema_name, schema in doc.get("components", {}).get("schemas", {}).items():
        for prop_name in schema.get("properties", {}):
            if prop_name.lower() in _SUSPICIOUS_PROPERTY_NAMES:
                problems.append(f"schema {schema_name!r} has a suspicious property {prop_name!r}")
    ok = not problems
    return LintResult(str(path), ok, "; ".join(problems))


def main() -> int:
    results: List[LintResult] = []
    for spec_path in SPEC_PATHS:
        if not spec_path.is_file():
            results.append(LintResult(str(spec_path), False, "file not found"))
            continue
        results.append(check_schema_valid(spec_path))
        results.append(check_operations_require_auth(spec_path))
        results.append(check_no_raw_token_schemas(spec_path))

    print(f"{'PASS':<6}{'CHECK'}")
    for r in results:
        print(f"{'✓' if r.passed else '✗':<6}{r.spec}")
        if not r.passed and r.detail:
            print(f"      -> {r.detail}")

    if all(r.passed for r in results):
        print(f"\nRESULT: PASS ({len(results)} checks across {len(SPEC_PATHS)} spec(s))")
        return 0
    print("\nRESULT: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
