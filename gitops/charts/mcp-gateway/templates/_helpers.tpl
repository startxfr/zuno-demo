{{/*
OpenShift image-change trigger: patches the named container's image
field directly from the ImageStreamTag whenever a fresh Build pushes to
it, so a rebuild rolls this Deployment with no manual pod deletion.
Call with (dict "repository" .Values.image.repository "tag" .Values.image.tag "container" <container name>).
`base` strips the registry+namespace prefix down to the bare ImageStream
name the trigger's `from.name` expects (the stream itself always lives
in zuno-ai-build regardless of this chart's own namespace - see
ansible/tasks/apply_openshift_build.yml).
*/}}
{{- define "mcp-gateway.imageTrigger" -}}
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
{{- define "mcp-gateway.imageRef" -}}
{{- if .digest -}}
{{- if not (regexMatch "^sha256:[0-9a-f]{64}$" .digest) -}}
{{- fail (printf "image digest %q is not sha256:<64 hex>" .digest) -}}
{{- end -}}
{{- printf "%s@%s" .repository .digest -}}
{{- else -}}
{{- printf "%s:%s" .repository .tag -}}
{{- end -}}
{{- end -}}

{{- define "mcp-gateway.imagePullPolicy" -}}
{{- if .digest -}}IfNotPresent{{- else -}}{{ .pullPolicy }}{{- end -}}
{{- end -}}
