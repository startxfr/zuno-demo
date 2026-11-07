{{- define "openclaw.keycloakHost" -}}{{ .Values.keycloak.host | default (printf "keycloak.%s" .Values.clusterBaseDomain) }}{{- end -}}
{{- define "openclaw.issuer" -}}https://{{ include "openclaw.keycloakHost" . }}/realms/{{ .Values.keycloak.realm }}{{- end -}}
