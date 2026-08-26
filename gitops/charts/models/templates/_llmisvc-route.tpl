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

Parameters (dict):
  name           - LLMInferenceService name; also the path segment, the
                   InferencePool name prefix (<name>-inference-pool) and
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
      - group: inference.networking.k8s.io
        kind: InferencePool
        name: {{ $root.name }}-inference-pool
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
      - group: inference.networking.k8s.io
        kind: InferencePool
        name: {{ $root.name }}-inference-pool
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
{{- end -}}
