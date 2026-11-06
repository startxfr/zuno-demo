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
Name of the upstream hashicorp/vault chart's client Service (the one
carrying the service-ca serving cert), replicating that chart's own
vault.fullname helper. ADR-0602 clause 1 / WP-223: the Route targets this
Service rather than the "-ui" one, because a reencrypt Route verifies the
backend certificate against the Service it points at, and only the client
Service's name is in the cert.
*/}}
{{- define "vault.serverServiceName" -}}
{{- if contains "vault" .Release.Name -}}
{{ .Release.Name }}
{{- else -}}
{{ .Release.Name }}-vault
{{- end -}}
{{- end -}}
