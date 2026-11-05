{{/* Same image-change trigger as the gateways: a fresh Build rolls the Deployment. */}}
{{- define "zuno-dify-knowledge.imageTrigger" -}}
{{- list (dict "from" (dict "kind" "ImageStreamTag" "name" (printf "%s:%s" (base .Values.image.repository) .Values.image.tag) "namespace" "zuno-ai-build") "fieldPath" "spec.template.spec.containers[?(@.name==\"zuno-dify-knowledge\")].image") | toJson -}}
{{- end -}}
