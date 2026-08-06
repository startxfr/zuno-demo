{{/*
Route host: fixed to "vault.<clusterBaseDomain>" unless explicitly
overridden via route.host - same predictable-hostname convention as the
tekos and keycloak charts' own route/hostname helpers.
*/}}
{{- define "vault.routeHost" -}}
{{- if .Values.route.host -}}
{{ .Values.route.host }}
{{- else -}}
vault.{{ .Values.global.clusterBaseDomain }}
{{- end -}}
{{- end -}}

{{/*
Name of the upstream hashicorp/vault chart's "-ui" Service. Replicates
that chart's own vault.fullname helper (fullnameOverride unset, and the
release name is always "zuno-vault" - see gitops/apps/vault/application.yaml
and ansible/roles/vault/tasks/prepare.yml's gitops_app_name comment - which
already contains "vault", so fullname == .Release.Name) rather than
vendoring or re-templating the dependency chart just for this.
*/}}
{{- define "vault.uiServiceName" -}}
{{- if contains "vault" .Release.Name -}}
{{ .Release.Name }}-ui
{{- else -}}
{{ .Release.Name }}-vault-ui
{{- end -}}
{{- end -}}
