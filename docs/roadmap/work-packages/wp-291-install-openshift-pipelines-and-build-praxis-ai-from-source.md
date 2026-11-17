# WP-291: Install OpenShift Pipelines and build Praxis AI from source

- **State:** Repo work in review
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
4. Vault and secrets: grant the key in `platform/vault/secret-access.yaml` and `gitops/charts/external-secrets/values.yaml`. The robot is `zuno+zuno_demo` (owner, 2026-11-17); its token is in `ansible/confidential.yml` and the role writes it to Vault `zuno/quay-io/zuno-push`.
5. Role `ansible/roles/praxis_build`: it creates a `PipelineRun`, waits, and prints the digest. Wire it into `day2_build.yml` and `DAY2_BUILD_COMPONENTS`.
6. Build resources: 6 GiB of memory requested, 1 CPU. Allow egress from `zuno-ai-build` to github.com, crates.io, static.rust-lang.org, docker.io and quay.io, after checking what exists.
7. Live, each step with the owner's go:
   - check that demo333 is up;
   - install the operator;
   - the owner's robot account and Vault secret;
   - the first fork run, then one upstream run.

## Acceptance

- Both sources build. The fork digest is written in `gitops/charts/praxis/values.yaml`.
- `helm template` of both charts passes. `check_app_projects.py` and `check_secret_access.py` pass.

## Result (2026-11-17, repo)

Repo work done; nothing is applied to the cluster.

- **Operator:** component `openshift-pipelines` (Day 1, last).
  - Role `ansible/roles/openshift_pipelines`, modelled on `lightspeed`: package discovery, d0 Subscription, then a wait for `TektonConfig/config` Ready, then d1.
  - Chart `gitops/charts/openshift-pipelines` (startx `operator` 21.3.277).
  - App pair `gitops/apps/openshift-pipelines/` (d0 `zuno-platform`, d1 `zuno-apps`).
  - Nodes in the AAP day-1 DAG and surveys; Makefile `DAY1_RUN_COMPONENTS`; the four day-1 playbooks.
- **Pipeline:** `source-image-build` (git-clone, then buildah, through the cluster resolver) and the ExternalSecret `quay-io-zuno-push`.
  - Both are in the same chart, d1, instead of a separate `source-builds` chart: one component, one removal path.
  - The push key `quay-io/zuno-push` (properties `username`, `token`) is granted to `zuno-ai-build` in `platform/vault/secret-access.yaml`.
- **Build:** component `praxis` (Day 2 build), role `ansible/roles/praxis_build`.
  - The source switch lives in the role defaults, not in chart values, because the role creates the run.
  - Revision resolved to a full SHA by `git ls-remote`; image tag `<source>-<sha12>`.
  - The run carries `sidecar.istio.io/inject: "false"`; the build task requests 1 CPU and 6 Gi (no CPU limit; the general workers have under 2.1 CPU free, live recon finding 5).
  - The role prints the digest. Feature names were checked in both `server/Cargo.toml` files: `api-key-auth-filter` is fork-only.
  - Wired into `day2_build.yml`, the AAP day-2 build DAG and its survey, and `DAY2_BUILD_COMPONENTS`.
- **Checks:** `check_docs.py`, `check_app_projects.py`, `check_secret_access.py`, `check_mesh_mtls.py`, `helm lint` and the ansible syntax check pass.
- **Live steps remaining**, each with the owner's go:
  1. `make d1 install openshift-pipelines`;
  2. the owner's quay.io robot for `zuno/praxis-ai` and its token in Vault;
  3. `make d2 build praxis`, then `-e zuno_praxis_build_source=upstream`.

  Before step 3, check that the catalog tasks are named `git-clone` and `buildah` in `openshift-pipelines` on this operator version.

## Live, 2026-11-17

The owner gave the go for the operator install. The run was `ansible-playbook ... day1_install.yml -e target_component=openshift-pipelines -e zuno_gitops_target_revision=devel`, from a worktree, on devel `f8d1e0ae`.

- **Installed:** OpenShift Pipelines 1.24.3, Succeeded. `TektonConfig/config` is Ready.
- **Catalog:** the tasks `git-clone` and `buildah` are in `openshift-pipelines`, and the default ServiceAccount `pipeline` exists in `zuno-ai-build`.
- **Applications:** `zuno-openshift-pipelines-d0` is Synced/Healthy. `zuno-openshift-pipelines-d1` is Synced, with the Pipeline `source-image-build` created, but Degraded: the ExternalSecret `quay-io-zuno-push` reports `SecretSyncedError`, because the robot is not in Vault yet.
- **Finding:** a worktree has no `ansible/confidential.yml` and devel has no `ansible/branch-pin.yml`. A local run from a worktree must therefore pass `-e zuno_gitops_target_revision=devel`, or the Applications would point at `main`. The first attempt was stopped before any apply.

