{{- define "mlops.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "mlops.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name (include "mlops.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "mlops.labels" -}}
app.kubernetes.io/name: {{ include "mlops.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
app.kubernetes.io/part-of: mlops
{{- end }}

{{- define "mlops.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "mlops.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- .Values.serviceAccount.name -}}
{{- end -}}
{{- end }}

{{/*
ADR-0603 M16 (WP-226): repository@digest once a release has rendered
images.mlops.digest (platform/supply-chain/render_release_digests.py),
repository:tag otherwise (ADR-0059). mlops.imagePullPolicy follows: a fixed
digest needs no re-pull.
*/}}
{{- define "mlops.image" -}}
{{- with .Values.images.mlops -}}
{{- if .digest -}}
{{- if not (regexMatch "^sha256:[0-9a-f]{64}$" .digest) -}}
{{- fail (printf "images.mlops.digest %q is not sha256:<64 hex>" .digest) -}}
{{- end -}}
{{- printf "%s@%s" .repository .digest -}}
{{- else -}}
{{- printf "%s:%s" .repository .tag -}}
{{- end -}}
{{- end -}}
{{- end }}

{{- define "mlops.imagePullPolicy" -}}
{{- if .Values.images.mlops.digest -}}IfNotPresent{{- else -}}{{ .Values.images.mlops.pullPolicy }}{{- end -}}
{{- end }}

{{- define "mlops.s3Endpoint" -}}
{{- if .Values.s3.endpoint -}}
{{- .Values.s3.endpoint -}}
{{- else if eq .Values.s3.type "aws" -}}
{{- printf "https://s3.%s.amazonaws.com" .Values.s3.region -}}
{{- else -}}
{{- fail "s3.endpoint is required when s3.type is not aws" -}}
{{- end -}}
{{- end }}
