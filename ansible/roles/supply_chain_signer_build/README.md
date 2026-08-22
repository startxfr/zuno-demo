# supply_chain_signer_build

Day 1 `build` component (ADR-0420/WP-068, `make day1|d1 build supply-chain-signer`).
Builds `supply-chain-signer` via native OpenShift `BuildConfig`/`ImageStream` in
`zuno-ai-build` - see `ansible/tasks/apply_openshift_build.yml` for the shared
mechanism. Also creates the `zuno-signer` ServiceAccount in that namespace,
which `ansible/roles/vault`'s Transit block binds its `platform-signer`
Kubernetes-auth role to - without this ServiceAccount existing first, that
role's `bound_service_account_names=zuno-signer` binds to nothing.

Not a Day 1 `run` component: this image backs one-off debug pods and (from
WP-069 onward) a signing Job, never a long-running Deployment of its own.
