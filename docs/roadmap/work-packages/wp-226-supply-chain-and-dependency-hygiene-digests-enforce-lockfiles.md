# WP-226: Supply chain and dependency hygiene: digests, enforce mode, lockfiles (delivers ADR-0603)

- **State:** Done (2026-11-07, user decision). On `devel`; the image policy is in `enforce` on demo333 for the opt-in namespaces after a clean warn run. The live steps still open (first rendered release, `zuno_validate_route_certs`, AAP execution environment digest) are listed in [post-demo-hardening.md](../post-demo-hardening.md) and each needs the user's go.
- **ADRs:** ADR-0603
- **Depends on:** WP-222
- **Blocks:** WP-227
- **Estimated files touched:** ~40 (120 in the end: 18 lockfiles and their 18 sources, 11 charts with their helpers)

> Execute this brief as a standalone task from the repository root.

## Goal

Make what runs the same bytes that were built and reviewed (M16 to M18, M20), and triage the certificate-verification
exceptions (M3).

## ADR references

ADR-0603 clause 4.

## Preconditions

- Read `RELEASING.md`, ADR-0535, `platform/supply-chain/pinned-releases.yaml` and the two pin checkers
  (`check_no_latest_tags.py`, `check_unifai_pins.py`) to see why `:latest` charts pass.
- Every release pin needs the user's go (memory: pin every release with the user's go).

## Decisions taken with the user (2026-11-07)

- `ClusterImagePolicy` ships in `warn` in git with a documented switch to `enforce`. The dry run and the switch are
  cluster actions left to the operator.
- No release pin or ledger entry is created or changed. Digests reach the charts only through the release tooling.
- Lockfiles with `pip-compile --generate-hashes`, one version per shared library, `kubernetes.core` pinned, Dependabot
  for GitHub Actions and pip.
- `validate_certs`, `insecure` and `verify=False`: fixed where safe, otherwise kept with a one-line reason.
- `evaluations/.venv-gate`: untracked, history not rewritten.
- Not done here (WP-224 finding, 2026-11-07): the ADR-0053 acceptance gate
  (`ansible/roles/agents/tasks/run_acceptance_gate.yml`) still `pip install`s at start-up, so the TEMPORARY
  `pypi.org` / `files.pythonhosted.org` entries stay in the zuno-ai-run EgressFirewall
  (`gitops/charts/namespaces/values.yaml`) until it runs from a prebuilt image with hash-pinned dependencies.

## Repo changes (done)

### M16: digests rendered into chart values, base images pinned

1. **The charts can render a digest.** The 11 first-party charts (a2a-gateway, ai-gateway, diagram-render, mcp-aap,
   mcp-confluence, mcp-gateway, mcp-git-forge, mcp-salesforce, mlops, zuno-dify-knowledge, zuno-token-proxy) get a
   `digest: ""` key next to each image `tag` (`image`, `okf.fetch.image`, `images.mlops`) and an `imageRef` and
   `imagePullPolicy` helper. With a digest, the container runs `repository@sha256:...` and pulls `IfNotPresent`, and the
   `image.openshift.io/triggers` annotation is dropped (the `:latest` trigger would rewrite the pinned image). A digest
   that is not `sha256:<64 hex>` fails the render. With a digest the pod template also carries
   `zuno.io/image-digest` (and `zuno.io/okf-fetch-image-digest` for the init container): the Applications ignore
   `/spec/template/spec/containers/0/image` (the `:latest` trigger patches it) without `RespectIgnoreDifferences`, so
   without the annotation a release moving `@A` to `@B` would stay `Synced` and roll nothing (review finding). With
   every digest empty the charts render byte for byte what they rendered at 2befc90a (checked with `helm template`, also
   with `okf.fetch.enabled`), so the merge changes nothing live.
