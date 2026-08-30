# ADR-0535: Adopt RHTAS as the artifact trust and supply-chain service

- **Status:** Proposed
- **Target:** v0.9
- **Date:** 2026-08-30
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0420](0420-sign-supply-chain-artifacts-in-cluster-with-vault-transit.md)
  in full - Vault Transit signing is replaced by RHTAS as the artifact-signing
  mechanism. This is a product-demonstration decision, not a reversal of
  ADR-0420's technical reasoning: Vault Transit remains a smaller, cheaper,
  fully sufficient trust surface for the signing problem alone (see Context).
  ADR-0420's other content (Vault as workload-identity precedent, the
  rejected PKI/Fulcio-by-hand/Keycloak-workload-identity alternatives)
  stays valid background, restated where relevant below.

## Context

Zuno-demo already signs the supply-chain artifacts it produces. ADR-0420
(Implemented, v0.4, 2026-08-22) replaced the platform's original keyless
Cosign/GitHub-OIDC/Fulcio/Rekor pipeline (ADR-0115, ADR-0106) with an
**in-cluster Vault Transit** signer: a single non-exportable `ecdsa-p256`
Transit key, authenticated via Vault's existing Kubernetes-auth pattern,
signing server-side with no external SaaS dependency. That decision
explicitly evaluated and **rejected** standing up a self-hosted Fulcio/Rekor
stack, calling it *"disproportionate: this means operating a CA service, a
transparency log service, and their own storage/availability, for a demo
platform - a much larger and more fragile build than one Vault Transit key,
for no capability this demo needs beyond what Transit already gives it."*
That mechanism is live today: all 14 first-party images and all 8 OKF agent
bundles are signed, an automated gate (`make d2 check supply-chain`) verifies
every image's live digest, and WP-068/WP-069/WP-070 are all `Done`.

Red Hat Trusted Artifact Signer (RHTAS) is, mechanically, exactly the
self-hosted Fulcio/Rekor/Trillian stack ADR-0420 declined to operate. This
ADR does not reopen that decision on security grounds - Vault Transit remains
a smaller, cheaper, sufficient trust surface for the signing problem itself,
and nothing about the platform's threat model has changed since 2026-08-22.

The reason to adopt RHTAS anyway is the same reason zuno-demo already carries
AAP (ADR-0354/ADR-0418), TrustyAI (ADR-0534) and OpenShift Lightspeed
(ADR-0524): this platform is a **demonstration** of Red Hat's product
portfolio, and several of those components were adopted where a simpler
in-repo alternative already existed or would have sufficed, because
demonstrating the product is itself an objective. RHTAS is Red Hat's
flagship trusted-software-supply-chain product; a Red Hat solution-pattern
demo has a standing reason to show it working, independent of whether
Vault Transit already solves the narrower signing problem on its own.

## Decision

Adopt RHTAS 1.4+ as the platform's artifact-signing mechanism, **replacing**
Vault Transit (ADR-0420) for that role. This is a product-demonstration
decision, not a security-driven one, and the operational cost ADR-0420
declined to take on - operating Fulcio (CA), Rekor (transparency log) and
their storage/availability - is accepted here deliberately, in exchange for
demonstrating RHTAS as a real, working component of the platform.

```text
Keycloak / OIDC
      |
      v
    RHTAS
   /   |   \
Fulcio Rekor Policy
      |      Controller
   Cosign      |
      |        v
      v   admission
OpenShift    verification
Internal
Registry
      |
      v
 zuno workloads
```

- **Identity**: Keycloak remains the identity source. Signing identities are
  CI/build service identities, not human signers for ordinary platform
  builds - the same "who signs" boundary ADR-0420 already drew for its
  `zuno-signer` ServiceAccount. The concrete OIDC/Fulcio identity-issuer
  wiring is left to the implementing WP (WP-104), not decided here.
- **Registry**: the OpenShift internal registry stays the artifact store.
  RHTAS adoption does **not** imply Quay - that remains a separate,
  independently-justified decision (see Non-goals).
- **Enforcement**: progressive, following the seed's own ladder -
  observe -> verify -> warn/report -> enforce on selected zuno namespaces ->
  reject untrusted artifacts. This ADR authorizes only the observe/verify/
  audit stages; flipping the Sigstore Policy Controller to reject unsigned
  artifacts on any zuno namespace is a separate, later decision once the
  audit stage has run cleanly.
- **Scope (this ADR)**: Priority 1 only - the container images ADR-0420/
  WP-070 already signs (agent frontend/BFF, agent-runtime, ai-gateway,
  MCP servers, shared AI backend components, `supply-chain-signer` itself).
  Cutting these over from Vault Transit to RHTAS/Cosign keyless signing,
  and standing up the Policy Controller in audit-only mode, is WP-104.

## Non-goals

