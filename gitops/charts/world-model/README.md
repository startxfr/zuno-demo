# world-model chart

ADR-0604, WP-235. The interactive generative world-model experience in `zuno-world-model`: the GPU runtime, the web tier and
its oauth2-proxy front door. Applied and deleted **only** by `ansible/roles/world_model` (Application `zuno-world-model-d1`),
which follows `zuno_world_model_enabled` and needs the on-demand GPU node of `gitops/apps/machines-world-model`. With the demo
off, nothing from this chart exists.

| Object | Why |
|---|---|
| `world-model-runtime` Deployment (+ Service) | One GPU (`nvidia.com/gpu: 1`), `Recreate`, only on the node labelled `zuno.io/gpu-workload=world-model` (toleration `zuno.io/gpu-world-model`). An init container copies the pinned weights from S3 into an `emptyDir` (`files/fetch_models.py`); ready only after both models are loaded and warmed (`startupProbe` 20 min); `NVIDIA_DRIVER_CAPABILITIES=compute,utility,video` for NVENC |
| `world-model-web` Deployment (+ Service) | Browser API and UI; one replica, `Recreate` (the GPU lease is in memory) |
| `world-model-front-door` + `Route world-model` | oauth2-proxy admits the groups, forwards and refreshes the user's token (`--pass-access-token`, `--cookie-refresh=10m`, the access token lives 15 min); the only Route; 30 min timeout for the stream |
| 3 `ExternalSecret`s | Front door client and cookie secrets, the web/runtime token, S3 read; from Vault through the namespace's own SecretStore |
| `NetworkPolicy` + `EgressFirewall` | DNS, the namespace, the ai-gateway; outside the cluster only Keycloak and the model bucket's S3 hosts |
| 2 `ServiceMonitor`s | `/metrics` of the runtime and the web tier |

The pinned model revisions in `values.yaml` must equal `platform/world-model/models.lock.yaml`
(`platform/world-model/tests/check_pins.py`, run in CI). The weights live in the bucket's own region (`eu-west-2`), not the cluster's.
