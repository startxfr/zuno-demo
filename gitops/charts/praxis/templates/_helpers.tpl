{{/*
ADR-0603 M16: the image reference, always by digest (ADR-0619 clause 7). Fails when the digest is not sha256:<64 hex>.
*/}}
{{- define "praxis.imageRef" -}}
{{- if not (regexMatch "^sha256:[0-9a-f]{64}$" .digest) -}}
{{- fail (printf "image digest %q is not sha256:<64 hex>" .digest) -}}
{{- end -}}
{{- printf "%s@%s" .repository .digest -}}
{{- end -}}

{{- define "praxis.issuer" -}}
{{- .Values.keycloak.issuer | default (printf "https://keycloak.%s/realms/zuno" .Values.clusterBaseDomain) -}}
{{- end -}}

{{- define "praxis.jwksUrl" -}}
{{- .Values.keycloak.jwksUrl | default (printf "%s/protocol/openid-connect/certs" (include "praxis.issuer" .)) -}}
{{- end -}}

{{/* The host of the issuer URL: the only private address the policy engine may reach (the JWKS through the Route). */}}
{{- define "praxis.issuerHost" -}}
{{- (urlParse (include "praxis.issuer" .)).host -}}
{{- end -}}

{{/* The direct KServe Service of a model: <service>-kserve-workload-svc.<namespace>.svc */}}
{{- define "praxis.directHost" -}}
{{- printf "%s-kserve-workload-svc.%s.svc" .service .ns -}}
{{- end -}}

{{/* The models a client may name, for the policy route and /v1/models. */}}
{{- define "praxis.modelNames" -}}
{{- $names := list .Values.alias.name -}}
{{- range .Values.models }}{{ $names = append $names .name }}{{ end -}}
{{- if .Values.saas.enabled }}{{ $names = append $names .Values.saas.claude.name }}{{ $names = append $names .Values.saas.codestral.name }}{{ end -}}
{{- toJson $names -}}
{{- end -}}

{{/* The OpenAI-style model objects of GET /v1/models, from a JSON list of names. */}}
{{- define "praxis.modelList" -}}
{{- $out := list -}}
{{- range . }}{{ $out = append $out (dict "id" . "object" "model" "owned_by" "zuno") }}{{ end -}}
{{- toJson $out -}}
{{- end -}}

{{/* The sovereign models a client may name: the alias and the local models, as a JSON list. */}}
{{- define "praxis.sovereignModels" -}}
{{- $names := list .Values.alias.name -}}
{{- range .Values.models }}{{ $names = append $names .name }}{{ end -}}
{{- toJson $names -}}
{{- end -}}

{{/*
The request half of the Anthropic Messages translation, for a router step. It must sit inside the step, before the
step's load_balancer: Praxis rewrites the body only once an upstream is selected, and only steps select upstreams.
The condition keeps the OpenAI requests (Open WebUI and the other clients on /v1/chat/completions) untouched.
*/}}
{{- define "praxis.messagesToChat" -}}
- filter: anthropic_messages_to_chat_completions
  allow_lossy_features: [prompt_caching, extended_thinking]
  conditions:
    - when:
        path: "/v1/messages"
{{- end }}
