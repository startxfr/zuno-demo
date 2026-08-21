Real `cosign sign-blob` output for each OKF agent bundle (ADR-0106/WP-05),
one `<agent>.sig` + `<agent>.pem` pair per name in `values.yaml`'s
`okfSignedAgents`. Public signature material - safe to commit, unlike a
private key. Sourced from `.github/workflows/build-publish.yml`'s
`sign-okf-bundles` job (GitHub Actions artifact `okf-signature-<agent>`,
which also includes an `<agent>.digest` file - discard it, the runtime
never reads it).

`templates/configmap-signatures.yaml` renders whichever pairs are present
here into one ConfigMap, mounted read-only at `/app/okf-signatures` -
`components/agent-runtime/app/registry.py`'s `_verify_signature()` looks
up `{name}.sig`/`{name}.pem` there, but only when
`ZUNO_REQUIRE_SIGNED_BUNDLES` is `true` (`values.yaml`'s
`requireSignedBundles`, default `false`). A partially-populated directory
is safe while that flag stays off; do not flip it on until every agent in
`okfSignedAgents` has both real files here and each has been verified
(`platform/supply-chain/sign_okf_bundle.py verify`) - see ADR-0106's
2026-08-21 implementation note.