2. **The release tooling writes the digests.** `platform/supply-chain/render_release_digests.py --release <tag>` reads the
   last ledger entry of that release and writes each pin's digest into the matching `digest` key, keeping every comment.
   It refuses, and writes nothing, on a `digest: null` pin, on a pin that is not `signed: true`, or on a chart without a
   `digest` key. `--clear` returns to `:latest`. `--check` (now in `lint.yml`) fails on a first-party digest that is not a
   signed ledger pin for that chart and field. `make d3 release TAG=<tag> RENDER_DIGESTS=1` runs it after the ledger is
   written; when the release was routed to AAP, the ledger entry is not in the local checkout, so make prints "pull the
   ledger commit, then run render_release_digests.py --release <tag>" instead. Tests:
   `platform/supply-chain/tests/test_render_release_digests.py` (10 tests; two render charts with `helm template`, one
   of them proves `@A` and `@B` give different pod templates for all 10 Deployment charts), in the `lint.yml` helm job.
   trustyai-eval has no digest path yet: its image is a plain `image:` string in `gitops/charts/trustyai-config`, outside
   the ledger's component set.
3. **The release builds every chart that can be pinned.** `tag_local_release.py` `COMPONENTS` adds a2a-gateway,
   supply-chain-signer (the `okf-fetch` init containers of mcp-gateway and a2a-gateway), zuno-dify-knowledge and
   zuno-token-proxy: 12 components, up from 8.
4. **Base images by digest.** The zuno-ai-build mirrors that first-party Dockerfiles build FROM (python 3.11-slim and
   3.12-slim, node 20-alpine, ubi9 python-311) import a digest with `importPolicy.scheduled: false`
   (`ansible/roles/image_mirrors/tasks/install.yml`, digests resolved on 2026-11-07 with `skopeo inspect --raw`), and
   `build-publish.yml` passes the same `tag@digest` as `BASE_IMAGE`. The refresh routine is written next to the mirrors.
5. `pullPolicy: Always` now applies only to the `:latest` path. A rendered digest pulls `IfNotPresent`.

### M17: enforce mode and keyless CI signing

6. `gitops/charts/rhtas-config`: `policyOperand.clusterImagePolicy.mode` is a value (`warn` in git; the template accepts
   only `warn` or `enforce`). Live today: `zuno-first-party-images` is `warn`, `zuno-unifai-images` is already `enforce`.
7. `build-publish.yml`: each build job gets `id-token: write`, signs the pushed digest keylessly (`cosign sign`, public
   Sigstore, GitHub OIDC), attaches the SBOM as a signed `spdxjson` attestation (`cosign attest`) and verifies both
   against this identity:
   - issuer `https://token.actions.githubusercontent.com`;
   - subject `^https://github\.com/startxfr/zuno-demo/\.github/workflows/build-publish\.yml@refs/(heads/main|tags/v[0-9].*)$`;
   - `--certificate-github-workflow-repository startxfr/zuno-demo`.

   A run dispatched from any other branch signs, but its verify step fails. The workflow stays `workflow_dispatch` only
   (ADR-0115).

### M18: cosign checksum, SBOM attestation, Trivy

8. `components/supply-chain-signer/Dockerfile`: the cosign v2.4.1 and oras 1.2.2 downloads are checked with
   `sha256sum -c` against the digests in the releases' checksum files (re-read from GitHub on 2026-11-07; the same
   digests as in the AAP execution environment). The other images already checked theirs (`install_release_tools.py`,
   the execution environment).
9. The SBOM is an attestation (item 7). `ignore-unfixed` is dropped: the report also lists the HIGH and CRITICAL
   findings that have no upstream fix yet. The scan stays non-blocking (`continue-on-error`, ADR-0115's recorded
   reason).

### M20: hashed lockfiles, one version per library, kubernetes.core pinned

10. Each Python component keeps its direct dependencies in `requirements.in`, and `requirements.txt` is now a
    `pip-compile --generate-hashes --allow-unsafe` lock: 18 locks, 12 under `components/` and 6 under `evaluations/`.
    Every Dockerfile, CI step and Ansible pip task already installs `requirements.txt`, and pip switches to
    hash-checking mode by itself. `platform/python/compile_locks.py` recompiles them (pip-tools in a throwaway venv).
    Extras are kept in the locks: with `--strip-extras`, pip refused ai-gateway's transitive `google-api-core[grpc]` in
    hash-checking mode. The mlops image now upgrades pip before the install, like the other images: pip 22 refused the
    mcp-gateway lock (`uvicorn` next to `uvicorn[standard]`), pip 26 installs it.
