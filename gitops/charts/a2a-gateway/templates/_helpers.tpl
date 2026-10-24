{{/*
OpenShift image-change trigger: a fresh Build pushing to the ImageStreamTag rolls this Deployment
(same mechanism as mcp-gateway). Call with (dict "repository" .Values.image.repository "tag" .Values.image.tag "container" <name>).
*/}}
{{- define "a2a-gateway.imageTrigger" -}}
{{- list (dict "from" (dict "kind" "ImageStreamTag" "name" (printf "%s:%s" (base .repository) .tag) "namespace" "zuno-ai-build") "fieldPath" (printf "spec.template.spec.containers[?(@.name==\"%s\")].image" .container)) | toJson -}}
{{- end -}}
