{{- define "world-model.keycloakIssuer" -}}
{{- .Values.global.zuno.keycloakIssuerUrl | default (printf "https://keycloak.%s/realms/zuno" .Values.global.zuno.clusterBaseDomain) -}}
{{- end -}}
{{- define "world-model.keycloakHost" -}}
{{- .Values.global.zuno.keycloakHost | default (printf "keycloak.%s" .Values.global.zuno.clusterBaseDomain) -}}
{{- end -}}
{{- define "world-model.podSecurity" -}}
securityContext:
  runAsNonRoot: true
  seccompProfile:
    type: RuntimeDefault
{{- end -}}
{{- define "world-model.containerSecurity" -}}
securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: ["ALL"]
{{- end -}}
