# ADR-0353: Source runtime images by family: the internal registry for zuno components, quay.io/zuno for UnifAI and OKF

- **Status:** Proposed
- **Target:** v0.11
- **Date:** 2026-10-24
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md), [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md), [ADR-0352](0352-run-day-0-platform-services-in-internal-or-external-mode.md), [ADR-0549](0549-close-the-secnumcloud-supply-chain-gap-with-an-in-cluster-release-ledger.md), [ADR-0561](0561-adopt-unifai-as-the-agent-platform.md), [ADR-0574](0574-deploy-unifai-through-argocd-from-a-pinned-olm-catalog.md), [ADR-0577](0577-publish-okf-as-per-agent-artifacts-plus-a-corp-index-artifact.md), [ADR-0578](0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md)

## Context

This ADR started as a stub (2026-08-04, `docs/roadmap/adr-decisions-v0.3.md`)
that [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md)
deferred to it: should charts be able to source first-party runtime images
from Quay, or another external registry, instead of the in-cluster registry,
and how is that different from ADR-0352's internal/external axis (who deploys
a platform service) and ADR-0116/0117's (how agents reach third-party tool
backends)? It is a third sense of "external": where an image comes from.

Since then the question has been answered in two different ways, by
different decisions, for different images.

**The components zuno-demo builds itself** (mcp-gateway, ai-gateway, mlops,
the MCP servers, diagram-render: eleven charts whose `image.repository` is
`image-registry.openshift-image-registry.svc:5000/...`) are built in the
cluster by a BuildConfig and read from the OpenShift ImageStream registry.
ADR-0549 made that the SecNumCloud posture on purpose: "the existing
OpenShift-native internal ImageStream registry only. No self-hosted Quay, no
new operator", with an in-cluster signed release ledger instead of a
dependency on an external registry or on GitHub Actions. ADR-0115's
GitHub Actions to Quay pipeline stays available and mothballed (WP-04
deferred), and `pin_release.py` is kept for "ADR-0353's still-unwritten
external-registry scenario".

**The UnifAI stack and the OKF release** came later and were never part of
that internal path. They live outside this repository (`startxfr/UnifAI`,
`startxfr/zuno-demo-agents`) and are published to `quay.io/zuno/*`: the
operator catalog and the stack's application images
(`quay.io/zuno/unifai-<component>`, ADR-0574), the per-agent artifacts and the
corp artifact (`quay.io/zuno/okf-*`, ADR-0577). The OKF artifacts are signed
keyless with GitHub OIDC and verified offline by identity (ADR-0578); the
operator catalog is pinned by digest in `gitops/charts/unifai/values.yaml`.
The one other literal `quay.io` image in a chart is Red Hat's own
`quay.io/modh/vllm` (a vendor image, not first-party).

So an external registry is already the source of record for one family of
images, and the internal registry for another. What is missing is the
decision that says so, and that says what is *not* decided.

## Decision

1. **Two families, two sources, no switch between them.**
   - *Components built by zuno-demo* are sourced from the cluster's internal
     registry, built in the cluster (ADR-0056, ADR-0549). Their charts never
     point `repository`, `frontendRepository` or `bffRepository` at an external
     registry. ADR-0115 and ADR-0549 are unchanged.
   - *The UnifAI stack and the OKF release* are sourced from `quay.io/zuno/*`,
     which is the registry of the repositories that build them.
2. **Conditions on the external family.** A reference to `quay.io/zuno/*` is
   admitted in a chart or a lock only when it is immutable: a digest, or at
   least a version tag that a reviewed commit chose (ADR-0574), never a moving
   tag on a deployed cluster. OKF artifacts are, in addition, verified
   offline against the signing identity before they are used (ADR-0578).
3. **No per-chart registry override.** This ADR does not add an
   `image.registry` setting letting a zuno-demo component be pulled from an
   external registry. That would reopen ADR-0549's posture for a use case no
   deployment has asked for. If one does, it needs its own ADR that
   supersedes this decision in part, states the SecNumCloud consequences, and
   makes digest pinning and signature verification mandatory for that path.
4. **Vocabulary.** "External" in the image-source sense (this ADR) is a
   distinct axis from ADR-0352's mode and from ADR-0116/0117's SaaS backends;
   an ADR that means one of the other two says so.

## Alternatives considered

- **Per-chart external registry for first-party components** (the original
  stub): rejected for now. It contradicts ADR-0549's deliberate choice for
  the images zuno-demo owns, adds a code path (chart values, pinning,
  verification) with no consumer, and would have to be proven against the
  SecNumCloud controls before use. Recorded in decision 3 as a path that needs
  its own ADR.
- **Adopt `quay.io/zuno` as the official source for every image:** rejected;
  it would supersede ADR-0549 for the components that are meant to stay
  in-cluster.
- **Move the UnifAI stack to the internal registry:** rejected for this ADR.
  The images are built by another repository's CI and the operator is deployed
  from a pinned catalog (ADR-0574); mirroring them in is possible
  (`image_mirrors`) but is a separate operational choice, not a new rule.

## Consequences

- No code or chart change: the ADR records the existing split and closes the
  deferral in ADR-0115, ADR-0549 and WP-134.
- A reviewer who sees `quay.io/zuno/...` in a chart or a lock has a rule to
  apply (decision 2); a reviewer who sees an external registry on a zuno-demo
  component has a reason to refuse it (decision 3).
- The UnifAI runtime images are not signature-verified by this platform today:
  they are pinned by reference (ADR-0574) but only the OKF artifacts are
  verified by identity. That gap is stated here, not closed.

## Security considerations

External images are a supply-chain dependency on the registry and on the
publishing repository's CI. The conditions in decision 2 reduce that to a
reviewed, immutable reference; signature verification of the UnifAI runtime
images remains open. Restricting external sources to the family that already
has them keeps the SecNumCloud argument of ADR-0549 intact for the rest.

## Review evidence

Chart image repositories inventoried on 2026-10-24 (eleven in-cluster
registry references, `quay.io/zuno` in `gitops/charts/unifai`, one vendor
`quay.io/modh`), cross-read against ADR-0115, ADR-0549, ADR-0574 and
ADR-0577.