11. `platform/python/constraints.txt` names the shared versions, and every lock is compiled against it. ai-gateway moved
    to them: fastapi 0.115.0 to 0.141.1, pydantic 2.9.2 to 2.13.4, PyJWT 2.9.0 to 2.13.0, httpx 0.27.2 to 0.28.1,
    OpenTelemetry 1.27 to 1.44, langchain-core 0.3.15 to 0.3.86, langchain-openai 0.2.4 to 0.2.14, openai 1.54.4 to
    1.109.1 (httpx 0.28 needs openai 1.55.3 or later). trustyai-eval, mlops and the evaluations moved to httpx 0.28.1;
    protobuf is held at 5.29.6 for every component (ai-gateway's Google client caps it below 6).
    `platform/python/check_python_locks.py` (in `lint.yml`) fails on an unhashed or stale lock, a drift from the
    constraints, a lock resolved for the wrong interpreter, or a library at two versions. One exception:
    `components/mlops/tooling` (kfp, the pipeline compiler on the control host) needs kubernetes below 31 and is resolved
    for Python 3.9, the control host's `python3`; it is compiled as its own environment.
12. `ansible/requirements.yml` pins `kubernetes.core` 3.3.1, `community.hashi_vault` 7.1.0 and `community.general`
    13.2.0, the versions the playbooks run with today. The `lint.yml` ansible job installs from it, with `ansible`
    12.3.0.
13. `.github/dependabot.yml`: weekly grouped updates for GitHub Actions and for pip (every `requirements.in` directory). A
    pip update that splits a shared library fails `check_python_locks.py`. The fix is a bump in `constraints.txt` and a
    recompile.

### M3: certificate-verification triage

14. Once the virtual environment left git (WP-222), 157 hits remain outside `docs/`, not 501. 121 of them are Ansible
    `uri` calls to the cluster's own Routes, most of them credentialed (Keycloak admin password grants, AAP admin basic
    auth). They now read `validate_certs: "{{ zuno_validate_route_certs | default(false) | bool }}"`. The variable is in
    `ansible/inventories/demo/group_vars/all/main.yml` with its reason: until ADR-0211's ACME wildcard is issued (a
    per-cluster choice), the Routes serve the router's self-signed default certificate. demo333's Routes verify
    (keycloak, aap, rh-ai and grafana, checked on 2026-11-07), so the switch to `true` is an Operator pending step.
15. Kept, each with a one-line reason in place: the models precheck to an in-cluster Service (service-CA certificate,
    diagnostic only); the evaluation probes that send no credential and assert a refusal or a status code
    (`unifai_checks.py`, `security_checks.py`, `run_scenarios.py`); the vLLM PodMonitor (it scrapes by pod IP); the OTLP
    hop to Tempo; the vendor OGX playground; the Grafana and failover-drill shortcuts, already commented; `cosign
    --insecure-ignore-tlog` for the Transit blob signatures (ADR-0420); and `load_k8s_auth_env.yml`, which follows the
    AAP credential's own `verify_ssl`.

### M21: virtual environment

16. Already done by WP-222 (72f6ec45): `evaluations/.venv-gate` is untracked and `.venv-*/` is ignored. History is not
    rewritten. The purge is the user's decision: the 1,902 files are a stock venv with no secret, so rewriting a public,
    shared history would buy only a smaller clone.

## Verification (2026-11-07)

- **Install from the locks.** Every lock installs in a fresh venv with an up-to-date pip and `pip install
  --require-hashes -r requirements.txt`: the 11 Python 3.11 locks, the four MCP servers on Python 3.12 and on 3.11, and
  `mlops/tooling` on Python 3.9 with the venv's stock pip 21. The mlops lock (torch and CUDA, several GB) was checked
  with `pip install --dry-run --require-hashes` (every artifact downloaded and hash-checked, exit 0). The ai-gateway install first failed on
  `google-api-core[grpc]` with `--strip-extras`, so extras are kept in the locks.
- **Tests on the new locks, against the old `requirements.txt` of `devel`.** ai-gateway: 376 passed, 1 failed, the same
  as on the old pins (`test_reply_cap.py::test_the_cap_shrinks_to_the_room_left_in_the_model_window`, pre-existing).
  mcp-gateway: 127 passed, 12 failed, 4 errors, the same 16 names as on the old pins. a2a-gateway 36 passed;
  zuno-token-proxy, zuno-dify-knowledge, the four MCP servers (on 3.12 and 3.11) and the seven `evaluations/tests`
  scripts of `lint.yml` pass. trustyai-eval: ragas 0.2.15 with datasets 2.21.0 imports and builds an
  `EvaluationDataset` and a `LangchainLLMWrapper`. ai-gateway builds `ChatOpenAI` and an `openai.OpenAI` client on
  httpx 0.28.
