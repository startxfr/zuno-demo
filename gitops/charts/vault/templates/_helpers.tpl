{{/*
Route host: "vault.<clusterBaseDomain>" unless overridden via route.host.
*/}}
{{- define "vault.routeHost" -}}
{{- if .Values.route.host -}}
{{ .Values.route.host }}
{{- else -}}
vault.{{ .Values.global.clusterBaseDomain }}
{{- end -}}
{{- end -}}

{{/*
Name of the upstream hashicorp/vault chart's "-ui" Service, replicating
that chart's own vault.fullname helper.
*/}}
{{- define "vault.uiServiceName" -}}
{{- if contains "vault" .Release.Name -}}
{{ .Release.Name }}-ui
{{- else -}}
{{ .Release.Name }}-vault-ui
{{- end -}}
{{- end -}}
