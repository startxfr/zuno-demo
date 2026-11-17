# ADR-0620: Build third-party images from source with OpenShift Pipelines and push them to quay.io

- **Status:** Accepted
- **Target:** v0.17
- **Date:** 2026-11-17
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md),
  [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md),
  [ADR-0420](0420-sign-supply-chain-artifacts-in-cluster-with-vault-transit.md),
  [ADR-0612](0612-serve-every-zuno-image-from-an-internal-red-hat-quay-backed-by-an-s3-bucket.md),
  [ADR-0619](0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)

## Context

Praxis AI ([ADR-0619](0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)) must be
built from source:
- the published images do not carry the features the demo needs;
- the fork's own image is pushed to a personal Quay namespace.

The owner asked for a Tekton pipeline (2026-11-17). It must build the fork `https://github.com/redhat-et/praxis-ai`
by default, be able to switch to the upstream `https://github.com/praxis-proxy/ai`, and push to quay.io.

ADR-0056 rejected Tekton for day-1 builds in favour of `BuildConfig`. Its reason was to avoid one more operator in the
day-0 prerequisites.

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | Neither OpenShift Pipelines nor any Tekton object is installed or used by the repository. ArgoCD already excludes `TaskRun` and `PipelineRun`. | `ansible/roles/argocd/kustomize/argocd/argocd.yaml`; ADR-0056 "Alternatives considered" |
| F2 | The fork builds its image from a `Containerfile` with the build argument `PRAXIS_AI_FEATURES` (default `full`). The builder is `rust:1.99-alpine3.24`. | `Containerfile` of `redhat-et/praxis-ai` at `0c024ef` |
| F3 | The fork's own image goes to `quay.io/modden/praxis-ai`, "an interim personal namespace". | `docs/enmaas-image-publishing.md` of the fork |
| F4 | The repository already publishes to the `quay.io/zuno` organisation, through the manual `build-publish.yml` workflow. | `.github/workflows/build-publish.yml` |
| F5 | Third-party images are trusted by digest pin, not by signature. The first-party ClusterImagePolicy covers only `zuno-ai-build` images of the internal registry. | `platform/supply-chain/mirrored-images.yaml`, `gitops/charts/rhtas-config/templates/clusterimagepolicy.yaml` |

## Decision

**Third-party images that the demo must build from source are built by an OpenShift Pipelines (Tekton) pipeline in
`zuno-ai-build`, from a pinned commit of a selectable source repository, and pushed to `quay.io/zuno/<name>`. First-party
images keep `BuildConfig`.**

1. **Install OpenShift Pipelines by GitOps.** The Red Hat operator `openshift-pipelines-operator-rh` is installed from
   the chart `gitops/charts/openshift-pipelines`. This amends ADR-0056 for this case only. Its `BuildConfig` path
   stays the one for first-party components.
2. **One generic pipeline.** `source-image-build` runs git-clone then buildah, both tasks taken from the operator's
   catalog through the cluster resolver. Its parameters are `git-url`, `git-revision`, `containerfile`, `build-args`,
   `image` and `tag`.
3. **The source is a switch.** The image's build role defaults (`ansible/roles/<name>_build/defaults/main.yml`) hold, per image:
   - the fork and upstream URLs and default revisions;
   - a `source: fork|upstream` switch;
   - the build arguments for each source.

   For Praxis, the fork is the default.
4. **Push to quay.io/zuno.**
   - The owner creates a robot account and writes its token to Vault; the sessions never handle it. An ExternalSecret
     turns it into the pipeline's push secret.
   - The pipeline reports the pushed digest. The chart pins that digest, never a tag.
5. **Trust by digest, as for mirrored images.** The image is not signed in this record. Tekton Chains signing with
   Vault Transit (ADR-0420) is a later option.
6. **A run is explicit.** An Ansible build role creates a `PipelineRun` and waits for it (`make d2 build praxis`).
   There are no triggers or webhooks.

## Alternatives considered

- **`BuildConfig`, as in ADR-0056.** No new operator, and it would work. Not chosen, at the owner's request: the
  pipeline is meant to be shown and reused for the other gateways.
- **GitHub Actions.** It puts nothing in the cluster. Not chosen, because it keeps the build out of the demo platform
  and needs push secrets in GitHub.
- **Use the fork's published image.** It sits in a personal namespace and lacks the needed features.

## Consequences

- One more operator on the cluster, cluster-wide.
- A Rust release build takes tens of minutes and several GiB of memory on a worker.

## Security considerations

- **Build egress:** the build pods reach github.com, crates.io, static.rust-lang.org, docker.io and quay.io.
- **Push secret:** the robot token is scoped to the `zuno/praxis-ai` repository.
- **What the images can contain:** a build runs code from the selected repository at the selected commit, so only the
  two listed repositories are allowed as sources.

## Operational considerations

- The operator install and the first `PipelineRun` each need the owner's go.
- The digest written into `gitops/charts/praxis/values.yaml` is the release record.

## Work packages

[WP-291](../roadmap/work-packages/wp-291-install-openshift-pipelines-and-build-praxis-ai-from-source.md) (operator, pipeline, push, first build).

## Update 2026-11-17 (WP-291): the push robot is zuno+zuno_demo, kept in confidential.yml

The owner chose on 2026-11-17 to reuse the zuno organisation's robot `zuno+zuno_demo` rather than create a new one, and
gave it write on `quay.io/zuno/praxis-ai`. This replaces the owner's Vault write described in clause 4. The robot's name
and token live in `ansible/confidential.yml` (`zuno_quay_io_push_username`, `zuno_quay_io_push_token`; template in
`ansible/confidential.example.yml`). `make d1 install openshift-pipelines` writes them to Vault `zuno/quay-io/zuno-push`
through `ansible/tasks/vault_cli.yml`, so no secret appears on a command line.

The first install on demo333 (2026-11-17) brought:
- OpenShift Pipelines 1.24.3 (channel `latest`), with `TektonConfig/config` Ready;
- the catalog tasks `git-clone` and `buildah` in `openshift-pipelines`;
- the `source-image-build` Pipeline in `zuno-ai-build`.

The d1 Application stays Degraded until the robot is in Vault, because its ExternalSecret has nothing to read.

