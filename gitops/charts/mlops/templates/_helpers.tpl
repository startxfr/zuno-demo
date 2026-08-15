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

{{- define "mlops.image" -}}
{{- printf "%s:%s" .Values.images.mlops.repository .Values.images.mlops.tag -}}
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
