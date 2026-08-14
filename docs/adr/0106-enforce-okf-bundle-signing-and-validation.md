# ADR-0106: Enforce OKF bundle signing and validation

- **Status:** Partially implemented - signing/validation tooling and enforcement paths merged (`platform/supply-chain/sign_okf_bundle.py`, `validate_okf_bundle.py`, `components/agent-runtime/app/registry.py`'s `ZUNO_REQUIRE_SIGNED_BUNDLES` gate); first real signed bundle pending WP-04 stage 2 (2026-08-14, roadmap WP-05)
- **Target:** v0.1
- **Date:** 2026-08-14
- **Decision owners:** Zuno Demo architecture team

## Decision

Promote this decision from a one-line v0.1-roadmap entry
(`0100-v0.1-roadmap.md`) to a full record, since WP-04's supply-chain
tooling makes it concretely implementable.

Sign every OKF agent bundle (the per-agent content under `agents/<agent>/`)
in CI with keyless Cosign over a canonical bundle digest, and validate
before any promotion or load: (1) signature and signer identity,
(2) OKF schema validity, (3) policy validity - declared tools and
knowledge references must resolve against the platform policy files.
Both the Day 1 agents check (`ansible/roles/agents`) and the Agent
Runtime registry startup refuse a bundle that fails any of the three
checks (fail closed). Signing keys/identity follow ADR-0115's keyless
GitHub OIDC convention; no key material enters Git.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Consequences, Security/Operational considerations,
Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0022](0022-use-gitops-managed-declarative-agent-tasks-and-policies.md)
- [ADR-0038](0038-use-standards-compliant-okf-v0-2-markdown-bundles.md)
- [ADR-0039](0039-make-agent-runtime-execute-the-okf-agent-contract.md)
- [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md)
