# WP-161: Fetch OKF content at pod start instead of baking it

- **State:** Not started
- **ADRs:** [ADR-0580](../../adr/0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md)
- **Depends on:** [WP-160](wp-160-admit-the-corp-okf-release-in-zuno-demo.md)
- **Related:** [ADR-0561](../../adr/0561-adopt-unifai-as-the-agent-platform.md), [WP-156](wp-156-retire-zuno-agent-and-rag-code.md), [WP-165](wp-165-cut-over-and-remove-agents-from-zuno-demo.md)
- **Target:** v0.12
- **Estimated files touched:** ~15 in `zuno-demo` — `components/supply-chain-signer/Dockerfile` (+ oras, `okf-fetch` entrypoint), `components/{mcp-gateway,mlops}/{Dockerfile,Containerfile}`, `gitops/charts/{mcp-gateway,mlops}/templates/*`, their NetworkPolicies and values.

> Fail-closed: a pod that cannot verify its agents does not start.

## Goal

mcp-gateway and mlops read agents and corp policies from an `emptyDir`
filled and verified by an `okf-fetch` init container at the digest in their
pod template; their images no longer contain `agents/` or `policies/`; a
merged promotion rolls them.

## Steps

1. **`okf-fetch` entrypoint** in the `supply-chain-signer` image: given
   `OKF_CORP_REF`, the trusted root and identity (ConfigMap), pull, run
   `admit_okf_bundle.py verify` then `extract` into `/okf`, exit non-zero on
   any failure. Add oras to the image; keep the image in
   `build-publish.yml`'s matrix.

2. **Charts.** For each of mcp-gateway and mlops: init container, `emptyDir`
   mounted where `AGENTS_DIR` and the policy paths already point, a pod
   template annotation `zuno.startx.fr/okf-corp-digest` from the generated
   values (WP-164) or, until then, from a value set by
   `make d3 admit agents`. Pass `check_workload_hardening.py`.

3. **Egress.** Measure what a pull from quay.io needs (registry host and the
   blob CDN redirects). If the namespace NetworkPolicies cannot express it,
   implement the mirror of ADR-0580: `oras copy` by digest with referrers to
   `zuno_okf_registry_mirror` during admission. First verify whether the
   OpenShift internal registry stores OCI artifacts and their referrers;
   record the result.

4. **Remove baking.** Delete `COPY agents` / `COPY policies` from the two
   images. Leave agent-runtime and agent-frontend alone (WP-156 deletes
   them; the frozen mirror keeps their copy correct meanwhile).

5. **Live on demo333** (ask the user to power it on; `--context` on every
   `oc`): deploy, compare `/v1/agents` and the entitlement answers of
   mcp-gateway before and after; set a forged digest and see the pod stay in
   `Init`; promote a prompt-only release and see mlops serve the new prompt
   without an image build.

## Acceptance

Neither image contains `agents/`; both pods start only with a verified
release; a promotion rolls them; the entitlement behaviour of mcp-gateway is
identical to before on the tekos scenarios.

## Open questions

- Hot reload through mcp-gateway's `/admin/reload-policy` instead of a
  rollout: worth it, given that a digest change is rare?
