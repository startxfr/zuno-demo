{{/* Labels of the Zuno objects of this chart (the startx subcharts carry their own). */}}
{{- define "zuno-chaos.labels" -}}
app.kubernetes.io/part-of: zuno-chaos
zuno.io/managed-by: argocd
{{- end -}}

{{/* repository@digest: every Zuno task image is pinned by digest, as the startx chaos-pipeline chart pins krkn. */}}
{{- define "zuno-chaos.image" -}}
{{- printf "%s@%s" .repository (required "zuno.images.*.digest is required: the Zuno tasks run pinned images only" .digest) -}}
{{- end -}}

{{/* Restricted security context of the Zuno task steps: they only call the API server, curl and sleep. */}}
{{- define "zuno-chaos.securityContext" -}}
allowPrivilegeEscalation: false
runAsNonRoot: true
capabilities:
  drop: ["ALL"]
seccompProfile:
  type: RuntimeDefault
{{- end -}}
