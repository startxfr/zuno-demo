{{/* Required inputs, checked once. */}}
{{- define "zuno-token-proxy.validate" -}}
{{- if not .Values.namespace }}{{ fail "namespace is required" }}{{ end -}}
{{- if not .Values.clientId }}{{ fail "clientId is required" }}{{ end -}}
{{- end -}}

{{- define "zuno-token-proxy.tokenUrl" -}}
{{- .Values.tokenUrl | default (printf "https://keycloak.%s/realms/zuno/protocol/openid-connect/token" .Values.clusterBaseDomain) -}}
{{- end -}}

{{/* Same image-change trigger as the gateways: a fresh Build rolls the Deployment. */}}
{{- define "zuno-token-proxy.imageTrigger" -}}
{{- list (dict "from" (dict "kind" "ImageStreamTag" "name" (printf "%s:%s" (base .Values.image.repository) .Values.image.tag) "namespace" "zuno-ai-build") "fieldPath" "spec.template.spec.containers[?(@.name==\"zuno-token-proxy\")].image") | toJson -}}
{{- end -}}

{{/*
ADR-0603 M16 (WP-226): the image reference of a first-party container. Called
with an image values map (repository, tag, digest, pullPolicy). When a release
has rendered `digest` (platform/supply-chain/render_release_digests.py), the
reference is repository@digest and the pull policy IfNotPresent: the bytes are
fixed, a re-pull adds nothing. Without a digest it stays repository:tag with the
chart's pull policy, the ADR-0059 `:latest` path.
*/}}
{{- define "zuno-token-proxy.imageRef" -}}
{{- if .digest -}}
{{- if not (regexMatch "^sha256:[0-9a-f]{64}$" .digest) -}}
{{- fail (printf "image digest %q is not sha256:<64 hex>" .digest) -}}
{{- end -}}
{{- printf "%s@%s" .repository .digest -}}
{{- else -}}
{{- printf "%s:%s" .repository .tag -}}
{{- end -}}
{{- end -}}

{{- define "zuno-token-proxy.imagePullPolicy" -}}
{{- if .digest -}}IfNotPresent{{- else -}}{{ .pullPolicy }}{{- end -}}
{{- end -}}
