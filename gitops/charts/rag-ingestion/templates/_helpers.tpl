{{- define "rag-ingestion.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "rag-ingestion.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name (include "rag-ingestion.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "rag-ingestion.labels" -}}
app.kubernetes.io/name: {{ include "rag-ingestion.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
app.kubernetes.io/part-of: rag-ingestion
{{- end }}

{{- define "rag-ingestion.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "rag-ingestion.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- .Values.serviceAccount.name -}}
{{- end -}}
{{- end }}


{{- define "rag-ingestion.image" -}}
{{- printf "%s:%s" .Values.images.ingestion.repository .Values.images.ingestion.tag -}}
{{- end }}

{{- define "rag-ingestion.s3Endpoint" -}}
{{- if .Values.s3.endpoint -}}
{{- .Values.s3.endpoint -}}
{{- else if eq .Values.s3.type "aws" -}}
{{- printf "https://s3.%s.amazonaws.com" .Values.s3.region -}}
{{- else -}}
{{- fail "s3.endpoint is required when s3.type is not aws" -}}
{{- end -}}
{{- end }}
