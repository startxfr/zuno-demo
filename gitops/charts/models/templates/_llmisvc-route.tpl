{{- /*
ADR-0521 (WP-076), 2026-08-26 live incident: KServe's LLMInferenceService
controller generates every model's HTTPRoute with the SAME rule names
(v1-chat-completions-path, v1-completions-model-routing, ... - confirmed
identical on gpt-oss-20b's and qwen36-27b-instruct's generated routes),
and Istio keys the per-route ext_proc override that wires a route to its
InferencePool's endpoint-picker (EPP) by that rule name. On a shared
gateway (maas-default-gateway - MaaS mandates route adoption there, no
per-model gateway is possible) the names collide and ONE model's EPP
captures the override on EVERY route: proven live via the gateway's Envoy
config dump, where all of gpt-oss-20b's routes carried
outbound|9002||qwen36-27b-instruct-epp-service while a test route with a
unique rule name got its own model's EPP back immediately.

The visible symptom is far worse than misrouted scheduling: the EPP tells
Envoy per-request (ext_proc mode_override) whether it wants the response
stream, and for traffic it never scheduled it skips it - but the route's
FULL_DUPLEX_STREAMED response body mode can't actually downgrade, so the
response body chunks are handed to a gRPC stream nobody reads and Envoy
fails open WITHOUT them: HTTP 200, correct headers, empty body, on every
MaaS-routed completion (isolated live: 6/6 full bodies on the EPP-less
catch-all rule vs 0/6 on the EPP rule, same gateway/auth/usage filters).

Fix: stop relying on KServe's generated rule names - supply the full
route spec ourselves via spec.router.route.http.spec (the CRD's
user-managed route escape hatch), byte-for-byte identical to what the
controller generates (mirrored from the live generated routes, including
the 0s timeouts and trailing-slash match variants) EXCEPT every rule name
is prefixed with the model's own name, making them unique per model on
the shared gateway.

SECOND deliberate deviation (same incident, second root cause): every
rule's backendRef is the plain workload Service, NOT the InferencePool
the controller would generate. Fixing the name collision alone restored
gpt-oss-20b (8/8 full bodies) but NOT qwen (1/8, then 0/8 with a fresh,
correctly-wired EPP): even a model's OWN endpoint-picker drops response
bodies whenever its response-headers reply reaches Envoy BEFORE the
response body has propagated into the EPP's filter position. Envoy's
ext_proc then takes the buffered-chunk-after-headers-response path,
forwards the chunk to the EPP and CONTINUES WITHOUT AWAITING the echo
(observed in ext_proc trace: "Sending a chunk of buffered data" ->
"Continuing processing" -> onDestroy, vs the healthy "Sending body data
... without_waiting_for_header_response" -> "Received response body
response" -> inject) - in FULL_DUPLEX_STREAMED the server owns the body,
so the client gets 200 + headers + nothing. Which side of the race a
request lands on is decided by the gateway<->EPP RTT: qwen's EPP pod is
co-located with the gateway pod (sub-ms reply, loses always - confirmed
0/8 immediately after a clean EPP pod restart on the same node), gpt-oss's
sits on another node (reply arrives after the body, wins always). An
upstream Envoy/llm-d bug, not a Zuno config error.

A Service backend generates no per-route EPP ext_proc override at all, so
no response-path ext_proc filter exists to lose the race - proven 6/6
reliable on the controller's own catch-all rules (Service-backed) while
the InferencePool rules were 0/6, same listener. Nothing else changes:
Kuadrant auth + TokenRateLimitPolicy target the HTTPRoute/gateway (not
the backend kind) and the ipp usage-metering ext_proc chain is
listener-level - all stay active. What is genuinely given up is llm-d
load-aware endpoint picking, which is worth exactly nothing at
replicas: 1 (both models, MIG-constrained). The controller still deploys
the scheduler/EPP (its defaulting always adds it) - it just serves no
route. Revisit when a model goes multi-replica or RHOAI fixes the race;
the interim alternative documented in the WP-076 evidence doc is
scheduler anti-affinity against the gateway's node (keeps the EPP in the
path but makes it always lose the race - fragile, latency-dependent).

Parameters (dict):
  name           - LLMInferenceService name; also the path segment and
                   the workload Service prefix (<name>-kserve-workload-svc)
  namespace      - model namespace (path segment + publishers/<ns>/...)
  publishedModel - spec.model.name, NOT the k8s resource name (qwen's is
                   "qwen3.6-27b-instruct" with dots) - the controller
                   derives the X-Gateway-Model-Name match value
                   publishers/<ns>/models/<model.name> from it
  gatewayName / gatewayNamespace - the adopting Gateway parentRef
*/ -}}
{{- define "models.llmisvcRouteSpec" -}}
parentRefs:
  - group: gateway.networking.k8s.io
    kind: Gateway
    name: {{ .gatewayName }}
    namespace: {{ .gatewayNamespace }}
