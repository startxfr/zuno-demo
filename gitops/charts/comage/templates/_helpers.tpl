{{/*
Route host: "comage.<clusterBaseDomain>" unless overridden; must stay
predictable since the OIDC redirect URI depends on it.
*/}}
{{- define "comage.routeHost" -}}
{{- if .Values.frontend.route.host -}}
{{ .Values.frontend.route.host }}
{{- else -}}
comage.{{ .Values.global.clusterBaseDomain }}
{{- end -}}
{{- end -}}

{{/*
Keycloak issuer URL, defaulting to the Keycloak CR's actual Route hostname
(keycloak.<clusterBaseDomain> - see gitops/charts/keycloak/templates/keycloak.yaml).
*/}}
{{- define "comage.keycloakIssuerUrl" -}}
{{- if .Values.keycloak.issuerUrl -}}
{{ .Values.keycloak.issuerUrl }}
{{- else -}}
https://keycloak.{{ .Values.global.clusterBaseDomain }}/realms/zuno
{{- end -}}
{{- end -}}

{{- define "comage.selfBaseUrl" -}}
https://{{ include "comage.routeHost" . }}
{{- end -}}

{{- define "comage.frontendImage" -}}
{{ .Values.image.registry }}/{{ .Values.image.frontendRepository }}:{{ .Values.image.tag }}
{{- end -}}

{{- define "comage.bffImage" -}}
{{ .Values.image.registry }}/{{ .Values.image.bffRepository }}:{{ .Values.image.tag }}
{{- end -}}