- **Charts.** `helm lint` passes for every chart. `helm template` with every digest empty is identical to `devel` for the
  11 charts (and for `rhtas-config`, comments aside). With a digest the charts render `@sha256:`, `IfNotPresent` and no
  trigger; a malformed digest and an unknown policy mode fail the render.
- **Checks.** `check_python_locks.py` (18 locks, 0 problems) and its tests (5/5), `render_release_digests.py --check`
  and its tests (9/9), `check_docs.py`, `check_build_matrix.py`, `check_mcp_server_conformance.py`,
  `check_release_ledger.py`, `check_unifai_pins.py`, `test_pin_release.py`, `test_check_unifai_pins.py`, and the
  syntax check of the 32 playbooks with the pinned collections: all pass. `check_no_latest_tags.py` (13 hits) and
  `check_workload_hardening.py` (the keycloak chart's `helm template` error) fail as they do on `devel`.
- **Route certificates.** A `uri` task with the new `validate_certs` expression gets 200 from demo333's Keycloak with the
  switch off and on (read-only GET, no credential).

## Review fixes (2026-11-07)

A read-only review by the main session found the points below, fixed in one follow-up commit.

- **A digest-to-digest release did not roll** (high): the pod-template digest annotation, see M16 item 1.
- **Stale locks behind a range passed** (mlops, mlops/tooling): `check_python_locks.py` now parses every line of a
  `requirements.in` with `packaging` and requires the locked version to satisfy its specifier. It also refuses any
  option line (`-r`, `-e`, `--extra-index-url`, `--find-links`, ...) in a lock or a `.in`. New tests: a library added
  without a recompile, a range bumped past the lock, option lines.
- **CI verify identity** anchored to `refs/heads/main` or a `v*` tag, plus the workflow-repository check (M17 item 7).
- **`RENDER_DIGESTS=1` after an AAP-routed release** no longer renders from a ledger that is not local (M16 item 2).
- **pip, setuptools and wheel** are pinned before each lock (see Not done here for the missing hashes).
- **httpx 0.28** deprecates `verify=<path>`: ai-gateway (`providers.py`, `maas_adapter.py`, `model_readiness.py`) and
  zuno-token-proxy pass `app/tls.py`'s `verify_for(path)`, which keeps the old meaning (a bool passes through, a file is
  `cafile`, a directory `capath`, empty is the default store). Tests: `tests/test_tls_verify.py` in both.
- `reasoning.py`'s `_astream` mirror was re-read against langchain-openai 0.2.14: same helpers and signatures; the
  comment says so.

## Operator pending (each step needs the user's go)

1. **Push and merge** `wp-226-supply-chain` into `devel`, then `main`.
2. **Rebuild on the locks and the pinned bases.** Re-import the mirrors, then build every first-party image:

   ```bash
   ansible-playbook -i ansible/inventories/demo/hosts.yml ansible/playbooks/day0_install.yml -e target_component=image_mirrors
   make d1 build ai-gateway && make d1 build supply-chain-signer
   make d2 build mcp && make d2 build mlops && make d2 build trustyai-eval && make d2 build token-proxy && make d2 build dify-knowledge
   make d2 check supply-chain
   ```

3. **Warn dry run on a test namespace.** The policy only sees labelled namespaces, and the webhook refuses tag
   references there in either mode, so the test uses digests:

   ```bash
   oc create namespace zuno-wp226-cip-test
   oc label namespace zuno-wp226-cip-test policy.rhtas.com/include=true
   R=image-registry.openshift-image-registry.svc:5000/zuno-ai-build
   SIGNED=$(oc get istag ai-gateway:latest -n zuno-ai-build -o jsonpath='{.image.metadata.name}')
   UNSIGNED=$(oc get istag python:3.11-slim -n zuno-ai-build -o jsonpath='{.image.metadata.name}')
   oc run signed -n zuno-wp226-cip-test --restart=Never --image=$R/ai-gateway@$SIGNED --command -- sleep 60
   oc run unsigned -n zuno-wp226-cip-test --restart=Never --image=$R/python@$UNSIGNED --command -- sleep 60
   ```

   Expected in `warn`: both are admitted, `unsigned` with a policy warning. Fix any signed first-party image that warns.
