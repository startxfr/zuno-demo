# WP-165: Cut over and remove agents from zuno-demo

- **State:** Not started
- **ADRs:** [ADR-0576](../../adr/0576-extract-agent-definitions-and-corp-policies-into-the-zuno-demo-agents-repository.md), [ADR-0578](../../adr/0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md), [ADR-0580](../../adr/0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md)
- **Depends on:** [WP-161](wp-161-fetch-okf-content-at-pod-start.md), [WP-162](wp-162-keyless-okf-verification-in-unifai-operator.md), [WP-164](wp-164-generate-stack-configuration-from-the-corp-release.md), [WP-156](wp-156-retire-zuno-agent-and-rag-code.md)
- **Related:** [ADR-0106](../../adr/0106-enforce-okf-bundle-signing-and-validation.md), [ADR-0535](../../adr/0535-adopt-rhtas-as-the-artifact-trust-and-supply-chain-service.md), [WP-51](wp-51-adaptation-hooks-conformance.md)
- **Target:** v0.12
- **Estimated files touched:** ~130 deletions and ~30 edits in `zuno-demo` — `agents/`, the moved `policies/` files, `platform/okf/schema/` and moved scripts, `Makefile`, `ansible/` (day3 sign chain, vault role key export, agents check, acceptance gate, stresstest, availability check), `platform/docs/check_docs.py`, `evaluations/*`, `.github/workflows/lint.yml`, docs.

> The payoff, and the only irreversible step. It starts only after WP-156
> (no baked consumer left) and a live parity proof.

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
