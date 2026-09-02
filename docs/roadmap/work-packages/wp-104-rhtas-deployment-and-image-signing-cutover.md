# WP-104: Deploy RHTAS and cut Priority-1 image signing over from Vault Transit

- **State:** Cancelled — superseded by [WP-110](wp-110-rhtas-operator-deployment-and-fundamentals.md)/[WP-111](wp-111-rhtas-config-rhoai-assessment-and-signing-cutover.md) (2026-09-02). This WP's scope is unchanged and correct - it is split in two rather than dropped, to commit/push/test each half (operator+fundamentals, then RHOAI-assessment+cutover) independently along this platform's Day 1/Day 2 convention. The Design/Acceptance-checks/Out-of-scope content below stays as the historical record of the open questions WP-110/WP-111 resolve; do not execute this brief directly.
- **ADRs:** ADR-0535 (Decision - full scope of this WP).
- **Depends on:** none in-repo. RHTAS is a new component; the images it will
  sign are already built and already signed by the Vault Transit mechanism
  this WP replaces (ADR-0420/WP-070), so nothing upstream is missing.
- **Unblocks:** ADR-0535's Migration/evolution steps 2-4 (OKF bundle trust,
  AI/model trust, admission enforcement) - none of those are worth
  authoring until RHTAS itself is live on this platform.
- **Target:** v0.9.

> Execute this brief as a standalone task from the repository root.

## Goal

Stand up RHTAS 1.4+ in-cluster, wire it to Keycloak as its OIDC identity
source for signing identities, and cut over the signing of the 14 first-party
images ADR-0420/WP-070 already signs
(`agent-runtime`, `agent-bff`, `agent-frontend`, `ai-gateway`,
`aiagent-operator`, `mcp-gateway`, `mcp-confluence`, `mcp-git-forge`,
`mcp-sales-db`, `mcp-salesforce`, `mlops`, `rag-ingestion`, `rag-service`,
`supply-chain-signer`) from Vault Transit's `hashivault://` cosign mode to
RHTAS/Fulcio/Rekor keyless signing. Deploy the Sigstore Policy Controller in
**audit-only** mode against these images - no rejection behavior in this WP.

## ADR references

ADR-0535: "Cutting these over from Vault Transit to RHTAS/Cosign keyless
signing, and standing up the Policy Controller in audit-only mode, is
WP-104." This is that WP. ADR-0535 also authorizes only the observe/verify/
audit enforcement stages - do not configure the Policy Controller to reject
anything in this WP.

## Design (to be finalized during execution)

Open questions this WP must resolve against the live cluster, not assumed
up front:

- **RHTAS topology and namespace.** Follow the platform's existing
  install-role convention (one `ansible/roles/<component>` per platform
  service, Day 0/Day 1 sequencing per ADR-0060) rather than assuming RHTAS's
  own default install layout fits unmodified.
- **Storage/database.** RHTAS's Rekor/Trillian backend needs its own
  persistent storage; confirm what the operator requires against this
  cluster's actual storage classes before assuming parity with existing
  Postgres-backed services (do not reuse the shared PGO fleet without
  checking RHTAS's own supported backend first).
- **Keycloak OIDC wiring for signing identities.** ADR-0032 already
  documented Keycloak's `serviceAccountsEnabled: false` posture platform-
  wide (cited by ADR-0420 when it rejected Keycloak workload identity for
  Vault authentication). RHTAS's Fulcio identity model needs an OIDC issuer
  that can assert a build/CI identity - determine during execution whether
  this requires a new Keycloak client with `serviceAccountsEnabled: true`
  scoped narrowly to the signing identity, and treat that as a deliberate,
  documented exception to the ADR-0032 posture, not a silent reversal of it.
- **Where signing runs.** No Tekton/OpenShift Pipelines is installed
  (confirmed by ADR-0420's Context). The signing step likely still runs from
  the existing `supply-chain-signer` component/Job pattern
  (`components/supply-chain-signer/`, `platform/supply-chain/`), pointed at
  RHTAS's Fulcio/Rekor endpoints instead of Vault Transit - do not introduce
  a pipelines operator solely for this WP unless RHTAS genuinely requires
  one.
- **Verification path.** `platform/supply-chain/verify_signatures.py` and
  agent-runtime's bundle verification currently verify against
  `zuno-platform-signer.pub` (a static committed key). RHTAS keyless
  verification instead checks a Fulcio-issued certificate's identity/issuer
  against Rekor - rework the verifier accordingly, and confirm the existing
  `make d2 check supply-chain` gate keeps passing as verification moves from
  key-based to certificate/transparency-log-based.
- **Policy Controller scope.** Deploy scoped to the zuno-ai-build namespace
  and/or the namespaces that consume these 14 images; audit-only
  (`ClusterImagePolicy` in report mode, not enforce) - do not enable
  rejection anywhere in this WP.

## Acceptance checks (repo-side)

- `python3 platform/docs/check_docs.py` exits 0 (ADR-0535/ADR-0420 status
  fields match their README rows; this WP's State matches its tracker row).
- `make d2 check supply-chain` (or its RHTAS-updated equivalent) passes
  against all 14 images, verified live with `cosign verify` against the
  RHTAS-issued certificates/transparency-log entries - not just a green
  Ansible run (ADR-0420's own implementation notes record more than one
  case where a green playbook run did not mean a real signature existed).
- Policy Controller audit findings reviewed for false positives before any
  future WP proposes flipping it to enforce mode.

## Operator / human follow-up

- Obtaining/configuring whatever external prerequisites the RHTAS operator
  itself requires (e.g. cert-manager issuer wiring, if its defaults don't
  match this cluster's existing Vault PKI-issued certificates) - to be
  enumerated once the operator is actually installed and its CRs inspected
  (`oc explain` on its CRDs before authoring any CR, per this repo's
  standing WP-execution convention).

## Out of scope / deferred

- OKF bundle signing cutover (blocked on ADR-0506/ADR-0507, see ADR-0535
  Non-goals).
- AI/model/LoRA artifact signing (see ADR-0535 Non-goals).
- Any Quay work.
- Flipping the Policy Controller to reject/enforce mode - a separate,
  later WP once this WP's audit stage has run clean.
- Retiring `ansible/roles/supply_chain_signer_build`/the Vault Transit
  `zuno-platform-signer` key outright - keep both live in parallel until
  the RHTAS cutover above is confirmed working end to end, then remove the
  Vault Transit path in a follow-up commit once no longer needed as a
  fallback.
