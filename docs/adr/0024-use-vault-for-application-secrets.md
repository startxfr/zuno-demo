# ADR-0024: Use Vault for application secrets

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

## Context

Zuno Demo requires an explicit, reviewable architecture decision so implementation, security and roadmap work remain aligned across the MVP and future releases.

## Decision

Keep credentials and sensitive tokens out of Git and reference secrets through Vault-backed mechanisms.

**Hardened requirement (added 2026-08-04):** exactly one credential may be supplied by a human for the entire install — the OpenShift API endpoint and a cluster-admin token, passed to `make precheck`/`make prepare`. Every other secret (Keycloak admin, PostgreSQL, Google OAuth client, SMTP, MCP tool credentials) is sourced from Vault: in-cluster workloads consume secrets exclusively through the External Secrets Operator (`ExternalSecret` resources resolving from a `ClusterSecretStore` backed by this Vault instance), and Ansible bootstrap-time values use the `community.hashi_vault` lookup plugin — never a hand-typed value in a manifest, `group_vars`, or `-e` flag. Vault itself is the one component that cannot depend on Vault: the `vault` role initializes and auto-unseals it during `make prepare`, storing unseal keys and the root token in a locked-down, non-default-namespace Kubernetes `Secret` rather than requiring external input.

## Alternatives considered

Alternatives remain valid when documented in implementation discussions, but this ADR records the selected direction for the stated target release.

## Consequences

Implementation and documentation must follow this decision. Any material change requires a superseding ADR and an explicit migration/evolution note.

## Security considerations

Security implications must be evaluated during implementation. This decision must not weaken identity propagation, data classification, least privilege, secret management or auditability.

## Operational considerations

Operational checks, observability and rollback/diagnostic procedures must be added as the corresponding capability becomes executable.

## Migration / evolution

Future changes must be documented by a new ADR using `Supersedes ADR-0024` when applicable.

## Related ADRs

See [ADR index](README.md).