4. **Switch to enforce.** Set `policyOperand.clusterImagePolicy.mode: enforce` in `gitops/charts/rhtas-config/values.yaml`,
   commit, push, sync `zuno-rhtas-config-d1`, then:

   ```bash
   oc get clusterimagepolicies.policy.sigstore.dev zuno-first-party-images -o jsonpath='{.spec.mode}'   # enforce
   oc run unsigned2 -n zuno-wp226-cip-test --restart=Never --image=$R/python@$UNSIGNED --command -- sleep 60      # refused
   oc run signed2 -n zuno-wp226-cip-test --restart=Never --image=$R/ai-gateway@$SIGNED --command -- sleep 60     # admitted
   oc delete namespace zuno-wp226-cip-test
   ```

   Back-out: `mode: warn`, then sync. Opting a real namespace in (`zuno-ai-run`) also needs every image there by digest,
   third-party ones included: WP-227.
5. **First rendered release**, with the go for that release: `make d3 release TAG=v0.15.0 RENDER_DIGESTS=1`, review the
   `digest:` diff, commit the ledger and the values together, merge into `main`. Back-out:
   `python3 platform/supply-chain/render_release_digests.py --clear`.
6. **Route certificate verification.** Run once with the switch on, then set the default in
   `ansible/inventories/demo/group_vars/all/main.yml` to `true`:

   ```bash
   make d0 check keycloak EXTRA_VARS="-e zuno_validate_route_certs=true"
   make d0 check aap EXTRA_VARS="-e zuno_validate_route_certs=true"
   make d0 install aap-config EXTRA_VARS="-e zuno_validate_route_certs=true"
   ```

7. **First CI-signed image** (optional; path 2 is manual-only): once Quay credentials exist, run `build-publish.yml` by
   hand and check its "Verify the signature and the SBOM attestation" step.

## Not done here

- **The AAP execution environment base** (`registry.redhat.io/.../ee-supported-rhel9:latest`) is not digest-pinned:
  resolving its digest needs a registry.redhat.io login that this workstation does not hold. Pin it at its next rebuild.
- **Unhashed tool installs.** The pip upgrade before each lock is now pinned exactly (`pip==26.0.1 setuptools==84.2.1
  wheel==0.48.0`, mlops `pip==26.0.1`), and `pyyaml==6.0.2` in the okf-release stages and the signer is pinned too, but
  none of them carries a hash: hashing them needs a requirements file the per-directory build contexts of the MCP
  servers cannot reach. Dependabot does not see these pins; bump them with the base-image refresh.
- **The ledger header** in `release_ledger.py` still says no deployment consumes the ledger. It is left as is: the
  ledger file is never hand-edited, and its header changes with the next release write.
- **History purge** of `evaluations/.venv-gate`: the user's decision (item 16).

## Live finding: warn dry run on demo333 (2026-11-07, user's go)

Namespace `zuno-wp226-cip-test` (label `policy.rhtas.com/include=true`). Both the signed `ai-gateway@sha256:d849b322…`
and the unsigned `python:3.11-slim` were admitted with the same warning: `signature keyless validation failed …
Get "https://image-registry.openshift-image-registry.svc:5000/v2/": tls: failed to verify certificate: x509:
certificate signed by unknown authority`. The policy webhook could not reach the internal registry at all, so warn mode
had been reporting every image as failed, and enforce would have refused all of them. Fix: the rhtas-config chart
renders a service-CA-injected ConfigMap and passes it as the upstream chart's `webhook.registryCaBundle`
(`SSL_CERT_DIR=/etc/custom-ca:/etc/ssl/certs`, system roots kept). Re-run the dry run after the sync before any switch
to enforce.

Re-run after the sync (2026-11-07): the signed `ai-gateway@sha256:d849b322…` passes the policy, and the unsigned
`python:3.11-slim` fails on its signature, not on TLS any more. `zuno-first-party-images` is switched to `enforce` in
git. Opted-in namespaces at the switch: unifai-operator and zuno-unifai, with no first-party image, plus the test
namespace.

