# ADR-0576: Extract agent definitions and corp policies into the zuno-demo-agents repository

- **Status:** Implemented (2026-10-23, WP-158 and WP-165) - see `platform/okf/agents.lock`, `platform/okf/release_cache.py` and the implementation note below
- **Target:** v0.12
- **Date:** 2026-10-22
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0506](0506-extract-okf-content-into-a-standalone-zuno-okf-repository.md), [ADR-0507](0507-consume-the-zuno-okf-repository-through-a-single-pinned-reference.md), [ADR-0510](0510-make-the-aiagent-operator-watch-the-zuno-okf-repository.md)
- **Related:** [ADR-0001](0001-use-a-monorepo-for-the-zuno-agent-platform.md), [ADR-0005](0005-use-okf-v0-2-as-the-declarative-agent-definition-contract.md), [ADR-0513](0513-give-okf-rag-tools-and-policies-directories-a-real-schema.md), [ADR-0561](0561-adopt-unifai-as-the-agent-platform.md), [ADR-0564](0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md), [ADR-0577](0577-publish-okf-as-per-agent-artifacts-plus-a-corp-index-artifact.md), [ADR-0578](0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md), [ADR-0579](0579-extend-okf-to-v0-3-with-skills-model-roles-guardrails-and-limits.md), [ADR-0580](0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md), [ADR-0581](0581-derive-stack-configuration-from-the-admitted-corp-bundle.md)

## Context

The eight agent bundles (`agents/<name>/`, OKF v0.2 per ADR-0005 and
ADR-0038) live in the `zuno-demo` monorepo and are versioned in lockstep with
every unrelated platform change. The rules that bound them live beside them
but outside `agents/`: `policies/tools/tool-policy.yaml`,
`policies/knowledge/knowledge-policy.yaml`, `policies/quotas/quota-policy.yaml`,
`policies/model-routing/model-routing-policy.yaml` and `policies/guardrails/`.
The tooling that validates them is spread over `platform/okf/` (schemas,
authorization matrix, quota lint, contract-test runner) and
`platform/supply-chain/validate_okf_bundle.py`.

ADR-0506, ADR-0507 and ADR-0510 (all `Proposed`, never implemented) planned
the extraction into a `zuno-okf` repository consumed through a pinned git
reference, with the AIAgent operator polling that repository. Since then:

- ADR-0561 retires agent-runtime, agent-bff, agent-frontend and the AIAgent
  operator in favour of UnifAI, so the git-polling operator of ADR-0510 has
  no future host;
- ADR-0564 already delivers a bundle to `unifai-operator` as a signed OCI
  artifact pinned by digest, which makes a git reference the wrong unit of
  consumption: the cluster consumes artifacts, not trees;
- the definitions people want to govern have grown beyond `agents/`: model
  preferences, quotas, guardrails and limits are policy files today, edited
  through platform pull requests by people who are not platform engineers.

The `zuno-okf` repository was never created. The user decision of
2026-10-22 names the repository `startxfr/zuno-demo-agents` (public, like
`zuno-demo`), with its git history preserved.

## Decision

**1. `startxfr/zuno-demo-agents` is the sole source of agent definitions and
of the corp policies that bound them.** It receives, at unchanged relative
paths and with history preserved (`git filter-repo`):

- `agents/<name>/`: `agent.okf.md`, `tasks/`, `prompts/`, `tools/`, `rag/`,
  `policies/` and `tests/` (and `skills/` once ADR-0579 lands);
- the corp policy set: `policies/tools/tool-policy.yaml`,
  `policies/knowledge/knowledge-policy.yaml`,
  `policies/quotas/quota-policy.yaml`,
  `policies/model-routing/model-routing-policy.yaml`, `policies/guardrails/`;
- the OKF tooling: `platform/okf/schema/*.json`,
  `platform/okf/generate_authorization_matrix.py`,
  `platform/okf/validate_quota_policy.py`,
  `platform/okf/run_agent_contract_tests.py`,
  `platform/supply-chain/validate_okf_bundle.py`, and the bundle half of
  `platform/templates/agent/scaffold_agent.py`.

"Corp" names the organisation-wide layer: what every agent may at most do.
An agent bundle can only narrow it (ADR-0579 clause 5).

**2. Stays in `zuno-demo`, deliberately.** The model catalog
(`platform/ai-gateway/provider-routing.yaml`), the physical tool bindings
(`platform/bindings/`), `policies/{data-classification,optimization,database}/`,
`evaluations/` (scenarios and runner), every chart, Application and Ansible
role, and the Keycloak realm. These describe what the platform *offers*, not
what an agent *is*.

**3. Dropped rather than moved.** `agents/*/deployment/` holds snapshots
rendered from the charts back into the bundles (chart to agent, the reverse
of the new flow); it stays in `zuno-demo` next to the charts if still useful.
`agents/{cognos,naveo,soursage}/keycloak-fragment.json` is replaced by the
generator of ADR-0581. `agents/zuno-platform-signer.pub` leaves the OKF path
with the Transit key (ADR-0578).

**4. A platform capability contract is the boundary.** `zuno-demo`
generates `platform-contract.json` from what it offers: the model roles of
`provider-routing.yaml`, the tool capabilities bound in `platform/bindings/`,
the knowledge domains actually served, and the classification levels. The
agents repository validates every change against a pinned copy of that
contract, which replaces the cross-tree lookups the monorepo allowed
(`generate_authorization_matrix.py` reading `provider-routing.yaml`
directly). `zuno-demo` re-validates the admitted bundle against its current
contract (ADR-0580 clause 3). A contract bump in the agents repository is an
ordinary reviewed pull request.

