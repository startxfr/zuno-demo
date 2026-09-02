# WP-111: RHOAI-integration assessment and RHTAS image-signing cutover

- **State:** Done (2026-09-02) - qualified: the signing cutover is fully
  live-verified end to end; the Policy Controller is deployed and
  correct but genuinely dormant (zero namespaces scoped), not the
  "audit-only, observing real traffic" state the ADR envisioned - see
  finding 6 below. `make d2 check supply-chain`'s in-cluster verify Job:
  `RESULT: PASS - all 14 image(s) verified` keyless via RHTAS, each with a
  real Fulcio certificate + Rekor entry. `supply-chain-signer` (a
  build-only tool image no `values.yaml` deploys, so outside the
  auto-discovered set) was also signed and verified manually. Part A
  finding: the ADR-0535 Non-goal premise was already false when the ADR
  was written - see the ADR's own Non-goals correction and this brief's
  Goal section; not folded into Part B, no model/adapter signing work
  done here.

  Six further live findings, all fixed in-repo the same day:
  1. **Stale image list.** This brief's original 14-name list included
     `mcp-sales-db` (never existed) and missed `mcp-aap`/`diagram-render`
     (added to the platform after WP-104's list was drafted). Corrected
     in the Goal section above to describe the auto-discovery instead of
     a fixed list, which is inherently self-correcting.
  2. **ClusterImagePolicy v1beta1's conversion webhook is mispackaged**
     (points at a nonexistent Service/namespace) **and, even pointed at
     the real Service, non-functional** (times out / 404s - the pod
     doesn't implement `/convert` at all). Fixed by authoring the CR as
     `v1alpha1` (the CRD's storage version, identical spec, no conversion
     needed) and, user-approved, patching `spec.conversion.strategy` to
     `None` on the live CRD (not GitOps-managed - reapplied idempotently
     by `ansible/roles/rhtas_config`).
  3. **None of TrustRoot/ClusterImagePolicy/PolicyController ever
     populate `status.conditions`** - ArgoCD's generic health check hung
     sync forever on "waiting for healthy state of ...". Fixed with 3 new
     `resourceHealthChecks` entries on the `ArgoCD` CR (ADR-0312 pattern,
     `ansible/roles/argocd`), always-Healthy for these 3 kinds.
  4. **ArgoCD's own admission-webhook calls into `zuno-rhtas` were
     NetworkPolicy-blocked** - same-namespace debug-pod curl tests always
     succeeded instantly, masking that ArgoCD's cross-namespace call was
     the one never allowed, intermittently exceeding the webhook's tight
     5s timeout. Fixed: `openshift-gitops` added to
     `allowedFromNamespaces`.
  5. **policy-controller-operator's own admission webhook hard-rejects
     its `PolicyController` CR outside a namespace literally named
     `policy-controller-operator`** - a genuine product-mandated fixed
     namespace (unlike `rhtas-operator`, AllNamespaces, co-located fine
     in `zuno-rhtas` per WP-110). Reinstalled there; see
     `gitops/charts/namespaces/values.yaml`.
  6. **Critical: the webhook's "container images must be referenced by
     digest" gate is unconditional, NOT governed by
     `ClusterImagePolicy.spec.mode: warn`** (that only governs the
     signature-verification result). Every chart in this repo still
     declares `tag: latest` (ADR-0115 gap 2), so labeling any real zuno
     namespace with `policy.rhtas.com/include` made the webhook actively
     REJECT real pods - observed live on the signing Job itself (6
     rejected admission attempts before a Job-controller retry happened
     to succeed; a bare Pod with no retry loop would have stuck). User
     decision: labels removed from `zuno-ai-build`/`zuno-mlops`/
     `zuno-ai-run`. The Policy Controller stack (TrustRoot/
     ClusterImagePolicy/PolicyController) stays deployed and correct but
     scoped to **zero namespaces** - genuinely dormant, not audit-only in
     practice - until ADR-0115 gap 2 is actually closed (immutable
     digests written into `values.yaml`). Re-enabling the namespace
     labels once that gap closes is a follow-up, not part of this WP.
- **ADRs:** ADR-0535 (Decision - remaining scope: RHOAI-integration
  assessment, Priority-1 image cutover, Policy Controller audit mode).
- **Depends on:** WP-110 (RHTAS operator, Trillian storage, and the
  `zuno-signer` Keycloak identity live and smoke-tested).
- **Related:** mirrors the `aap`/`aap-config` and `lightspeed`/
  `lightspeed-config` Day 1/Day 2 split. Completes WP-104's original
  scope (Cancelled - superseded by WP-110/this WP).
- **Target:** v0.9.

> Execute this brief as a standalone task from the repository root, after
> WP-110 is live. Read ADR-0535 in full first.

## Goal

Two parts, both landing as the new Day 2 component `rhtas-config`,
committed/pushed/tested live as one WP since Part A is expected to be a
short, low-risk investigation rather than its own multi-file change:

**Part A - RHOAI-integration assessment.** ADR-0535 already lists AI/ML
model and LoRA/PEFT artifact signing as a Non-goal ("Zuno-demo does not
yet produce a promoted model/adapter artifact that needs a trust chain -
WP-34's LoRA/MLOps pipeline is `Operator pending`"). This WP **confirms
that live** rather than assuming it holds: check WP-34's actual current
state, grep this repo's RHOAI-facing pipeline/build definitions (there is
no Tekton/OpenShift Pipelines operator installed per ADR-0420's own
Context - confirm that is still true), and confirm no promoted model or
adapter artifact exists that would need a trust chain today. Expected
outcome: document "not applicable for v0.9" in this WP's State, with no
code change for Part A. If a concrete, narrow need surfaces instead, note
it explicitly and scope a follow-on ADR for it - do not silently expand
this WP's Part B to cover it.

**Part B - the cutover** (WP-104's original core scope). Reconfigure
`platform/supply-chain/sign_in_cluster.py` and `verify_signatures.py` to
sign and verify via RHTAS/Cosign keyless (Fulcio certificate + Rekor
entry, using the `zuno-signer` identity WP-110 established) instead of
Vault Transit, for the first-party images `verify_signatures.py`
auto-discovers from `gitops/charts/*/values.yaml` at run time (not a
fixed list committed here, since it drifts as components are added -
14 at execution time: `agent-runtime`, `agent-bff`, `agent-frontend`,
`ai-gateway`, `aiagent-operator`, `diagram-render`, `mcp-aap`,
`mcp-confluence`, `mcp-gateway`, `mcp-git-forge`, `mcp-salesforce`,
`mlops`, `rag-ingestion`, `rag-service` - two names in this WP's original
draft, `mcp-sales-db` and `supply-chain-signer`, turned out stale/wrong:
`mcp-sales-db` never existed as a component, and `supply-chain-signer` is
a build-only tool image no `values.yaml` deploys, so the auto-discovery
correctly excludes it; it was still signed manually as part of this WP's
live verification). Deploy the Sigstore Policy Controller in
**audit-only** mode, scoped to the zuno namespaces that consume these
images - no rejection behavior in this WP. Keep the Vault Transit key
`zuno-platform-signer` and the committed `agents/zuno-platform-signer.pub`
in place as a rollback path; actual retirement of the Vault Transit path
is a separate, later decision, not part of this WP.

## ADR references

ADR-0535's "Scope (this ADR)" bullet: "cutting these images over from
Vault Transit to RHTAS/Cosign keyless signing, assessing whether RHOAI
needs any direct integration, and standing up the Policy Controller in
audit-only mode, is WP-111." ADR-0535 also authorizes only the
observe/verify/audit enforcement stages - do not configure the Policy
Controller to reject anything in this WP.

## Preconditions (verify before starting)

- WP-110 `Done` (or at minimum "Repo work merged, live verification
  pending" with its Acceptance checks actually confirmed) - this WP
  builds directly on its live `Securesign`/Trillian/`zuno-signer` stack.
- Read `components/supply-chain-signer/Dockerfile`,
  `platform/supply-chain/sign_in_cluster.py`,
  `platform/supply-chain/verify_signatures.py`,
  `ansible/roles/supply_chain/tasks/check.yml`, and
  `ansible/roles/supply_chain_signer_build/tasks/build.yml` in full.
- Read `gitops/apps/aap/application-d0.yaml`/`application-d1.yaml` (or
  `lightspeed-config`'s) sync-wave placement - place `rhtas-config`'s
  Applications after WP-110's `rhtas` waves, same pattern.

## Repo changes (step by step)

1. Part A: investigate per Goal above; record the finding in this WP's
   State section. No repository change unless a concrete need is found.
2. New chart `gitops/charts/rhtas-config`:
   - Policy Controller CR in audit-only mode.
   - `ClusterImagePolicy` targeting the 14 first-party image repos, scope
     observe/verify only - no `enforce`/reject.
3. Rework `sign_in_cluster.py`'s `sign_image()` to sign keyless via RHTAS
   (Fulcio cert + Rekor entry) using the `zuno-signer` OIDC identity,
   instead of `hashivault://`.
4. Rework `verify_signatures.py`'s verification path: today it checks
   against the static committed `zuno-platform-signer.pub`; RHTAS keyless
   verification instead checks a Fulcio-issued certificate's
   identity/issuer against Rekor. Confirm `make d2 check supply-chain`
   keeps passing as verification moves from key-based to
   certificate/transparency-log-based.
5. Update `ansible/roles/supply_chain/tasks/check.yml` accordingly.
6. Update `ansible/roles/supply_chain_signer_build` only if the signer
   image itself needs additional Fulcio/Rekor client tooling.
7. Makefile: `rhtas-config` added to `DAY2_RUN_COMPONENTS`.

## What NOT to touch

- Do not flip the Policy Controller to reject/enforce mode.
- Do not retire `zuno-platform-signer`, its Vault policy, or
  `ansible/roles/supply_chain_signer_build` - keep both signing paths
  live in parallel through this WP; removal is a separate follow-up once
  the cutover is confirmed working end to end with no fallback need.
- Do not touch OKF bundle signing (blocked on ADR-0506/ADR-0507) or any
  Quay work.
- Do not expand Part A into real model/adapter signing work unless a
  concrete need is found and scoped into its own follow-on ADR first.

## Acceptance checks (repo-side)

- `python3 platform/docs/check_docs.py` exits 0 (ADR-0535's Status field
  matches its README row; this WP's and WP-104's State match their
  tracker rows).
- `make d2 check supply-chain` (RHTAS-updated) passes against all 14
  images, verified live with `cosign verify` against the RHTAS-issued
  certificates/transparency-log entries - not just a green Ansible run.
- Policy Controller audit logs show observe/verify records for the zuno
  namespaces with zero reject actions.
- WP-104 confirmed `Cancelled - superseded by WP-110/WP-111` (already
  set; re-verify it wasn't reverted).

## Operator / human follow-up

- Reviewing Policy Controller audit findings for false positives before
  any future WP proposes flipping it to enforce mode.

## Out of scope / deferred

- OKF bundle signing cutover (blocked on ADR-0506/ADR-0507, see ADR-0535
  Non-goals).
- AI/model/LoRA artifact signing, unless Part A finds a concrete need (in
  which case: a follow-on ADR, not a silent scope expansion here).
- Any Quay work.
- Flipping the Policy Controller to reject/enforce mode.
- Retiring the Vault Transit path outright.

## Status updates

- On repository merge, before live confirmation: State -> "Repo work
  merged, live verification pending".
- After all Acceptance checks are live-confirmed (cutover + Policy
  Controller audit-only both verified): State -> "Done", and ADR-0535's
  Status -> "Implemented".
