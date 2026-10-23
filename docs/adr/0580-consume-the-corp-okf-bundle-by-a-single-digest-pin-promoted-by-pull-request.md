# ADR-0580: Consume the corp OKF bundle by a single digest pin, promoted by pull request

- **Status:** Partially implemented (2026-10-23, WP-160, WP-161 and WP-165) - see the amendment and implementation note below
- **Target:** v0.12
- **Date:** 2026-10-22
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0509](0509-deliver-okf-content-as-mounted-versioned-artifacts.md)
- **Related:** [ADR-0022](0022-use-gitops-managed-declarative-agent-tasks-and-policies.md), [ADR-0106](0106-enforce-okf-bundle-signing-and-validation.md), [ADR-0508](0508-isolate-okf-parsing-behind-per-component-adaptation-hooks.md), [ADR-0561](0561-adopt-unifai-as-the-agent-platform.md), [ADR-0564](0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md), [ADR-0576](0576-extract-agent-definitions-and-corp-policies-into-the-zuno-demo-agents-repository.md), [ADR-0577](0577-publish-okf-as-per-agent-artifacts-plus-a-corp-index-artifact.md), [ADR-0578](0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md), [ADR-0581](0581-derive-stack-configuration-from-the-admitted-corp-bundle.md)

## Context

Today OKF content reaches running components in two ways. Most of them bake
it: `COPY agents ./agents` in the Dockerfiles of mcp-gateway, agent-runtime,
agent-frontend and mlops, so a prompt edit means an image rebuild.
`unifai-operator` pulls one artifact per agent by digest (ADR-0564), and
those digests are pinned by hand in `ansible/confidential.yml`
(`zuno_unifai_values.okf.bundles[]`): `publish_okf_bundles.yml` only prints
them with "pin these in the UnifaiAgentBundle specs".

ADR-0509 (`Proposed`) planned operator-rendered ConfigMaps mounted into
pods, materialised by the AIAgent operator that ADR-0561 retires. ADR-0564
already listed ADR-0509 for supersession at the WP-156 cutover. After
ADR-0576 and ADR-0577 there is one release unit, the corp artifact, built
and signed outside the cluster.

ADR-0561 retires agent-runtime, agent-bff and agent-frontend (WP-156). The
remaining readers of bundle content are mcp-gateway (entitlement,
`app/agent_declarations.py`), mlops (task prompts), `unifai-operator`, and
the generators of ADR-0581.

## Decision

**1. One pin names the agents release: `platform/okf/agents.lock`.** It
holds one line, `<registry>/okf-corp@sha256:<digest>`, plus a comment with
the release tag for humans. No other file in `zuno-demo` names an OKF
version; charts, roles and generators read the lock (through the values
ADR-0581 generates). Changing the lock is the only way agents change on a
cluster, and it is a reviewed git change (ADR-0022).

**2. Promotion is a pull request opened by `zuno-demo` itself.** After a
release, the publish workflow of `zuno-demo-agents` sends a
`repository_dispatch` (`okf-release`, payload: the corp digest and tag) to
`startxfr/zuno-demo`, with a token scoped to that one action. A workflow in
`zuno-demo` (`okf-promote.yml`) then:

1. verifies the corp artifact and every agent artifact it lists (ADR-0578);
2. validates them against the current `platform-contract.json`;
3. updates `agents.lock` and runs the stack generator (ADR-0581);
4. writes a semantic diff into the PR description: agents added or removed,
   tasks, tools, knowledge domains, model roles, quota classes, guardrail
   modes, entitlement groups, each as before / after;
5. opens the PR, labelled `okf-promotion`.

The agents repository can therefore request a promotion but never write to
`zuno-demo`. Merging the PR is the promotion.

**3. Admission is one verb: `make d3 admit agents`.** It runs the same
verification and contract validation as step 2, locally or in-cluster,
against the digest in the lock, and fails on: an unsigned artifact, a
signature whose identity does not match (ADR-0578 clause 2), a missing
attestation, an agent listed in the index but not pullable, or a contract
violation. It replaces `make d3 sign agents`. The implementation
(`platform/supply-chain/admit_okf_bundle.py`) reuses the pull and layer
handling of `publish_okf_bundle.py` and the cosign invocation pattern of
`sign_okf_bundle.py`.

**4. Components fetch content at start, never at build.** Every component
that reads bundle content gets an init container, `okf-fetch` (the existing
`components/supply-chain-signer` image, which already carries cosign, plus
oras), that pulls the corp digest given in its pod template, verifies the
corp and agent signatures offline, and extracts the agents and policies
into an `emptyDir` mounted at the path the component already reads
(`AGENTS_DIR`, `/app/agents`, `/app/policies`), so component code is
unchanged. Verification failure keeps the pod in `Init`: fail-closed. The
digest is a pod template annotation, so a merged promotion rolls the
Deployment. `COPY agents` and `COPY policies` leave the Dockerfiles.

