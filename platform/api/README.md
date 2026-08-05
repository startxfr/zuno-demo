# Platform: API contracts

Cross-service API contract policy (ADR-0054: "Define the BFF contract
OpenAPI-first").

`lint_openapi.py` is the policy-as-code check that ADR's Operational
considerations ask for ("Add OpenAPI linting"): validates every OpenAPI
document this repo ships (currently
`components/agent-bff/openapi.json`) against the OpenAPI 3.x meta-schema,
plus two ADR-0054-specific conventions - every non-health operation
declares a security requirement, and no schema property name looks like it
holds a raw token/secret (Security considerations: "never expose internal
tokens in schemas"). No live cluster or running service needed - pure
static document validation, same style as
`platform/security/check_workload_hardening.py`.

```bash
pip install openapi-spec-validator
python3 platform/api/lint_openapi.py
```

Per-service field-level drift (does the Go/Python code's actual wire
shape still match the spec) is checked separately, per service, closer to
the code it's checking - see `components/agent-bff/README.md`'s "OpenAPI
contract" section for that service's `contract_test.go`.

Not wired into a CI pipeline - `.github/workflows/` doesn't exist yet in
this repository (see `.github/README.md`) - but written to be CI-usable
(non-zero exit on failure) the moment one does.
