# openshift_pipelines

ADR-0620 (WP-291). A Day 1 component that installs the Red Hat OpenShift Pipelines
operator, then the generic `source-image-build` Pipeline in `zuno-ai-build`.

- **d0** (`zuno-openshift-pipelines-d0`, project `zuno-platform`): the Subscription
  `openshift-pipelines-operator-rh` in `openshift-operators`. Its channel and catalog are
  discovered from the PackageManifest (ADR-0048).
- **d1** (`zuno-openshift-pipelines-d1`, project `zuno-apps`): the Pipeline and the quay.io
  push Secret (an ExternalSecret reading `quay-io/zuno-praxis-ai-push`, granted in
  `platform/vault/secret-access.yaml`).

The install waits for the operator's `TektonConfig/config` to be Ready before it applies d1,
because the Pipeline kind and the catalog tasks only exist after that.

Runs are not created here: a build role (`ansible/roles/praxis_build`, `make d2 build praxis`)
creates a `PipelineRun` and waits for it.

First-party components keep `BuildConfig`, as ADR-0056 decided. This operator serves only
third-party images built from source.
