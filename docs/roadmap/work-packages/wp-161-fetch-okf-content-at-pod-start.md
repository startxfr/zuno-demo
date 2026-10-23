# WP-161: Fetch OKF content at pod start instead of baking it

- **State:** Operator pending
- **ADRs:** [ADR-0580](../../adr/0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md)
- **Depends on:** [WP-160](wp-160-admit-the-corp-okf-release-in-zuno-demo.md)
- **Related:** [ADR-0561](../../adr/0561-adopt-unifai-as-the-agent-platform.md), [WP-156](wp-156-retire-zuno-agent-and-rag-code.md), [WP-165](wp-165-cut-over-and-remove-agents-from-zuno-demo.md)
- **Target:** v0.12
- **Estimated files touched:** ~15 in `zuno-demo` — `components/supply-chain-signer/Dockerfile` (+ oras, `okf-fetch` entrypoint), `components/{mcp-gateway,mlops}/{Dockerfile,Containerfile}`, `gitops/charts/{mcp-gateway,mlops}/templates/*`, their NetworkPolicies and values.

> Fail-closed: a pod that cannot verify its agents does not start.

## Progress (2026-10-23)

Repo work for mcp-gateway is done and proven locally; nothing is deployed.

- `components/supply-chain-signer` doubles as the `okf-fetch` image: oras
  1.2.2, pyyaml, `admit_okf_bundle.py` and the Sigstore trust material laid
  out as in the repository, made world-readable (an arbitrary OpenShift UID
  could not read 0600 files: caught by the local test, it would have kept
  every pod in Init).
- `gitops/charts/mcp-gateway`: `okf.fetch.{enabled,corpReference,image}`.
  Enabled, an init container verifies offline and extracts the release into
  an emptyDir; `AGENTS_DIR` and `TOOL_POLICY_PATH` point there, the
  data-classification policy and the tool bindings stay the platform's;
  the reference is a pod-template annotation, so a promotion rolls the
  pods; a non-digest reference fails the render. Disabled (the default),
  the render is byte-identical to before.
- `ansible/roles/mcp`: with `zuno_okf_fetch_enabled`, reads the reference
  from `stack-config.generated.yaml` and merges it into the Application's
  inline values (two exclusive tasks, not an `omit`, which
  `apply_gitops_app.yml`'s `is defined` would accept).
- Proven locally with podman (non-root, read-only root filesystem): v0.2.0
  verified and extracted; a dev-signed corp artifact refused with exit 1;
  mcp-gateway's `AgentDeclarationStore` loads the 8 agents from the
  extracted release with declarations identical to the baked copy.
- The baked `COPY agents` stays as the fallback until WP-165.

Not done, on purpose:

- **mlops** stays baked. It has no Deployment (KFP pipeline components and a
  TrainingRuntime use the image), and its evaluation gates read platform
  files (`platform/ai-gateway/provider-routing.yaml`, the data
  classification) and other agents' bundles from the repository layout.
  Fetching at start would mean an init step in every pipeline component;
  the image is rebuilt per training run anyway. Revisit at WP-165.
- **Live**: build the signer image in-cluster, set `zuno_okf_fetch_enabled`,
  run `make d1 install mcp` on demo333 and watch the Init container and the
  entitlement answers. Needs the user's go.
- `platform/security/check_workload_hardening.py` passes for mcp-gateway;
  its one failure (211/212) is ai-gateway's `MAAS_SA_TOKEN_PATH`, unrelated
  to this work.


## Live proof on demo333 (2026-10-23)

Coordinated with the sessions running the UnifAI pilot there (window agreed,
single sync, revert plan ready).

- Image: a BuildConfig `okf-fetch-wp161` (zuno-ai-build) built
  `supply-chain-signer:wp161` from 97fd352c (sha256:37dc154a...), leaving
  `:latest` untouched. Isolated pods first: v0.2.0 extracted under the
  restricted SCC; a dev-signed corp artifact refused with exit 1.
- The chart, role, Dockerfile and admission files went to the demo333 branch
  as a6c854fe (files only; default render byte-identical).
- `zuno-mcp-d1` values gained `okf.fetch` (enabled, v0.2.0 digest, tag
  wp161): one rolling update, `Synced Healthy`; `okf-fetch` exited 0 with
  `VERIFIED ... release 0.2.0, 8 agent(s)`, alongside the istio native
  sidecar; `AGENTS_DIR=/okf/agents`, `TOOL_POLICY_PATH=/okf/policies/...`;
  `/readyz` ready.
- No behaviour change: tekos scenarios 12 (consultant-01 ->
  salesforce.opportunity.read 403), 13 (unknown tool 404), 18 (board-01 ->
  undeclared git.repository.delete 403) pass; `/mcp` tools/list with
  `X-Zuno-Agent: tekos` gives consultant-01 200, sale-01 and adv-01 403;
  security checks tekos 12/12, comage 8/8, finage 7/7, advantage 7/7,
  naveo 5/5, arkos 11/11 - all equal to the baseline.
- Durable the same day (91761085 on demo222, 2ee40777 on demo333):
  `ansible/clusters/demo333.yml` sets `zuno_okf_fetch_enabled: true` and
  `zuno_okf_fetch_image_tag: wp161`, and `ansible/roles/mcp` passes the tag;
  the role renders exactly the values patched live, so a re-run keeps the
  release path. `okf-fetch-wp161` is kept, relabelled and annotated as the
  source of that image.

Operator action left: every zuno-ai-build BuildConfig builds from `main`,
whose supply-chain-signer Dockerfile predates okf-fetch. Once main carries
the WP-161 Dockerfile, rebuild `supply-chain-signer:latest`, drop
`zuno_okf_fetch_image_tag` from demo333.yml (back to latest) and delete
`okf-fetch-wp161`.

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
