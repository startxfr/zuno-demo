# WP-291: Install OpenShift Pipelines and build Praxis AI from source

- **State:** Not started
- **ADRs:** [ADR-0620](../../adr/0620-build-third-party-images-from-source-with-openshift-pipelines-and-push-them-to-quay-io.md)
- **Depends on:** none
- **Related:** [ADR-0619](../../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)
- **Target:** v0.17
- **Estimated files touched:** ~14: two new charts, their app pairs, a build role, the Makefile, the Vault grants

## Goal

Build `quay.io/zuno/praxis-ai` from the fork `https://github.com/redhat-et/praxis-ai` (or the upstream `https://github.com/praxis-proxy/ai`) with a Tekton pipeline, and pin the digest.

## Steps

1. Chart `gitops/charts/openshift-pipelines`: the Subscription `openshift-pipelines-operator-rh`. App pair `gitops/apps/openshift-pipelines/application-d{0,1}.yaml`, synced before the builds.
2. Chart `gitops/charts/source-builds` in `zuno-ai-build`:
   - the Pipeline `source-image-build`: git-clone, then buildah, from the cluster resolver; params `git-url`, `git-revision`, `containerfile`, `build-args`, `image`, `tag`;
   - its ServiceAccount;
   - an ExternalSecret for the push secret.
3. Values `sources.praxis`:
   - `fork` and `upstream` (URL, default revision, `PRAXIS_AI_FEATURES`), and `source: fork`;
   - fork features: `full,api-key-auth-filter,token-rate-limit-filter,opentelemetry`;
   - upstream: the same minus fork-only features. Check each name in `server/Cargo.toml` before the first run.
4. Vault and secrets: grant the key in `platform/vault/secret-access.yaml` and `gitops/charts/external-secrets/values.yaml`. The owner creates the quay.io robot and writes the token.
5. Role `ansible/roles/praxis_build`: it creates a `PipelineRun`, waits, and prints the digest. Wire it into `day2_build.yml` and `DAY2_BUILD_COMPONENTS`.
6. Build resources: about 8 GiB of memory. Allow egress from `zuno-ai-build` to github.com, crates.io, static.rust-lang.org, docker.io and quay.io, after checking what exists.
7. Live, each step with the owner's go:
   - check that demo333 is up;
   - install the operator;
   - the owner's robot account and Vault secret;
   - the first fork run, then one upstream run.

## Acceptance

- Both sources build. The fork digest is written in `gitops/charts/praxis/values.yaml`.
- `helm template` of both charts passes. `check_app_projects.py` and `check_secret_access.py` pass.
