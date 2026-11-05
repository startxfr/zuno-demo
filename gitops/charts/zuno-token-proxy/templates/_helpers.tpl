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