rules:
{{- $root := . }}
{{- range $ep := list "completions" "chat/completions" "responses" "messages" }}
{{- $slug := $ep | replace "/" "-" }}
  - name: {{ $root.name }}-v1-{{ $slug }}-path
    matches:
      - path:
          type: PathPrefix
          value: /{{ $root.namespace }}/{{ $root.name }}/v1/{{ $ep }}
    filters:
      - type: URLRewrite
        urlRewrite:
          path:
            type: ReplacePrefixMatch
            replacePrefixMatch: /v1/{{ $ep }}
    backendRefs:
      - group: ""
        kind: Service
        name: {{ $root.name }}-kserve-workload-svc
        port: 8000
        weight: 1
    timeouts:
      backendRequest: 0s
      request: 0s
  - name: {{ $root.name }}-v1-{{ $slug }}-model-routing
    matches:
      - headers:
          - name: X-Gateway-Model-Name
            type: Exact
            value: publishers/{{ $root.namespace }}/models/{{ $root.publishedModel }}
        path:
          type: Exact
          value: /v1/{{ $ep }}
      - headers:
          - name: X-Gateway-Model-Name
            type: Exact
            value: publishers/{{ $root.namespace }}/models/{{ $root.publishedModel }}
        path:
          type: Exact
          value: /v1/{{ $ep }}/
    backendRefs:
      - group: ""
        kind: Service
        name: {{ $root.name }}-kserve-workload-svc
        port: 8000
        weight: 1
    timeouts:
      backendRequest: 0s
      request: 0s
{{- end }}
  - name: {{ .name }}-v1-catch-all-path
    matches:
      - path:
          type: PathPrefix
          value: /{{ .namespace }}/{{ .name }}
    filters:
      - type: URLRewrite
        urlRewrite:
          path:
            type: ReplacePrefixMatch
            replacePrefixMatch: /
    backendRefs:
      - group: ""
        kind: Service
        name: {{ .name }}-kserve-workload-svc
        port: 8000
        weight: 1
    timeouts:
      backendRequest: 0s
      request: 0s
  - name: {{ .name }}-v1-catch-all-model-routing
    matches:
      - headers:
          - name: X-Gateway-Model-Name
            type: Exact
            value: publishers/{{ .namespace }}/models/{{ .publishedModel }}
        path:
          type: PathPrefix
          value: /
    backendRefs:
      - group: ""
        kind: Service
        name: {{ .name }}-kserve-workload-svc
        port: 8000
        weight: 1
    timeouts:
      backendRequest: 0s
      request: 0s
  # Status-plane anchor, NOT a traffic rule (2026-08-26, same incident as
  # the header comment): KServe gates the LLMInferenceService's
  # InferencePoolReady condition on its InferencePool being referenced by
  # an accepted gateway route, and switching every real rule above to
  # Service backends left the pool unreferenced - LLMISvc Ready=False
  # (WaitingForGateway), which MaaSModelRef then surfaces as
  # Unhealthy/BackendNotReady even though traffic is fine. This rule's
  # only job is to reference the pool: an Exact match on a path nothing
  # ever calls (vLLM serves no such endpoint anyway - a stray hit would
  # 404 at the backend, or drop its body to the ext_proc race like any
  # EPP-routed response, which is exactly why real rules avoid the pool).
  # The per-route EPP ext_proc override Istio generates for it exists
  # only on this dead route.
  - name: {{ .name }}-inference-pool-anchor
    matches:
      - path:
          type: Exact
          value: /{{ .namespace }}/{{ .name }}/.zuno-pool-anchor
    backendRefs:
      - group: inference.networking.k8s.io
        kind: InferencePool
        name: {{ .name }}-inference-pool
        port: 8000
        weight: 1
    timeouts:
      backendRequest: 0s
      request: 0s
{{- end -}}
