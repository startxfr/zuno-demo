# postgresql pgvector image

This directory's `Dockerfile` adds pgvector to the stock CloudNativePG
operand image (`ghcr.io/cloudnative-pg/postgresql:16-bookworm`) via
`apt-get install postgresql-16-pgvector` - see the `Dockerfile`'s own
header comment for why this approach was chosen over CNPG's newer
ImageVolume extension mechanism. This is the one manual prerequisite
`ansible/roles/postgresql/README.md` refers to: the `Cluster` this
repository applies (`gitops/charts/postgresql/templates/cluster.yaml`)
references this image by name, and cannot start until it exists in a
registry the cluster can actually pull from.

## Build and push

Build from the repository root so the build context matches how this
image is expected to be built and tagged:

```bash
cd gitops/charts/postgresql/image
podman build -t <your-registry>/<your-namespace>/postgresql-pgvector:16-bookworm .
podman push <your-registry>/<your-namespace>/postgresql-pgvector:16-bookworm
```

(`docker build`/`docker push` work identically if that's your tool of
choice.)

`values.yaml`'s `image.repository`/`image.tag` default to a placeholder
(`image-registry.zuno-demo.internal/zuno/postgresql-pgvector:16-bookworm`)
that does not correspond to a real registry - it exists only so `helm
template`/`helm lint` have something concrete to render.
`ansible/roles/postgresql/tasks/configure.yml` applies this chart with no
Helm value overrides today (unlike e.g. `ansible/roles/models`, which does
inject a discovered image via `apply_gitops_app.yml`'s
`gitops_app_extra_helm_values`), so the only way to point this chart at
whatever you actually pushed to is editing `gitops/charts/postgresql/
values.yaml`'s `image.repository`/`image.tag` directly and committing the
change, the same way any other chart default is customized in this
repository.

If your cluster's internal OpenShift image registry is exposed and you'd
rather not stand up an external registry for this one image, an
`oc image push docker.io/library/postgresql-pgvector:16-bookworm
image-registry.openshift-image-registry.svc:5000/zuno-data/postgresql-pgvector:16-bookworm`
-style push after a local build works too - just make sure the `zuno-data`
namespace's default service account can pull from wherever you push to
(same-cluster internal registry pulls need no extra configuration; an
external registry needs an `imagePullSecret` on that namespace).

## Rebuilding for a different CNPG/PostgreSQL version

Bump the `FROM` line in `Dockerfile` to match whatever operand image
version `ansible/roles/postgresql/tasks/prepare.yml`'s CNPG `stable`
channel actually installs, then rebuild/push/re-point `values.yaml` as
above.
