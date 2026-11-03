{{- define "openclaw.keycloakHost" -}}keycloak.{{ .Values.clusterBaseDomain }}{{- end -}}
{{- define "openclaw.issuer" -}}https://{{ include "openclaw.keycloakHost" . }}/realms/{{ .Values.keycloak.realm }}{{- end -}}
