{{/*
Route host: "finage.<clusterBaseDomain>" unless overridden; must stay
predictable since the OIDC redirect URI depends on it.
*/}}
{{- define "finage.routeHost" -}}
{{- if .Values.frontend.route.host -}}
{{ .Values.frontend.route.host }}
{{- else -}}
finage.{{ .Values.global.clusterBaseDomain }}
{{- end -}}
{{- end -}}

{{/*
Keycloak issuer URL, defaulting to the Keycloak CR's actual Route hostname
(keycloak.<clusterBaseDomain> - see gitops/charts/keycloak/templates/keycloak.yaml).
*/}}
{{- define "finage.keycloakIssuerUrl" -}}
{{- if .Values.keycloak.issuerUrl -}}
{{ .Values.keycloak.issuerUrl }}
{{- else -}}
https://keycloak.{{ .Values.global.clusterBaseDomain }}/realms/zuno
{{- end -}}
{{- end -}}

{{- define "finage.selfBaseUrl" -}}
https://{{ include "finage.routeHost" . }}
{{- end -}}

{{- define "finage.frontendImage" -}}
{{ .Values.image.registry }}/{{ .Values.image.frontendRepository }}:{{ .Values.image.tag }}
{{- end -}}

{{- define "finage.bffImage" -}}
{{ .Values.image.registry }}/{{ .Values.image.bffRepository }}:{{ .Values.image.tag }}
{{- end -}}

{{/*
OpenShift image-change trigger: patches the named container's image
field directly from the ImageStreamTag whenever a fresh Build pushes to
it, so a rebuild rolls this Deployment with no manual pod deletion.
Call with (dict "repository" <values.image.*Repository> "tag" .Values.image.tag "container" <container name>).
The ImageStream lives in zuno-ai-build regardless of this chart's own
namespace (see ansible/tasks/apply_openshift_build.yml); "repository" is
"zuno-ai-build/<name>", so `base` strips the namespace prefix down to
the bare stream name the trigger's `from.name` expects.
*/}}
{{- define "finage.imageTrigger" -}}
{{- list (dict "from" (dict "kind" "ImageStreamTag" "name" (printf "%s:%s" (base .repository) .tag) "namespace" "zuno-ai-build") "fieldPath" (printf "spec.template.spec.containers[?(@.name==\"%s\")].image" .container)) | toJson -}}
{{- end -}}
