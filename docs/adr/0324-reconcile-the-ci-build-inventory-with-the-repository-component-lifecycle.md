# ADR-0324: Reconcile the CI build inventory with the repository component lifecycle

- **Status:** Implemented - see `.github/workflows/build-publish.yml` (stale `postgresql-pgvector` matrix entry removed).
- **Target:** v0
- **Date:** 2026-08-11
- **Decision owners:** Zuno Demo architecture team

## Context

The repository migrated PostgreSQL from a custom `postgresql-pgvector` image to the Crunchy PGO-managed PostgreSQL operand. Commit history removed `gitops/charts/postgresql/image/Dockerfile`, but `.github/workflows/build-publish.yml` still contains the old build matrix entry:

```yaml
- name: postgresql-pgvector
  dockerfile: gitops/charts/postgresql/image/Dockerfile
  context: gitops/charts/postgresql/image
```

The workflow therefore contains a build target that cannot exist in the current repository. This is not only a one-line CI defect: it shows that the build inventory can drift independently from architectural component removal/replacement.

ADR-0115 requires a verifiable software supply chain; that guarantee is weakened if the CI inventory is not reconciled with the set of actual first-party build artifacts.

## Decision

Reconcile `.github/workflows/build-publish.yml` with the current component lifecycle and make such reconciliation enforceable.

### Immediate reconciliation

Remove `postgresql-pgvector` from the build/publish matrix. PostgreSQL is now supplied and lifecycle-managed through Crunchy PGO and must not be rebuilt or republished as a Zuno first-party image unless a future ADR explicitly introduces a new custom operand image.

### Build-inventory rule

The CI image inventory contains **only first-party Zuno images with an existing, tracked build context and Dockerfile**. Operator/vendor operand images are consumed from their approved upstream registries and are outside the Zuno image-build matrix.

### Preventive validation

Before any matrix build starts, CI must validate every declared entry:

- Dockerfile exists;
- build context exists;
- image name is unique;
- the target is still referenced by a Zuno deployable component or is explicitly documented as a build-only artifact;
- removed/replaced components do not remain as stale matrix entries.

Repository acceptance should also detect first-party Dockerfiles that are expected to be published but are absent from the declared inventory.

## Consequences

The build workflow becomes an accurate projection of the repository's current first-party software artifacts. Component migrations such as custom PostgreSQL -> operator-managed PostgreSQL cannot silently leave a permanently broken release job.

Maintainers must update the build inventory as part of any component add/remove/replace change.

## Security considerations

The reconciliation must not encourage rebuilding trusted vendor/operator operand images. Zuno should preserve upstream provenance and signatures for Red Hat/operator-provided images rather than inserting them into the custom image pipeline.

## Operational considerations

The build inventory/path validation must run without registry credentials so stale entries fail early on pull requests. Registry login, image publication, SBOM, scanning and signing remain downstream steps governed by ADR-0115.

## Acceptance criteria

- `postgresql-pgvector` is removed from `.github/workflows/build-publish.yml`.
- Every remaining matrix Dockerfile/context exists in the repository.
- A CI preflight fails when a declared Dockerfile/context is missing.
- A CI/repository check identifies an expected first-party build artifact that is absent from the inventory.
- The corrected build inventory becomes a prerequisite for moving ADR-0115 from `Partially implemented` back to `Implemented`.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0015](0015-use-postgresql-and-pgvector-as-the-persistent-data-platform.md)
- [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md)
- [ADR-0053](0053-make-make-check-an-end-to-end-acceptance-and-security-gate.md)
- [ADR-0315](0315-dedicated-keycloak-postgresql-database.md)
