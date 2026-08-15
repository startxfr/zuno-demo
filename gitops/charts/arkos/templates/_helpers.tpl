{{/*
Route host: "arkos.<clusterBaseDomain>" unless overridden; must stay
predictable since the OIDC redirect URI depends on it.
*/}}
{{- define "arkos.routeHost" -}}
{{- if .Values.frontend.route.host -}}
{{ .Values.frontend.route.host }}
{{- else -}}
arkos.{{ .Values.global.clusterBaseDomain }}
{{- end -}}
{{- end -}}

{{/*
Keycloak issuer URL, defaulting to the Keycloak CR's actual Route hostname
(keycloak.<clusterBaseDomain> - see gitops/charts/keycloak/templates/keycloak.yaml).
*/}}
{{- define "arkos.keycloakIssuerUrl" -}}
{{- if .Values.keycloak.issuerUrl -}}
{{ .Values.keycloak.issuerUrl }}
{{- else -}}
https://keycloak.{{ .Values.global.clusterBaseDomain }}/realms/zuno
{{- end -}}
{{- end -}}

{{- define "arkos.selfBaseUrl" -}}
https://{{ include "arkos.routeHost" . }}
{{- end -}}

{{- define "arkos.frontendImage" -}}
{{ .Values.image.registry }}/{{ .Values.image.frontendRepository }}:{{ .Values.image.tag }}
{{- end -}}

{{- define "arkos.bffImage" -}}
{{ .Values.image.registry }}/{{ .Values.image.bffRepository }}:{{ .Values.image.tag }}
{{- end -}}
