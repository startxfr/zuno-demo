# WP-165: Cut over and remove agents from zuno-demo

- **State:** Done (2026-10-24)
- **ADRs:** [ADR-0576](../../adr/0576-extract-agent-definitions-and-corp-policies-into-the-zuno-demo-agents-repository.md), [ADR-0578](../../adr/0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md), [ADR-0580](../../adr/0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md)
- **Depends on:** [WP-161](wp-161-fetch-okf-content-at-pod-start.md), [WP-162](wp-162-keyless-okf-verification-in-unifai-operator.md), [WP-164](wp-164-generate-stack-configuration-from-the-corp-release.md), [WP-156](wp-156-retire-zuno-agent-and-rag-code.md)
- **Related:** [ADR-0106](../../adr/0106-enforce-okf-bundle-signing-and-validation.md), [ADR-0535](../../adr/0535-adopt-rhtas-as-the-artifact-trust-and-supply-chain-service.md), [WP-51](wp-51-adaptation-hooks-conformance.md)
- **Target:** v0.12
- **Estimated files touched:** ~130 deletions and ~30 edits in `zuno-demo` — `agents/`, the moved `policies/` files, `platform/okf/schema/` and moved scripts, `Makefile`, `ansible/` (day3 sign chain, vault role key export, agents check, acceptance gate, stresstest, availability check), `platform/docs/check_docs.py`, `evaluations/*`, `.github/workflows/lint.yml`, docs.

> The payoff, and the only irreversible step. It starts only after WP-156
> (no baked consumer left) and a live parity proof.

## Progress (2026-10-23)

Step 1 is done: on 2026-10-23 the runtime files, frontmatter and corp
policies of release v0.2.0 were byte-identical to the `agents/` mirror
(only the generated authorization-matrix body of `agent.okf.md` differed,
documentation only). Steps 2 to 4 are done on branch
`prep/wp165-cutover`, nothing deployed:

- **Readers switched.** One helper, `platform/okf/release_cache.py`,
  verifies the locked digest offline (through `admit_okf_bundle.extract`)
  and extracts it once into the gitignored `.cache/okf-release/<digest>/`
  (`current` link for kustomize; `ZUNO_OKF_RELEASE_DIR` override).
  `check_docs.py`, `check_knowledge_refs.py`, `generate_quota_enforcement.py`
  (`--release-dir`), `generate_stack_config.py`, `evaluations/*` (through
  `evaluations/common/okf_release.py`), the mcp-gateway tests, the
  acceptance-gate and stresstest `configMapGenerator`s (refreshed by
  `ansible/tasks/okf_release_cache.yml`), the Day 2 agents check
  (admission plus the catalog check against the release), the stresstest
  contract layer (the release's contract-tests attestation) and the
  scaffold (evaluation half only) read the release. The AAP execution
  environment gains `oras`; `lint.yml` jobs install `cosign`/`oras`;
  `okf-promote.yml` also regenerates the quota files.
- **Images.** mcp-gateway bakes neither agents nor the tool policy;
  `okf-fetch` is unconditional in `ansible/roles/mcp`. ai-gateway (the
  model-routing policy) and mlops (agents, corp policies) read the release
  at build time in an `okf-release` stage (ADR-0580 amendment of
  2026-10-23), proven with podman on public bases: the baked routing
  policy is byte-identical to the release's and to the old copy.
- **Deleted.** `agents/`, `policies/{tools,knowledge,quotas,model-routing,
  guardrails}/`, `platform/okf/schema/`, the moved OKF scripts,
  `generate_deployment_snapshot.py`, the mirror check, and the Transit
  chain (`make d3 sign agents`, `day3_sign.yml`, the signing Job and
  `sign-okf-bundles`, `verify_okf_signatures.yml`,
  `publish_okf_bundles.yml`, `sign_okf_bundle.py`, `publish_okf_bundle.py`,
  the `zuno/okf-signatures` Vault policy path, the vault role's key
  export, the `zuno-day3-sign` AAP Job Template).
- **Kept on purpose, then removed.** The Transit public key, frozen in
  `ansible/roles/unifai/files/`, served the pre-release bundles the `unifai`
  role verified with `publicKeyRef`. WP-164 removed it with the chart's
  `publicKeyRef` branch on 2026-10-25; every bundle is keyless.

Left for the operator: rebuild the AAP execution environment (oras;
`make d1 build aap-execution-environment`), supply-chain-signer, ai-gateway
(`make d1 build`) and mlops (`make d2 build mlops`); re-run
`make d0 install aap-config` and delete the live `zuno-day3-sign` Job
Template, which the role no longer declares; a full promotion cycle
(acceptance below).

## Goal

`zuno-demo` contains no agent definition and no corp policy; every reader
uses the admitted release; the Vault Transit OKF path is gone; docs and ADR
statuses match.

## Steps

1. **Parity proof** on the cluster that runs the release (respect demo
   freezes; message parallel sessions first): admitted digest equals the
   mirror; the tekos scenarios answer identically.
2. **Readers of `agents/` switch to the admitted release** (extracted by
   `admit_okf_bundle.py extract` into a cache directory): `Makefile` agent
   discovery (lines 91-96 today), `check_docs.py` (`AGENTS_DIR`), the
   acceptance-gate `configMapGenerator`, stresstest and
   `day2_availability_check.yml` discovery, `ansible/roles/agents/tasks/check.yml`,
   `evaluations/*`. `grep -rn "agents/"` outside `docs/` must return only
   intentional hits.
3. **Delete** `agents/`, the moved policy files and scripts, the frozen-mirror
   check, and the OKF Transit chain: `day3_sign.yml` signing and publishing
   tasks, Vault KV `zuno/okf-signatures`, the agent-runtime ExternalSecret if
   WP-156 left it, the vault role's export of `agents/zuno-platform-signer.pub`.
4. **Docs.** `RELEASING.md`, `docs/security/secnumcloud-controls.md` supply
   chain rows, `.github/README.md`; ADR-0106 status note; ADR index statuses
   for 0576-0581 per what is live; WP-51 re-scoped or abandoned.

## Acceptance

`agents/` absent; `check_docs.py`, `lint.yml` and the acceptance gate green
against the admitted release; a full promotion cycle (tag, PR, merge, roll)
works with no file under `zuno-demo` naming an agent version except
`platform/okf/agents.lock`.

## Acceptance, met 2026-10-24

`agents/` is absent; `check_docs.py`, the Day 2 agents check (keyless
admission of the pinned release) and the tekos acceptance gate are green
against the admitted release (WP-156 step 6, 2026-10-24); a full promotion
cycle ran live with no file under zuno-demo naming an agent version except
`platform/okf/agents.lock` (release 0.3.0, PR #3; details in ADR-0580's dated
note).

