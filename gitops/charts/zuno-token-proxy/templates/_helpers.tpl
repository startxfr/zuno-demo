{{/* Required inputs, checked once. */}}
{{- define "zuno-token-proxy.validate" -}}
{{- if not .Values.namespace }}{{ fail "namespace is required" }}{{ end -}}
{{- if not .Values.clientId }}{{ fail "clientId is required" }}{{ end -}}
{{- end -}}

{{/*
WP-297 (ADR-0619 clause 5): the ALT_GATEWAYS env of the proxy, from the `altGateways` contract: a JSON list of
{name, url, headers, timeout_s?}. `label` and `models` are the client's side of the contract and are not sent.
*/}}
{{- define "zuno-token-proxy.altGateways" -}}
{{- $out := list -}}
{{- range .Values.altGateways -}}
{{- if not (regexMatch "^[a-z0-9]([a-z0-9-]{0,38}[a-z0-9])?$" (toString .name)) }}{{ fail (printf "altGateways: name %q must be a DNS label of at most 40 characters" (toString .name)) }}{{ end -}}
{{- if not (regexMatch "^https?://[^/ ]+" (toString .url)) }}{{ fail (printf "altGateways: %s: url must be an http(s) URL" .name) }}{{ end -}}
{{- $entry := dict "name" .name "url" .url "headers" (.headers | default $.Values.aiHeaders) -}}
{{- if .timeoutSeconds }}{{ $_ := set $entry "timeout_s" (float64 .timeoutSeconds) }}{{ end -}}
{{- $out = append $out $entry -}}
{{- end -}}
{{- $out | toJson -}}
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

{{/*
ADR-0603 M16 (WP-226 review): pod-template annotations naming the rendered
digests. The Applications ignore /spec/template/spec/containers/0/image (the
:latest image trigger patches it), so a release moving @A to @B changes no
field ArgoCD compares; this annotation does, and rolls the pods. Empty when no
digest is rendered, so the :latest path renders exactly as before.
*/}}
{{- define "zuno-token-proxy.digestAnnotations" -}}
{{- if .image.digest }}
zuno.io/image-digest: {{ .image.digest | quote }}
{{- end }}
{{- if and .okf .okf.fetch .okf.fetch.image .okf.fetch.image.digest }}
zuno.io/okf-fetch-image-digest: {{ .okf.fetch.image.digest | quote }}
{{- end }}
{{- end -}}
