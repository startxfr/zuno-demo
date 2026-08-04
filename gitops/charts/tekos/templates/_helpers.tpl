{{/*
Route host: fixed to "tekos.<clusterBaseDomain>" unless explicitly
overridden, since the OIDC redirect URI contract
(https://<agent>.apps.<cluster-domain>/*) needs a predictable hostname.
*/}}
{{- define "tekos.routeHost" -}}
{{- if .Values.frontend.route.host -}}
{{ .Values.frontend.route.host }}
{{- else -}}
tekos.{{ .Values.global.clusterBaseDomain }}
{{- end -}}
{{- end -}}

{{/*
Keycloak issuer URL, defaulting to the sso.<clusterBaseDomain> convention
documented in values.yaml and components/agent-frontend/README.md.
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
