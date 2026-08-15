{{/*
Route host: "advantage.<clusterBaseDomain>" unless overridden; must stay
predictable since the OIDC redirect URI depends on it.
*/}}
{{- define "advantage.routeHost" -}}
{{- if .Values.frontend.route.host -}}
{{ .Values.frontend.route.host }}
{{- else -}}
advantage.{{ .Values.global.clusterBaseDomain }}
{{- end -}}
{{- end -}}

{{/*
Keycloak issuer URL, defaulting to the Keycloak CR's actual Route hostname
(keycloak.<clusterBaseDomain> - see gitops/charts/keycloak/templates/keycloak.yaml).
*/}}
{{- define "advantage.keycloakIssuerUrl" -}}
{{- if .Values.keycloak.issuerUrl -}}
{{ .Values.keycloak.issuerUrl }}
{{- else -}}
https://keycloak.{{ .Values.global.clusterBaseDomain }}/realms/zuno
{{- end -}}
{{- end -}}

{{- define "advantage.selfBaseUrl" -}}
https://{{ include "advantage.routeHost" . }}
{{- end -}}

{{- define "advantage.frontendImage" -}}
{{ .Values.image.registry }}/{{ .Values.image.frontendRepository }}:{{ .Values.image.tag }}
{{- end -}}

{{- define "advantage.bffImage" -}}
{{ .Values.image.registry }}/{{ .Values.image.bffRepository }}:{{ .Values.image.tag }}
{{- end -}}
