# WP-224: live rehearsal on demo333 (2026-11-06/07)

The objects were applied by hand with `oc apply`, outside ArgoCD, one step at a time, each with the user's go. They
were rendered from branch `wp-224-network-gitops`.

## 0. Preconditions

- No PeerAuthentication existed anywhere in the cluster, so "mTLS-enforced" in older comments was never true.
- No EgressFirewall existed in zuno-ai-run or zuno-unifai.
- No pod in zuno-ai-run, zuno-auth or zuno-data was unhealthy.
- Baseline monitoring: 18 of 19 targets up in the three namespaces. `zuno-guardrails-smoke-service` was already down.

## 1. PERMISSIVE baseline (2026-11-06 22:15 UTC)

- 15 PeerAuthentications created (3 namespace defaults, 12 workload exceptions).
- istiod pushed them with no error.
- The Keycloak Route answered 200.
- Monitoring still showed 18/19 up.
- istiod logs "Conflicting inbound listener:8000" between the `*-kserve-workload-svc` and `*-inference-pool-ip-*`
  Services of each model. KServe creates both Services, so the conflict is unrelated to these objects.

## 2. Plaintext inbound observed

- **Mesh Prometheus coverage is partial.** It scrapes only 3 of about 30 sidecars (guardrails, guardrails-smoke and
  evalhub), because the namespace NetworkPolicies do not admit zuno-mesh on port 15090.
- **Per-sidecar counters instead.** Each sidecar's own counters were read (`pilot-agent request GET
  stats/prometheus`, read-only exec, 36 series). They count `reporter="destination"` and
  `connection_security_policy="none"` since pod start.

| Namespace | Destination | Source | Covered by |
|---|---|---|---|
| zuno-data | the three Postgres instances, about 13,800 HTTP requests each | unknown (monitoring and Patroni) | 9187 / 8008 |
| zuno-data | the Postgres primary, 1 TCP connection | unknown | unexplained; watched under STRICT |
| zuno-auth | Keycloak `zuno-service`, 576 HTTP requests | unknown (router) | 8080 |
| zuno-auth | `zuno-redis-metrics` | unknown (monitoring) | 9121 |
| zuno-ai-run | ai-, mcp- and a2a-gateway | unknown (unmeshed clients) | 8080 |
| zuno-ai-run | the four vLLM workloads, TCP | unknown | 8000 |
| zuno-ai-run | the EPP schedulers | unknown (monitoring) | 9090 |
| zuno-ai-run | embeddings-predictor | unknown, and `redhat-ods-applications/zuno-ogx` | 8080 |
| zuno-ai-run | evalhub, guardrails-smoke | unknown | 8443/8081, 8080 |

## 3a. zuno-data STRICT (2026-11-06 22:41 UTC)

After 3 minutes:
- **Monitoring:** 18/19 up, unchanged. The three `postgres-exporter` targets are up.
- **Database:** Patroni has one leader and two replicas streaming, with 0 lag. No pod restarted.
- **Sidecars:** none of the three Postgres sidecars logged a `filter_chain_not_found`, `tls_error` or certificate
  error.
- **Applications:** the Keycloak realm and the UnifAI UI both answered 200.

A 30-minute watch (monitoring targets, restarts, pod state, sidecar TLS errors) then ran:

<!-- results appended as the rehearsal proceeds -->

## 3b. zuno-auth STRICT (2026-11-06 22:53 UTC)

Before the switch, ingress sources and monitors in zuno-auth were checked:
- Keycloak, its operator and Redis all carry a sidecar.
- The only monitor is the `zuno-redis` ServiceMonitor.
- The only external Redis client is ai-gateway, which is meshed.

Checks after the switch, all within 1 minute:

| Path | Result |
|---|---|
| OIDC discovery through the public Route (router → Keycloak 8080, PERMISSIVE) | 200 |
| `client_credentials` token through the public Route (client `dify`) | issued; `iss=https://keycloak.apps.demo333.startx.fr/realms/zuno`, `aud=[zuno-admin-api, account]` |
| meshed ai-gateway → `zuno-service:8080` JWKS (mTLS) | 200 |
| meshed ai-gateway → Redis 6379 (mTLS) | answers (`NOAUTH`, the expected reply without a password) |
| unmeshed AAP gateway pod → `zuno-service:8080` (PERMISSIVE exception) | 200 |
| `zuno-redis-metrics` monitoring target | up |
| Keycloak and Redis sidecars: TLS or filter-chain errors | 0 |

The user then signed in through Open WebUI and UnifAI with a demo persona and through AAP SSO. All three logins worked.

## 3c. zuno-ai-run STRICT (2026-11-06 23:15 UTC)