**5. Review and CI are self-contained.** CODEOWNERS give `policies/` and any
bundle's `access`/`allowed_*` frontmatter to agent and policy owners. The
repository's CI runs schema validation, `validate_okf_bundle.py`, the
ADR-0504 contract suites, the authorization-matrix drift check and the
quota-policy lint, with no cluster and no checkout of `zuno-demo`.

**6. Single writer during transition.** From the bootstrap to the cutover
(WP-158 to WP-165), `agents/` and the moved policies stay in `zuno-demo` as a
frozen mirror: a CI check fails if their content diverges from the admitted
corp bundle. Edits happen only in `zuno-demo-agents`.

**7. Supersessions.** This record replaces ADR-0506 (scope, repository name,
ownership), ADR-0507 (a pinned git reference becomes a pinned OCI digest,
ADR-0580) and ADR-0510 (a git-polling operator becomes digest promotion by
pull request, ADR-0580).

## Amendment (2026-10-22) - independent life cycles, as bootstrapped

Corrected while `Accepted`, the same day, before any consumer exists, after
the user set the boundary between the two repositories: the agents
repository has its own life cycle and knows nothing about `zuno-demo`; the
only link is that `zuno-demo` consumes a release. Every other clause stands.

- **Clause 4, the boundary contract, is reversed.** The agents repository
  defines its own vocabulary in its corp policies; it no longer validates
  against a `platform-contract.json` exported by `zuno-demo`. The model
  vocabulary becomes a corp policy, `policies/models/model-catalog.yaml`:
  logical model names with `kind`, `model`, `role` and `eligible_for`,
  seeded from `platform/ai-gateway/provider-routing.yaml` without endpoints
  or credentials; `model-routing-policy.yaml` prefers those names and the
  authorization matrices are generated from them. `zuno-demo` keeps the
  last word at admission (ADR-0580 clause 3): it refuses a release naming a
  model, tool capability or knowledge domain it cannot serve, which is the
  same check `platform/bindings/` already gives tools.
- **Clause 1, moved content.** The Vault Transit scripts
  (`sign_okf_bundle.py`, `publish_okf_bundle.py`) were not carried over:
  releases are signed keyless (ADR-0578). The release tooling is new,
  `platform/release/okf_release.py`.
- **Versions.** `VERSION` is the release version and
  `agents/<name>/VERSION` each agent's own version, both bumped by hand on
  `devel`. The per-agent version is a file, not a `zuno.version` key: the
  OKF schemas, and the copies `unifai-operator` embeds, refuse unknown
  `zuno` keys, so a new key would invalidate every live bundle.
- **Branches.** `devel` (direct push), `main` (pull requests from `devel`
  only; every merge is a release), `stable` and the release tags (written
  only by the release GitHub App, never moved). The repository's
  `RELEASING.md` is the reference.
- **Bootstrap record.** Extracted on 2026-10-22 from `demo222` at
  `9b5507c6`, 120 commits of history kept, into
  `/home/cl/ClaudeCode/zuno-demo-agents` (WP-158). The extraction also
  regenerated the authorization matrices, which in `zuno-demo` had not
  picked up the `ocp-ai-ops` group `tool-policy.yaml` already allowed.

## Implementation note (2026-10-23) - the cutover (WP-165)

- **Clause 1.** `startxfr/zuno-demo-agents` is the only source: `agents/`,
  `policies/{tools,knowledge,quotas,model-routing,guardrails}/`,
  `platform/okf/schema/`, `generate_authorization_matrix.py`,
  `validate_quota_policy.py`, `run_agent_contract_tests.py` and
  `platform/supply-chain/validate_okf_bundle.py` are deleted from
  `zuno-demo` (each present in the agents repository). `scaffold_agent.py`
  keeps only its platform half, the evaluation skeleton.
- **Clause 2.** `policies/{data-classification,optimization,database}/`,
  the model catalog, the bindings and `evaluations/` stay.
- **Clause 3.** `agents/*/deployment/` is dropped rather than kept: the
  per-agent charts it mirrored were retired by WP-156, and with them
  `generate_deployment_snapshot.py`. The Transit public key left the OKF
  path; the frozen copy kept for the pre-release bundles the `unifai`
  role verified with `publicKeyRef` was removed by WP-164 (2026-10-25).
- **Clause 6.** The frozen mirror and its check
  (`platform/okf/check_agents_mirror.py`) are gone: every reader takes the
  admitted release instead, through one helper,
  `platform/okf/release_cache.py`, which verifies and extracts the locked
  digest once into the gitignored `.cache/okf-release/`.

## Consequences

Agent owners change agents without touching the platform repository, and the
platform consumes a versioned, signed unit instead of a directory. Every
cross-repository dependency is explicit: the contract one way, the pinned
digest the other.

Two repositories mean two pull requests for a change that spans both (a new
tool capability: binding in `zuno-demo`, contract bump, then the task in
`zuno-demo-agents`). That ordering is the point: an agent can never reference
a capability the platform does not yet offer.

`platform/docs/check_docs.py` and the ansible and stresstest discovery of
`agents/*/agent.okf.md` lose their local source at the cutover and read the
admitted bundle instead (WP-165).

## Security considerations

The repository is public, as `zuno-demo` already is. Bundles contain prompts,
group names and tool capability names, all already public today. No secret
belongs in a bundle; the CI runs gitleaks.

Moving the policies out of `zuno-demo` moves who can widen access. CODEOWNERS
and branch protection on `main` of `zuno-demo-agents` are a precondition of
WP-158, not a follow-up. The platform keeps a last word: admission refuses a
bundle that references a capability absent from its contract.

## Operational considerations

Creating the GitHub repository, its quay.io namespace and its branch
protection are user actions, confirmed before they are taken. No step of this
decision touches a cluster.
