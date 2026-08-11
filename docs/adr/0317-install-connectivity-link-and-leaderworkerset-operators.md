# ADR-0317: Install the Red Hat Connectivity Link and LeaderWorkerSet operators as OpenShift AI prerequisites

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-11
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0047 recorded, with detailed per-capability reasoning, that Connectivity
Link (Kuadrant-based API/Gateway policy) and LeaderWorkerSet (multi-node/
multi-GPU serving topology) were **not** installed: this repository's v0
feature set serves exactly one always-on, single-GPU model with no
multi-node topology, and its own MCP Gateway/AI Inference Gateway
(ADR-0009/ADR-0010) already act as this project's policy enforcement
points. That disposition is unchanged for what the demo actually *runs*
today - but the platform is being made ready ahead of two capabilities
OpenShift AI 3.5+ExA2 exposes for later use: Gateway API-fronted inference
policy (rate limiting/auth in front of `kserve` endpoints) and multi-node
distributed model serving. Installing both operators now, with no consumer
yet, follows the same "prerequisite before the feature that needs it"
shape ADR-0047 itself used for NFD.

## Decision

Install both as new Day 0 prerequisite components, `connectivity-link` and
`lws`, using the same chart + `-d0`/`-d1` ArgoCD `Application` pair +
Ansible role shape every other OLM operator in this repository already
uses (`nfd`, `nvidia-gpu`, `external-secrets`), ordered immediately before
`openshift_ai` in `Makefile`'s `DAY0_COMPONENTS` and each
`ansible/playbooks/day0_*.yml`'s `day0_components` list. Neither vendors a
startx `cluster-*` chart (no such chart is known to exist for either
operator); both use hand-authored `Namespace`/`OperatorGroup`/
`Subscription` templates, following `gitops/charts/external-secrets`'s
precedent for operators with no suitable vendor chart. Channel and catalog
source are discovered from each operator's own `PackageManifest` at apply
time (ADR-0048), never hardcoded - neither package's exact naming has been
verified against a real cluster catalog.

Scope is deliberately narrow: `connectivity-link`'s `-d1` renders a
minimal, empty `Kuadrant` CR (required for the operator to deploy its
sub-controllers at all - the same "meta-operator needs a singleton CR"
shape as this repository's `external-secrets` `OperatorConfig` and
`cert-manager` `CertManager` CR); `lws` has no operand CR and its `-d1`
points at `gitops/charts/noop`. No `Gateway`, `AuthPolicy`,
`RateLimitPolicy`, or actual `LeaderWorkerSet` workload is created by this
ADR - nothing in this repository consumes either operator yet.

## Consequences

`platform/openshift-ai/README.md`'s and `ansible/roles/openshift_ai/
README.md`'s "not applicable" bullets for Connectivity Link and
LeaderWorkerSet no longer describe the implemented state and are updated
accordingly (prose docs track implemented state; this ADR, like every
other, is not rewritten once merged). `gitops/charts/openshift-ai` itself
is unchanged.

## Security considerations

Both Subscriptions source from whatever catalog each operator's own
`PackageManifest` reports (ADR-0048's existing discovery pattern), never a
hardcoded assumption; if only a community/unverified catalog publishes a
given package on a target cluster, that is a fail-loud precheck finding to
resolve before installing, not a silent fallback. The `Kuadrant` CR is
empty - no policy, credential, or network exposure is introduced by this
change.

## Operational considerations

Neither operator's real OLM package name, default namespace, or channel
naming has been verified against a live OpenShift AI 3.5 catalog; the
values checked in are best-known placeholders (`rhcl-operator`/
`kuadrant-system` for Connectivity Link, `leader-worker-set`/
`openshift-lws-operator` for LWS). `ansible/roles/{connectivity_link,lws}/
tasks/install.yml`'s `PackageManifest` lookup fails with a clear
diagnostic (listing published channels) if the guessed package name is
wrong on a given cluster - expected until corrected against that
cluster's actual catalog, same as ADR-0048's existing discovery failure
mode elsewhere in this repository.

## Implementation state

**Implemented (2026-08-11)**, scoped exactly as described above: operator
installation (+ empty `Kuadrant` CR for Connectivity Link) only, ordered
ahead of `openshift_ai`. Supersedes ADR-0047's Connectivity Link and
LeaderWorkerSet dispositions specifically - its NFD gap fix, GPU operator
ordering, and RawDeployment fix are unrelated and remain in force
unchanged. ADR-0047's own text is not edited (ADRs are immutable records);
see `docs/adr/README.md`'s index for this ADR's row instead.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0047](0047-manage-the-complete-openshift-ai-prerequisite-lifecycle.md) (superseded in part - see Implementation state above)
- [ADR-0048](0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md)
- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md)
- [ADR-0312](0312-route-operator-installs-through-argocd-applications.md)