- **Before the switch:** 14 of 15 targets up (`zuno-guardrails-smoke-service` was already down). Every
  ServiceMonitor/PodMonitor port maps to an exception (`vllm-predictors`/`embeddings-metrics` → embeddings 8080, the
  schedulers → 9090, evalhub 8081, guardrails-smoke 8080, the vLLM engines' https 8000).
- **Unmeshed callers (from `zuno-unifai/unifai-multiagent-be`):** `/healthz` returned 200 on ai-gateway, mcp-gateway
  and a2a-gateway, and `/health` returned 200 on embeddings-predictor.
- **ai-gateway `/readyz`:** 200. Its routing config is loaded and its model readiness reaches the API server.
- **Routes through the router (both reach the application, not a router error):**
  - guardrails `/health`: 404 (that path is not served).
  - evalhub `/`: 401 (authentication required).
- **Real traffic in the 12 minutes after the switch (Prometheus):**
  - `zuno_model_calls_total` grew by about 10 for `unifai` and 1 for `open-webui`, and vLLM successful requests went
    up.
  - One tool call went through the mcp-gateway, `outcome=allowed`, with 0 `downstream_error`.
- **Logs:** no ERROR, 5xx or Traceback in the last 15 minutes of the ai-, mcp- and a2a-gateway logs. No TLS,
  filter-chain or upstream-connect error in the gateway, predictor or vLLM sidecars.
- **Not tested here:** a scripted end-to-end chat with a client secret, which the session's safety classifier refused.
  The user's own sessions in UnifAI and Open WebUI generated the traffic above.

## 4. Egress: preparation

The open question from the report was whether gpt-oss-20b downloads its tiktoken vocabulary from
`openaipublic.blob.core.windows.net` when it restarts. It does not. Both encodings
(`fb374d41…` = o200k_base, `9b5ad71b…`) are baked into the image at `/opt/app-root/tiktoken-cache`, and the image's
`TIKTOKEN_RS_CACHE_DIR` points there. No allowlist entry is needed.

The zuno-ai-run allowlist was checked against every external URL in the live Deployment env and ConfigMaps.
`aap-mcp` reaches AAP through `aap.zuno-aap.svc`; its public AAP URL only builds links. The zuno-unifai firewall waits
for the end of another session's UnifAI canary window on demo333 (decision of 2026-11-07).

## 4a. zuno-ai-run EgressFirewall (2026-11-06 23:50 UTC)

The user applied the firewall (`oc apply` of the rendered `default` EgressFirewall). Its status is `EgressFirewall
Rules applied`. Real HTTPS requests were then made from ai-gateway, the actual client of the providers:

| Destination | Result |
|---|---|
| `api.mistral.ai`, `api.anthropic.com`, `api.openai.com` | HTTP 401: reached (no key sent) |
| `oai.endpoints.kepler.ai.cloud.ovh.net/v1/models` | HTTP 200 |
| `generativelanguage.googleapis.com` | HTTP 404: reached |
| `startxfr.atlassian.net`, `api.github.com`, Keycloak public Route (tested from mcp-gateway) | 202 / 200 / 200 |
| `example.com`, `pypi.org` (not allowed) | **blocked**: TLS handshake timeout |

There are two traps to know when testing a meshed namespace:
- **A bare TCP connect "succeeds" for every host.** The Istio sidecar accepts the outbound connection locally before it
  tries the upstream, so only a real TLS or HTTP request proves the firewall.
- **A direct HTTPS call to Mistral or OVH from any pod other than ai-gateway gets "connection reset".** The
  `mistral-large` and `gpt-oss-120b-ovhcloud` DestinationRules originate TLS (SIMPLE) for every workload except
  ai-gateway, which has a DISABLE rule because it speaks TLS itself. The app's TLS is then wrapped a second time. This
  is the configuration, not the firewall.

### Automated tests after the firewall (2026-11-07 ~00:00 UTC)

- **`make d3 test` (availability): 15/15 PASS.**
  - All 8 agent bundles ready in UnifAI.
  - ai-gateway and mcp-gateway `/healthz` and `/readyz`.
  - unifai-multiagent and unifai-rag health.
  - The Lightspeed API.
- **`make d2 check agents` (ADR-0053 acceptance gate): FAIL, caused by the firewall.**
  - The gate Job (`docker.io/library/python:3.12-slim`, `ansible/roles/agents/tasks/run_acceptance_gate.yml:248`)
    installs its requirements from PyPI at start-up. The zuno-ai-run firewall now blocks PyPI ("connection reset"
    on `/simple/httpx/`), so the Job failed before running any scenario.
  - The same gate passed at 2026-11-06 22:49 UTC (18/18 scenarios, 14/14 security, 5/5 gate checks). That run had
    zuno-data in STRICT and no firewall yet.
  - The firewall did its job here. It also exposed a supply-chain weakness: an unpinned, unhashed runtime package
    download in a namespace that runs agent content.

### Second finding: okf-fetch needs quay.io (reported by session zuno-demo-a8, 2026-11-07)

- **Symptom.** A rebuilt a2a-gateway pod stayed in `Init:CrashLoopBackOff`.
- **Cause.** Its `okf-fetch` init container runs `cosign verify --offline` against the signed OKF bundles on
  `quay.io/zuno/okf-*`. With the firewall in place it failed with `Get "https://quay.io/v2/": TLS handshake timeout`.
- **Exposure.** Pods already running were unaffected. Any restart of a2a-gateway or mcp-gateway would have hit the
  same failure.
- **Fix.** `quay.io` and `cdn01`/`cdn02`/`cdn03.quay.io` are added to the allowlist; the CDN hosts serve Quay's blob
  redirects.
- **Lesson.** An allowlist built only from the env and ConfigMaps of running pods misses what init containers and
  start-up scripts fetch. Every Deployment restart path has to be exercised once.

## Watch after STRICT on all three namespaces

Two 30-minute watches ran, from 2026-11-06 22:48 to 2026-11-07 about 00:00 UTC. They checked monitoring targets,
pods not ready and container restarts in zuno-data, zuno-auth and zuno-ai-run. The only event was one false positive
from the watch script itself; there was no real anomaly.
