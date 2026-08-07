# postgresql pgvector image

This directory's `Dockerfile` adds pgvector to Crunchy Postgres
Operator's (PGO) own PostgreSQL 16 operand image
(`registry.developers.crunchydata.com/crunchydata/crunchy-postgres`) via
a `microdnf install pgvector_16` - see the `Dockerfile`'s own header
comment for why this is still necessary (PGO does not bundle pgvector
either) and for the three details flagged there as unverified against a
real pull/build (exact base tag, package manager, RPM package name).

**Built automatically** by `ansible/roles/postgresql/tasks/install.yml`
via `ansible/tasks/apply_openshift_build.yml` - the same on-cluster
`zuno-ai-build` `BuildConfig`/`ImageStream` mechanism every other
component's image in this repository uses (ADR-0056). The one thing an
operator still needs to supply is Crunchy Data developer-account
credentials, since the `Dockerfile`'s `FROM` pulls from an authenticated
registry - see below. This directory remains as the source of truth for
the build (Dockerfile) and as a manual fallback/reference for local
testing or troubleshooting a failed build.

## Crunchy Data registry access (new prerequisite vs. CloudNativePG)

Unlike CloudNativePG's public `ghcr.io` image, pulling Crunchy's base
image from `registry.developers.crunchydata.com` requires a free Crunchy
Data account - register at
[crunchydata.com/developers](https://www.crunchydata.com/developers/download-postgres/containers).

Add those credentials to `ansible/confidential.yml` as
`zuno_crunchydata_registry_username`/`zuno_crunchydata_registry_password`
(copy from `ansible/confidential.example.yml` if you haven't already -
see `ansible/README.md`) before running `make d0 install postgresql`.
`ansible/roles/postgresql/tasks/install.yml` turns these into a
`dockerconfigjson` Secret in `zuno-ai-build` and references it as the
`BuildConfig`'s `strategy.dockerStrategy.pullSecret`, so the on-cluster
build itself can authenticate the `FROM` pull - no `podman login` needed
locally. Without those two fields set, the role skips the build with a
clear warning and the `PostgresCluster` sits `ImagePullBackOff` until
they're added and the role is re-run.

## Manual build and push (fallback)

If you'd rather build locally instead of relying on the on-cluster
`BuildConfig` (e.g. troubleshooting, or a cluster whose network/policy
blocks the build pod from reaching Crunchy's registry), build from the
repository root so the build context matches how this image is expected
to be built and tagged:

```bash
cd gitops/charts/postgresql/image
podman login registry.developers.crunchydata.com   # your Crunchy Data account
podman build -t <your-registry>/<your-namespace>/postgresql-pgvector:latest .
podman push <your-registry>/<your-namespace>/postgresql-pgvector:latest
```

(`docker build`/`docker push` work identically if that's your tool of
choice.)

Then point `gitops/charts/postgresql/values.yaml`'s `image.repository`/
`image.tag` at wherever you pushed to and commit the change - the same
way any other chart default is customized in this repository. If your
cluster's internal OpenShift image registry is exposed and you'd rather
not stand up an external registry for this one image, an `oc image push
docker.io/library/postgresql-pgvector:latest
image-registry.openshift-image-registry.svc:5000/zuno-data/postgresql-pgvector:latest`
-style push after a local build works too - just make sure the `zuno-data`
namespace's default service account can pull from wherever you push to
(same-cluster internal registry pulls need no extra configuration; an
external registry needs an `imagePullSecret` on that namespace).

## Rebuilding for a different PGO/PostgreSQL version

Bump the `FROM` line in `Dockerfile` to match whatever operand image
version this cluster's PGO install actually expects for the declared
`postgresVersion` (`values.yaml`), then let `make d0 install postgresql`
rebuild it (or rebuild/push/re-point `values.yaml` manually as above).