**5. Scope by component.** `okf-fetch` is added to mcp-gateway and mlops.
agent-runtime and agent-frontend keep their baked copy until WP-156 deletes
them; ADR-0576 clause 6's frozen-mirror check keeps that copy identical to
the admitted release meanwhile. `unifai-operator` pulls agent artifacts
itself (ADR-0564) from the digests ADR-0581 generates.

**6. Supersession.** This record replaces ADR-0509 in full: content arrives
as a verified OCI artifact pulled by each consumer, not as an
operator-rendered ConfigMap. It also takes over, for the pin, the role ADR-0507
gave `platform/okf/zuno-okf.ref` (ADR-0507 is superseded by ADR-0576).

## Amendment (2026-10-22) - the platform pulls, the agents repository never calls

Corrected while `Accepted`, before implementation, after the user made the
two life cycles independent: the agents repository must not know
`zuno-demo`. Clauses 1, 3, 4, 5 and 6 stand.

- **Clause 2, promotion, no longer starts from the agents repository.**
  There is no `repository_dispatch` and no token of `zuno-demo` in the
  agents repository. `okf-promote.yml` in `zuno-demo` starts on a schedule
  and on demand (a release tag as input): it lists the `v*` tags of
  `okf-corp`, and for a release newer than the lock runs steps 1 to 5
  unchanged. The platform decides when it looks, and a release nobody
  promotes changes nothing.
- **Clause 3, admission,** also checks that every model name of the
  release's `policies/models/model-catalog.yaml` that its agents may reach
  is bound in `platform/ai-gateway/provider-routing.yaml` (ADR-0576
  amendment).

## Amendment (2026-10-23) - two images read the release at build time

Corrected while `Accepted`, at the cutover (WP-165), when `COPY agents` and
`COPY policies` had to leave the last two Dockerfiles that still baked
them. Clauses 1, 2, 3 and 6 stand; clause 4 stands for mcp-gateway.

- **Clauses 4 and 5, ai-gateway and mlops.** Both read the release at
  build time instead of fetching it at start: an `okf-release` stage
  installs pinned `cosign` and `oras`
  (`platform/okf/install_release_tools.py`) and runs
  `platform/okf/release_cache.py`, which verifies the locked digest offline
  exactly as admission does and extracts it; a release that does not
  verify fails the build. mlops has no Deployment to carry an init
  container (KFP pipeline components and a TrainingRuntime run the image)
  and is rebuilt per training run. ai-gateway bakes only the model-routing
  policy, and sits in front of every model call: a pod start should not
  depend on the agents registry. The cost is that a promotion is followed
  by a rebuild of these two images; ADR-0581's generated, mounted routing
  file replaces the ai-gateway case once WP-157 reshapes routing.

## Implementation note (2026-10-23)

Live: the lock (clause 1), the first end-to-end promotion PR of v0.2.0
(clause 2, WP-160), admission (clause 3) and mcp-gateway's `okf-fetch` on
demo333 (clause 4, WP-161). Repository-side readers, CI and the Ansible
checks read the admitted release through `platform/okf/release_cache.py`
(WP-165). Outstanding before `Implemented`: ai-gateway and mlops rebuilt
from the release on a cluster, and a full promotion cycle (tag, PR, merge,
roll) with no agent copy left in `zuno-demo`.

## Consequences

A prompt edit reaches the cluster without any image rebuild: tag in
`zuno-demo-agents`, review the promotion PR, merge, Argo CD rolls the pods.
The deployed agents are always one reviewed, signed, contract-checked
release, recorded in git history by its digest.

Pods now depend on the registry at start. A registry outage blocks new pods
(running pods are unaffected); the mirror option of the operational
considerations is the mitigation.

## Security considerations

Verification happens at three points: in the promotion workflow, at
admission, and in every pod at start (and in `unifai-operator` for its own
pulls). The pod-level check is the one that matters: it does not trust that
the earlier ones ran.

The `repository_dispatch` token can only trigger a workflow that re-verifies
everything and opens a PR for human review; a stolen token yields at most an
unwanted PR.

## Operational considerations

Pods need egress to the registry (quay.io and its blob CDN). Where a
NetworkPolicy or egress policy forbids it, admission copies the admitted
artifacts (`oras copy`, by digest, signatures included) into a mirror
registry set by `zuno_okf_registry_mirror`, and `okf-fetch` pulls from it;
whether the OpenShift internal registry serves OCI artifacts with referrers
is verified by WP-161 before relying on it.

`make d3 admit agents` is safe to run any time; it changes nothing on the
cluster unless the mirror is configured.