- **OKF bundle signing** (the seed's Priority 2). Blocked on ADR-0506/
  ADR-0507 (extract OKF content into the standalone `zuno-okf` repository),
  both still `Proposed` - not done. Trusting an agent bundle's origin repo
  and release is meaningless before that repository exists. Revisit once
  ADR-0506/ADR-0507 land; the actual bundle-trust ADR will be authored at
  that point, not pre-created now.
- **AI/ML model and LoRA/PEFT artifact signing** (the seed's Priority 3).
  Zuno-demo does not yet produce a promoted model/adapter artifact that
  needs a trust chain (WP-34's LoRA/MLOps pipeline is `Operator pending`).
  Revisit when a first model artifact is actually promoted between
  environments.
- **Quay.** Not required by RHTAS adoption. A Quay ADR, if ever written,
  needs its own independent justification (registry lifecycle, replication,
  vulnerability management) unrelated to this decision.
- **Admission enforcement (reject mode).** This ADR authorizes audit-only
  Policy Controller deployment. Enforcing rejection on any zuno namespace is
  a follow-on decision, made after the audit stage is live-verified clean.
- Splitting this into the seed's six pre-named child ADRs (deployment,
  identity, signing workflow, admission policy, OKF bundle integrity, AI/
  model trust) up front. No other ADR in this repo pre-declares child ADRs
  before the work that needs them exists; each is written when its own
  sub-scope is actually being implemented.

## Alternatives considered

**Keep Vault Transit as-is (do nothing).** This is the technically sufficient
option - ADR-0420 already delivers everything the signing problem itself
needs, at lower operational cost. Rejected here specifically for the reason
ADR-0420 didn't need to weigh: it forfeits the product-demonstration value of
showing RHTAS on this platform, which is this ADR's actual motivation.

**RHTAS as an additive layer only** (keep Vault Transit signing, add only
the Sigstore Policy Controller for admission enforcement and/or Keycloak-
OIDC-bound signing as a second, parallel mechanism). Considered and rejected
for this ADR's stated goal: running two parallel signing mechanisms
long-term for the same artifacts is exactly the kind of complexity ADR-0420
avoided, and would dilute rather than demonstrate RHTAS as the platform's
trust layer. (This alternative remains available to revisit if a live
RHTAS deployment surfaces a concrete reason Vault Transit needs to stay for
some artifact class.)

**Vault PKI, self-hosted Fulcio/Rekor built by hand, Keycloak workload
identity** - ADR-0420's own Alternatives considered section already
evaluated and rejected these for the signing problem; RHTAS packages and
operates the self-hosted-Fulcio/Rekor shape as a supported product rather
than something this platform would build and maintain itself, which is the
material difference from ADR-0420's rejection of a hand-rolled equivalent.

## Migration / evolution

1. **v0.9 (this ADR, WP-104)**: deploy RHTAS, wire Keycloak/OIDC signing
   identities, cut Priority-1 image signing from Vault Transit to RHTAS/
   Cosign keyless, deploy the Policy Controller in audit-only mode.
2. **Once ADR-0506/ADR-0507 (OKF extraction) are Implemented**: author the
   OKF/agent-bundle trust ADR and its WP(s), establishing the trust chain
   from a Git revision in `zuno-okf` through to a loaded agent bundle.
3. **Once a model/adapter artifact is actually promoted**: author the AI/
   model trust ADR and WP(s), evaluating RHTAS's model-validation
   capabilities separately from its (mature) image-signing capabilities.
4. **Admission enforcement (reject mode)**: a follow-on ADR/WP once the
   audit stage from step 1 has run clean for a defined period.

See [Standard clauses](README.md#standard-clauses) for Consequences,
Security considerations, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0420](0420-sign-supply-chain-artifacts-in-cluster-with-vault-transit.md) -
  superseded by this decision; its Vault Transit signing mechanism is what
  WP-104 cuts over from.
- [ADR-0106](0106-enforce-okf-bundle-signing-and-validation.md),
  [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md) -
  the original keyless Cosign/GitHub-OIDC/Fulcio/Rekor decisions ADR-0420
  itself superseded; RHTAS revisits the same mechanism shape, self-hosted
  rather than public-good.
- [ADR-0024](0024-use-vault-for-application-secrets.md) - Vault's role as
  application-secrets custodian is unchanged by this decision; only its
  artifact-signing role (added by ADR-0420) moves to RHTAS.
- [ADR-0032](0032-propagate-trusted-identity-end-to-end.md) - the identity-
  propagation precedent RHTAS's Keycloak/OIDC signing-identity model follows.
- [ADR-0506](0506-extract-okf-content-into-a-standalone-zuno-okf-repository.md),
  [ADR-0507](0507-consume-the-zuno-okf-repository-through-a-single-pinned-reference.md) -
  block this ADR's OKF-bundle-trust Non-goal until both are Implemented.
