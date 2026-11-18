{{- define "openclaw.keycloakHost" -}}{{ .Values.keycloak.host | default (printf "keycloak.%s" .Values.clusterBaseDomain) }}{{- end -}}
{{- define "openclaw.issuer" -}}https://{{ include "openclaw.keycloakHost" . }}/realms/{{ .Values.keycloak.realm }}{{- end -}}

{{/* WP-301 (ADR-0619 clause 5): the host of an alternative gateway's url, which the operator's proxy matches the credential by. */}}
{{- define "openclaw.altGatewayDomain" -}}
{{- regexReplaceAll "^https?://([^/:]+).*$" .url "${1}" -}}
{{- end -}}

{{/* Renders nothing; fails the render on a malformed altGateways entry. */}}
{{- define "openclaw.altGatewayCheck" -}}
{{- if not (regexMatch "^[a-z0-9]([a-z0-9-]{0,38}[a-z0-9])?$" (toString .name)) }}{{ fail (printf "altGateways: name %q must be a DNS label of at most 40 characters" (toString .name)) }}{{ end -}}
{{- if not (regexMatch "^https?://[^/ ]+" (toString .url)) }}{{ fail (printf "altGateways: %s: url must be an http(s) URL" .name) }}{{ end -}}
{{- end -}}
