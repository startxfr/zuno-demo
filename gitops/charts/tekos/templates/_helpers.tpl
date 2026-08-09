{{/*
Route host: "tekos.<clusterBaseDomain>" unless overridden; must stay
predictable since the OIDC redirect URI depends on it.
*/}}
{{- define "tekos.routeHost" -}}
{{- if .Values.frontend.route.host -}}
{{ .Values.frontend.route.host }}
{{- else -}}
tekos.{{ .Values.global.clusterBaseDomain }}
{{- end -}}
{{- end -}}

{{/*
Keycloak issuer URL, defaulting to the sso.<clusterBaseDomain> convention.
*/}}
{{- define "tekos.keycloakIssuerUrl" -}}
{{- if .Values.keycloak.issuerUrl -}}
{{ .Values.keycloak.issuerUrl }}
{{- else -}}
https://sso.{{ .Values.global.clusterBaseDomain }}/realms/zuno
{{- end -}}
{{- end -}}

{{- define "tekos.selfBaseUrl" -}}
https://{{ include "tekos.routeHost" . }}
{{- end -}}

{{- define "tekos.frontendImage" -}}
{{ .Values.image.registry }}/{{ .Values.image.frontendRepository }}:{{ .Values.image.tag }}
{{- end -}}

{{- define "tekos.bffImage" -}}
{{ .Values.image.registry }}/{{ .Values.image.bffRepository }}:{{ .Values.image.tag }}
{{- end -}}
