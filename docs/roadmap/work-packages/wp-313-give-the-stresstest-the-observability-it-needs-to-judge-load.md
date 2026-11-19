# WP-313: Give the stresstest the observability it needs to judge load

- **State:** Repo work in review (2026-11-19: dashboards and the Authorino ServiceMonitor done; the Limitador counter reader and the zero-initialised counters remain)
- **ADRs:** ADR-0624 (clause 9)
- **Depends on:** none
- **Related:** WP-306, WP-312
- **Target:** v0.17
- **Estimated files touched:** ~8: the Grafana and Perses ai-models, infra-data and world-model dashboards, gitops/charts/connectivity-link/templates/servicemonitor-authorino.yaml, components/ai-gateway/app/telemetry.py, platform/testing/

## Goal

A stress campaign can be judged from the dashboards: GPU use, model queues and latency, auth decisions and budget burn
are visible, and a counter does not read zero after a restart.

## Steps

1. vLLM metric renames in the ai-models dashboards (Grafana and Perses): `vllm:gpu_cache_usage_perc` is now
   `vllm:kv_cache_usage_perc`, `vllm:time_per_output_token_seconds` is now `vllm:inter_token_latency_seconds`
   (measured 2026-11-19: 1926 vllm:* series, the old names absent). Done.
2. DCGM metrics after the GPU operator update of 2026-11-19: the exporter now names its series with units
   (`DCGM_FI_DEV_FB_USED_BYTES`, `DCGM_FI_DEV_FB_FREE_BYTES`, `DCGM_FI_DEV_GPU_TEMP_CELSIUS`,
   `DCGM_FI_DEV_BOARD_POWER_WATTS`, `DCGM_FI_PROF_GR_ENGINE_UTIL_RATIO`) and the node label is `hostname`. GPU
   utilisation under MIG is read from `DCGM_FI_PROF_GR_ENGINE_UTIL_RATIO` per GPU instance (`exported_pod`), since
   `DCGM_FI_DEV_GPU_UTIL` is not exported with MIG. Framebuffer is summed per physical GPU, in bytes. Done in the
   ai-models, infra-data and world-model dashboards.
3. Authorino: a second ServiceMonitor endpoint on `/server-metrics`, where the `auth_server_*` decision counters live
   (read inside the pod 2026-11-19: `/metrics` holds none of them). Done.
4. A Limitador counter reader for the stress report: the per-limit counters are not exported as metrics, so the report
   reads `/counters/<namespace>` of the Limitador HTTP API before and after a run (the proof of WP-306 that a load run
   leaves the ai-gateway ServiceAccount's MaaS counter unchanged). To do.
5. Zero-initialised counters in the ai-gateway (and the mcp-gateway): the OTel counters are created at their first event,
   so after a restart `rate()`/`increase()` miss the first events of each label set. Pre-create the known label sets at
   0. Ships with the WP-306 image roll. To do.

## Acceptance

- The rendered dashboards are valid JSON (helm template), and each changed query returns series on demo333.
- `auth_server_*` series appear in Prometheus after the connectivity-link sync.
- A stress report shows the Limitador counters before and after the run.
- After an ai-gateway restart, `increase(zuno_model_calls_total[1h])` counts the first calls.
