# ADR-0002: Use OpenShift 4.20 and OpenShift AI 3.5 for the MVP

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

## Decision

Target the documented MVP platform combination and accept Early Access constraints for this internal demonstration.

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution and Related ADRs.

## Amended (2026-09-03): OpenShift AI 3.5 EA2 → 3.5.0 GA

The Decision paragraph above is left as originally written, per this project's
"ADRs are immutable" convention (see [ADR-0022](0022-use-gitops-managed-declarative-agent-tasks-and-policies.md)'s
own amendment note). Only the title and filename dropped `EA2`, so that the
record's *name* stops asserting an Early Access pin the platform no longer runs.

What changed: the RHOAI release train reached General Availability and the
cluster was upgraded `rhods-operator.3.5.0-ea.2` → `rhods-operator.3.5.0`,
moving the Subscription from the `beta` channel to `stable-3.5` (the 3.5
z-stream: it serves later `3.5.z` patches but never rolls to 3.6). The pin now
lives in `gitops/charts/openshift-ai/values.yaml`
(`subscription.version` / `subscription.operator.channel`), and
`ansible/roles/openshift_ai/tasks/discover_channel.yml` prefers `stable-3.5`
at deployment time per [ADR-0048](0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md).
`beta` must not be preferred again: that channel is frozen on `3.5.0-ea.2`, so
selecting it now resolves to a downgrade.

The "accept Early Access constraints" clause is therefore spent for the
platform version itself. It is NOT spent for everything this ADR's Early
Access framing licensed elsewhere: several ADRs record defects verified
against the EA build (for example [ADR-0201](0201-complete-the-openshift-ai-maas-governance-plane-integration.md),
[ADR-0118](0118-keep-the-ai-gateway-as-policy-router-and-defer-maas-delegation.md),
[ADR-0331](0331-revert-openshift-ai-to-the-default-applications-namespace.md)),
and each must be re-verified against the GA on its own terms rather than
assumed fixed. The GA upgrade itself surfaced two fresh vendor defects, so
that caution stands.

The OpenShift Container Platform half of this ADR's title (4.20) was already
superseded by [ADR-0319](0319-target-openshift-4-22.md) (4.20 → 4.22) and is
untouched here; `platform/docs/platform_profile.yaml` remains the single
source of truth for both version targets.
