# openshift_pipelines

ADR-0620 (WP-291). A Day 1 component that installs the Red Hat OpenShift Pipelines
operator, then the generic `source-image-build` Pipeline in `zuno-ai-build`.

- **d0** (`zuno-openshift-pipelines-d0`, project `zuno-platform`): the Subscription
  `openshift-pipelines-operator-rh` in `openshift-operators`. Its channel and catalog are
  discovered from the PackageManifest (ADR-0048).
- **d1** (`zuno-openshift-pipelines-d1`, project `zuno-apps`): the Pipeline and the quay.io
  push Secret (an ExternalSecret reading `quay-io/zuno-push`, granted in
  `platform/vault/secret-access.yaml`).

The install waits for the operator's `TektonConfig/config` to be Ready before it applies d1,
because the Pipeline kind and the catalog tasks only exist after that.

The push robot comes from `ansible/inventories/<cluster>/confidential.yml` (`zuno_quay_io_push_username`, default
`zuno+zuno_demo`, and `zuno_quay_io_push_token`). When the token is set, the install writes both
to Vault `zuno/quay-io/zuno-push` before it applies d1.

Writing the key is not enough for the ExternalSecret to read it. Vault's policy for the
namespace role `ns-zuno-ai-build` is written by the vault role's configure Job from
`platform/vault/secret-access.yaml`. On a cluster installed before the grant, run
`make d1 install vault` once, or the ExternalSecret reports `403 permission denied` and d1
stays Degraded.

Runs are not created here: a build role (`ansible/roles/praxis_build`, `make d2 build praxis`)
creates a `PipelineRun` and waits for it.

First-party components keep `BuildConfig`, as ADR-0056 decided. This operator serves only
third-party images built from source.
