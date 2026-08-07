# postgresql pgvector image

This directory's `Dockerfile` adds pgvector to Crunchy Postgres
Operator's (PGO) own PostgreSQL 16 operand image
(`registry.developers.crunchydata.com/crunchydata/crunchy-postgres`) via
a `microdnf install pgvector_16` - see the `Dockerfile`'s own header
comment for why this is still necessary (PGO does not bundle pgvector
either) and for the three details flagged there as unverified against a
real pull/build (exact base tag, package manager, RPM package name).
This is the one manual prerequisite `ansible/roles/postgresql/README.md`
refers to: the `PostgresCluster` this repository applies
(`gitops/charts/postgresql/templates/postgrescluster.yaml`) references
this image by name, and cannot start until it exists in a registry the
cluster can actually pull from.

## Crunchy Data registry access (new prerequisite vs. CloudNativePG)

Unlike CloudNativePG's public `ghcr.io` image, pulling Crunchy's base
image from `registry.developers.crunchydata.com` requires a free Crunchy
Data account - register at
[crunchydata.com/developers](https://www.crunchydata.com/developers/download-postgres/containers)
and `podman login registry.developers.crunchydata.com` with those
credentials before the `podman build` step below can pull the `FROM`
image.

## Build and push

Build from the repository root so the build context matches how this
image is expected to be built and tagged:

```bash
cd gitops/charts/postgresql/image
podman build -t <your-registry>/<your-namespace>/postgresql-pgvector:16-crunchy .
podman push <your-registry>/<your-namespace>/postgresql-pgvector:16-crunchy
```

(`docker build`/`docker push` work identically if that's your tool of
choice.)

`values.yaml`'s `image.repository`/`image.tag` default to a placeholder
(`image-registry.zuno-demo.internal/zuno/postgresql-pgvector:16-crunchy`)
that does not correspond to a real registry - it exists only so `helm
template`/`helm lint` have something concrete to render.
`ansible/roles/postgresql/tasks/install.yml` applies this chart with no
Helm value overrides today (unlike e.g. `ansible/roles/models`, which does
inject a discovered image via `apply_gitops_app.yml`'s
`gitops_app_extra_helm_values`), so the only way to point this chart at
whatever you actually pushed to is editing `gitops/charts/postgresql/
values.yaml`'s `image.repository`/`image.tag` directly and committing the
change, the same way any other chart default is customized in this
repository.

If your cluster's internal OpenShift image registry is exposed and you'd
rather not stand up an external registry for this one image, an
`oc image push docker.io/library/postgresql-pgvector:16-crunchy
image-registry.openshift-image-registry.svc:5000/zuno-data/postgresql-pgvector:16-crunchy`
-style push after a local build works too - just make sure the `zuno-data`
namespace's default service account can pull from wherever you push to
(same-cluster internal registry pulls need no extra configuration; an
external registry needs an `imagePullSecret` on that namespace).

## Rebuilding for a different PGO/PostgreSQL version

Bump the `FROM` line in `Dockerfile` to match whatever operand image
version this cluster's PGO install actually expects for the declared
`postgresVersion` (`values.yaml`), then rebuild/push/re-point `values.yaml`
as above.
