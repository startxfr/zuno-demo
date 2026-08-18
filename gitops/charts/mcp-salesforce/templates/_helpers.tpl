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
{{- define "mcp-salesforce.imageTrigger" -}}
{{- list (dict "from" (dict "kind" "ImageStreamTag" "name" (printf "%s:%s" (base .repository) .tag) "namespace" "zuno-ai-build") "fieldPath" (printf "spec.template.spec.containers[?(@.name==\"%s\")].image" .container)) | toJson -}}
{{- end -}}
