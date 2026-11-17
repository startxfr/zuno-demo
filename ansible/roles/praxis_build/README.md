# praxis_build

ADR-0620 (WP-291). `make d2 build praxis` builds Praxis AI from source with the
`source-image-build` Pipeline of `gitops/charts/openshift-pipelines` and pushes it to
`quay.io/zuno/praxis-ai`.

- **Source:** `zuno_praxis_build_source` selects `fork` (`redhat-et/praxis-ai`, the default)
  or `upstream` (`praxis-proxy/ai`). The revision is resolved to a full SHA before the run.
- **Image tag:** `<source>-<sha12>`.
- **Features:** set per source in `defaults/main.yml`, passed as the Containerfile's
  `PRAXIS_AI_FEATURES`.
- **Output:** the role prints the pushed digest. The digest, never a tag, is pinned in
  `gitops/charts/praxis/values.yaml`.

Prerequisites:
- `make d1 install openshift-pipelines`;
- the owner's quay.io robot token in Vault at `quay-io/zuno-praxis-ai-push`, with properties
  `username` and `token`.
