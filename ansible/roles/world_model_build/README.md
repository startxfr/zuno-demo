# world_model_build (Day 2 build)

ADR-0604, WP-231. `make d2 build world-model` builds `zuno-ai-build/world-model-runtime` in-cluster from
`components/world-model-runtime/Dockerfile` (signed by the existing chain, `ansible/tasks/apply_openshift_build.yml`) and
lets the `world-model-runtime` and `world-model-web` ServiceAccounts of `zuno-world-model` pull it. No GPU is needed to
build: the image runs on CPU with the mock adapters. It is about 10 GB (torch with its CUDA libraries), so check the
build nodes' ephemeral storage before the first build.
