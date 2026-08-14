# ADR-0111: Strengthen SecNumCloud-oriented security controls

- **Status:** Partially implemented - control matrix and first increment merged (`docs/security/secnumcloud-controls.md`, `platform/security/check_workload_hardening.py`'s new NetworkPolicy-coverage audit and hardcoded-secret check); the audit found and closed a real gap (`zuno-ai-run` was silently receiving an all-ports same-namespace NetworkPolicy, contradicting ADR-0037/0052's stated design - confirmed not yet live on the cluster, `policy.enabled` is currently false there). Remaining `gap` rows in the matrix belong to WP-12 (HA/PDB), WP-13 (backup), WP-26 (binding auth-mode enforcement) and live-cluster verification items (2026-08-14, roadmap WP-11)
- **Target:** v0.1
- **Date:** 2026-08-14
- **Decision owners:** Zuno Demo architecture team

## Decision

Promote this decision from a one-line v0.1-roadmap entry
(`0100-v0.1-roadmap.md`) to a full record.

Maintain a SecNumCloud-oriented control matrix at
`docs/security/secnumcloud-controls.md` mapping control families
(deployment, supply chain, identity, network, data) to their concrete
repo/cluster mechanisms and one of: `enforced-in-ci`,
`enforced-on-cluster`, `gap`. Each roadmap increment closes named
`gap` rows; CI-enforceable controls are added to
`platform/security/check_workload_hardening.py` (or a sibling checker)
so regressions block. The matrix is derived documentation - the
authoritative sources remain the policy/checker files it cites.

First increment (this WP): NetworkPolicy default-deny coverage for all
first-party namespaces; PodDisruptionBudget presence is WP-12's
concern; secrets-mount hardening checks (no hardcoded literal secret
values where `secretKeyRef` is required); image-provenance rows point
at ADR-0115.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Consequences, Security/Operational considerations,
Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0037](0037-protect-mcp-servers-with-network-and-workload-identity-boundaries.md)
- [ADR-0041](0041-remove-nominative-demo-identities-and-static-passwords-from-git.md)
- [ADR-0052](0052-harden-all-workloads-for-openshift-restricted-security-and-secnumcloud-objectives.md)
- [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md)
