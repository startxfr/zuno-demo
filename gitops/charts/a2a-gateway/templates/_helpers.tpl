{{/*
OpenShift image-change trigger: a fresh Build pushing to the ImageStreamTag rolls this Deployment
(same mechanism as mcp-gateway). Call with (dict "repository" .Values.image.repository "tag" .Values.image.tag "container" <name>).
*/}}
{{- define "a2a-gateway.imageTrigger" -}}
{{- list (dict "from" (dict "kind" "ImageStreamTag" "name" (printf "%s:%s" (base .repository) .tag) "namespace" "zuno-ai-build") "fieldPath" (printf "spec.template.spec.containers[?(@.name==\"%s\")].image" .container)) | toJson -}}
{{- end -}}

{{/*
ADR-0603 M16 (WP-226): the image reference of a first-party container. Called
with an image values map (repository, tag, digest, pullPolicy). When a release
has rendered `digest` (platform/supply-chain/render_release_digests.py), the
reference is repository@digest and the pull policy IfNotPresent: the bytes are
fixed, a re-pull adds nothing. Without a digest it stays repository:tag with the
chart's pull policy, the ADR-0059 `:latest` path.
*/}}
{{- define "a2a-gateway.imageRef" -}}
{{- if .digest -}}
{{- if not (regexMatch "^sha256:[0-9a-f]{64}$" .digest) -}}
{{- fail (printf "image digest %q is not sha256:<64 hex>" .digest) -}}
{{- end -}}
{{- printf "%s@%s" .repository .digest -}}
{{- else -}}
{{- printf "%s:%s" .repository .tag -}}
{{- end -}}
{{- end -}}

{{- define "a2a-gateway.imagePullPolicy" -}}
{{- if .digest -}}IfNotPresent{{- else -}}{{ .pullPolicy }}{{- end -}}
{{- end -}}
