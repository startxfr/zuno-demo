# WP-329: Inventory the dependencies and licences, and document exit paths

- **State:** Not started (proposed by ADR-0625 on 2026-11-21; the ADR is `Proposed`, so this work package is not approved)
- **ADRs:** [ADR-0625](../../adr/0625-evolve-zuno-toward-a-modular-sovereign-enterprise-ai-platform.md)
- **Depends on:** none
- **Related:** [ADR-0607](../../adr/0607-pin-gate-and-schedule-pre-ga-dependencies.md), [ADR-0120](../../adr/0120-implement-a-multi-provider-git-forge-mcp-server-for-github-and-gitlab.md), [ADR-0535](../../adr/0535-adopt-rhtas-as-the-artifact-trust-and-supply-chain-service.md), [ADR-0578](../../adr/0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md)
- **Target:** v0.19
- **Estimated files touched:** ~4: an inventory page, this brief

## Goal

An inventory of the platform's dependencies with licences, and a practical exit or replacement path for the strategically significant ones.

Horizon in the ADR's indicative roadmap: across the horizons. The horizons count from the start of an approved initiative. They are not calendar dates.

## Proposed work

1. List the dependencies: source code, container images, operators, runtimes, model weights, datasets, build services.
2. Assess licences and redistribution rights.
3. Document, for each significant dependency, the switching cost, functional parity, support implications and residual risks.

## Existing work it builds on

- The known-good file of [ADR-0607](../../adr/0607-pin-gate-and-schedule-pre-ga-dependencies.md), the GitHub and GitLab support of [ADR-0120](../../adr/0120-implement-a-multi-provider-git-forge-mcp-server-for-github-and-gitlab.md) and RHTAS ([ADR-0535](../../adr/0535-adopt-rhtas-as-the-artifact-trust-and-supply-chain-service.md)).
- The build-time signer: OKF artifacts are signed keyless with a GitHub OIDC identity ([ADR-0578](../../adr/0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md)).

## Acceptance

- Every dependency of the cluster's inventory has a licence and an owner.
- Each candidate path of section 1.6 of the ADR has a written assessment.
