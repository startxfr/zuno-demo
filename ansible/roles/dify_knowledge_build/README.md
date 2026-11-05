# dify_knowledge_build

Day 2 build component `dify-knowledge` (`make d2 build dify-knowledge`): builds
`components/zuno-dify-knowledge` (ADR-0599, WP-205) into `zuno-ai-build/zuno-dify-knowledge`
and lets the `zuno-dify-knowledge` ServiceAccount of `zuno_dify_knowledge_namespace` pull it.
Deployed by `gitops/charts/zuno-dify-knowledge`, applied by `make d2 install dify`.
