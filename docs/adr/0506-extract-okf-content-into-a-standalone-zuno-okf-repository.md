# ADR-0506: Extract OKF content into a standalone zuno-okf repository

- **Status:** Proposed
- **Target:** v0.10 (retargeted from v0.7 on 2026-09-05 — opened a dedicated v0.10 band for the OKF extraction-and-reconciliation chain, separating it from v0.7's release/supply-chain automation scope; still gated on an owner-created `zuno-okf` GitHub repository not yet provisioned. Previously retargeted from OKF v0.2 on 2026-08-30 — folded the standalone OKF version line into the platform milestone sequence)
- **Date:** 2026-08-18
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0001 chose a monorepo, and for the platform it stands. But the OKF
content inside it — agent bundles, their schemas, the authorization
policy files, the evaluation scenarios — is a different kind of artifact:
it is the *definition* of who can use what, for what, under which
policies, authored and reviewed by people who govern agents, not by
people who build platform components. Today that content is spread over
`agents/`, `platform/okf/schema/`, `platform/templates/agent/
scaffold_agent.py`, `policies/tools/`, `policies/knowledge/` (and
`policies/quotas/` once ADR-0511 lands) and `evaluations/`, versioned in
lockstep with every unrelated component change. The `AIAgent` CR already
anticipates separation: its `okfBundleRef` is "a reference only: OKF
remains the sole source of task/prompt/behavioral content... never
mirrored into this CR" (`operator/aiagent-operator/CONTRACT.md`). The
OKF v0.1 work (ADR-0502–0505, 0511, 0512) makes the content coherent
enough to be worth extracting; this ADR extracts it.

## Decision

1. **A standalone git repository, `zuno-okf` (GitHub, same org, per
   ADR-0004), becomes the sole home of the OKF package.** It receives,
   with history preserved (subtree-split or filter-repo, executed by
   WP-48), these content roots at unchanged relative paths:
   - `agents/` — all bundles;
   - `platform/okf/schema/` — the JSON Schemas;
   - `platform/templates/agent/scaffold_agent.py` — the generator's
     bundle-and-evaluations half (clause 4);
   - `policies/tools/tool-policy.yaml`,
     `policies/knowledge/knowledge-policy.yaml`,
     `policies/quotas/quota-policy.yaml` — the authorization and quota
     policy set **is part of the versioned OKF package**: the package
     defines who/what/for-what and the governing rules together;
   - `evaluations/` — the per-agent scenario suites and gate configs.

2. **Named as staying in `zuno-demo`, deliberately:**
   `policies/data-classification/classification.yaml` (platform-wide
   data policy, not agent knowledge — MCP Gateway composes it with the
   package's policy files), `platform/bindings/` (physical backend
   bindings, ADR-0116's deployment-side half), all `gitops/` charts and
   Applications, the Keycloak realm (`keycloak-fragment.json` files move
   with their bundles; `realm-zuno.json` stays), the ADR-0342 evaluation
   *runner* (it exercises Agent Runtime and lives with it — `zuno-okf`
   holds scenarios, `zuno-demo` executes them), and every component,
   operator and Ansible role.

3. **Ownership and review rules:** `zuno-okf` changes are reviewed by
   agent/policy owners; any change touching `policies/` or a bundle's
   `access`/`allowed_*` frontmatter requires the same review rigor the
   monorepo applies to those files today (the generated ADR-0503
   matrices make the diff legible). The repository runs its own
   self-contained CI: schema validation, bundle validation, the ADR-0504
   contract suites, matrix/deployment-snapshot drift checks, policy lint
   — everything that needs only repository files. Nothing in `zuno-okf`
   CI needs a cluster or a component build.

4. **The scaffold generator splits into its two natural halves:** the
   bundle + evaluations rendering moves to `zuno-okf` (it writes only
   files that live there); the GitOps chart/Applications rendering stays
   in `zuno-demo` as a sibling script consuming the same `AgentSpec`
   input file, so onboarding a new agent becomes two small PRs — one per
   repository, each self-validating — instead of one monorepo PR. The
   scaffold-validate-discard CI test relocates with its half.

5. **Migration is strictly sequenced — mirror, pin, cutover** (WP-48,
   WP-49, WP-50): `zuno-okf` is bootstrapped as a mirror while
   `zuno-demo` remains authoritative; then `zuno-demo` builds consume
   the pinned `zuno-okf` ref (ADR-0507) while the in-repo copies still
   exist; only when pinned builds are proven identical is the content
   deleted from `zuno-demo`. At no point do both repositories accept
   edits to the same content — the okf-roadmap's cross-repo clause makes
   the interim single-writer rule binding on every WP.

## Consequences

Agent governance gets its own change stream, release cadence and review
audience; `zuno-demo` stops rebuilding six images because a prompt
changed a comma — rebuilds happen when the *pin* moves (ADR-0507). The
cost is real: cross-repo changes (a new tool capability plus the policy
entry granting it) become two coordinated PRs, and every consumer of the
moved files — Dockerfile COPY paths, `lint.yml` jobs, `check_docs.py`
reference checks, `build-publish.yml`'s sign-okf-bundles matrix — must
be repointed at cutover, which is exactly why WP-50 is a single,
minimal, prepared commit. This ADR narrows ADR-0001's monorepo scope for
OKF content only; it supersedes nothing else in it.

## Security considerations

The package repository inherits the same supply-chain posture as the
monorepo: OKF bundle signing (ADR-0106) signs `zuno-okf` content at the
pinned ref, and the sign-okf-bundles flow follows the content. Policy
files moving out of the platform repo must not weaken review: clause 3's
review rule exists precisely so that extraction never makes an
`allowed_groups` widening easier to land than it is today. Secrets never
enter `zuno-okf` — it holds definitions and fixtures only.

## Operational considerations

Two repositories mean two CI surfaces; the split in clause 3 keeps them
disjoint (self-contained validation there, builds/evaluations/deploys
here). The `zuno-okf` repository needs an owner-created GitHub project,
branch protection, and CODEOWNERS before WP-48 merges its bootstrap.

## Acceptance criteria

- `zuno-okf` exists with the clause-1 roots at unchanged paths, history
  preserved, self-contained CI green.
- After WP-50: none of the clause-1 roots remain in `zuno-demo`;
  clause-2's stay-list is intact; all `zuno-demo` references point at
  the pinned-ref fetch path; both repositories' CI pass.
- Onboarding a test agent produces two PRs via the split generators.

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0001](0001-use-a-monorepo-for-the-zuno-agent-platform.md) (scope narrowed for OKF content only)
- [ADR-0004](0004-use-github-as-the-canonical-source-repository.md)
- [ADR-0106](0106-enforce-okf-bundle-signing-and-validation.md)
- [ADR-0116](0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md)
- [ADR-0307](0307-support-self-service-agent-onboarding.md)
- [ADR-0327](0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md)
- [ADR-0507](0507-consume-the-zuno-okf-repository-through-a-single-pinned-reference.md)
- [ADR-0508](0508-isolate-okf-parsing-behind-per-component-adaptation-hooks.md)
