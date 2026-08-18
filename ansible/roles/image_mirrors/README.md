# image_mirrors

Mirrors every public-registry image this platform depends on (Go/Node/Python
build bases, UBI9/distroless runtime bases, HashiCorp Vault, Bitnami
kubectl/Redis, PostgreSQL, the RHOAI KServe storage-initializer, the RHOAI
OGX core distribution image) into
`ImageStream`s in `zuno-ai-build`, `referencePolicy: Local` on every tag so
the in-cluster registry caches/pull-throughs each image on first use instead
of every build or pod (re)start hitting `docker.io`/`quay.io`/`gcr.io`/
`registry.redhat.io` directly. No OLM operator, no ArgoCD Application - same
raw-`kubernetes.core.k8s` pattern `ansible/tasks/apply_openshift_build.yml`
already uses for the `zuno-ai-build` namespace's own build-output
ImageStreams (ADR-0056 keeps this namespace's ImageStream/BuildConfig
objects out of the GitOps-tracked flow on purpose).

Every Dockerfile/Containerfile `FROM` and every consuming chart's `image:`
field points at the mirrored `image-registry.openshift-image-registry.svc:
5000/zuno-ai-build/<name>:<tag>` path instead of the public registry.

## Why this exists

Reduces this platform's dependency on external registries during builds and
pod (re)starts, and gives every namespace a single, auditable place
(`oc get imagestream -n zuno-ai-build`) to see exactly which upstream image
+ tag/digest every component is really running.

Three mirrors (`ubi9-ubi-minimal`, `odh-kserve-storage-initializer-rhel9`,
`odh-ogx-core-rhel9`) are imported by digest with `importPolicy.scheduled:
false` so they never drift - the same digest-pinning intent as ADR-0051,
extended to the mirror itself. `odh-ogx-core-rhel9` exists specifically to
work around the OGX Operator's own in-process OCI-manifest-fetch client
401ing against `registry.redhat.io` directly, even with a valid cluster
pull secret (WP-06/ADR-0322) - `gitops/charts/openshift-ai`'s `OGXServer`
points its `distribution.image` at this mirror instead.
`quay.io/modh/vllm` (`gitops/charts/models`) is intentionally **not**
mirrored: ADR-0048 has Ansible dynamically discover and override the real
serving image from the live OpenShift AI catalog at apply time, so the
static `values.yaml` fallback is never what's actually deployed - mirroring
it wouldn't reduce real `quay.io` traffic.

## Day 0 ordering

Positioned right after `namespaces` (`ansible/playbooks/day0_install.yml`)
and before every consumer - `vault`/`redis` need their mirrored images at
Day 0, and every `*_build` role's BuildConfig (Day 1) needs its Dockerfile's
base images mirrored before the first build runs. `zuno-ai-build` itself
already exists by this point (created by the `namespaces` role's chart, see
`gitops/charts/namespaces/values.yaml`), so this role only creates the
ImageStreams and the cross-namespace `system:image-puller` grant.
