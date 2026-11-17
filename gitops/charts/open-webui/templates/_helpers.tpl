{{/*
WP-296 (ADR-0619 clause 5): the three places the alternative gateways are written in must agree (see
values.yaml): `altGateways`, `global.zuno.altGateways`, and the subchart's `openaiBaseApiUrls`, which is the
ai-gateway's URL followed by each entry's url. Renders nothing; fails the render otherwise.
*/}}
{{- define "open-webui.altGatewaysCheck" -}}
{{- $alt := .Values.altGateways | default list -}}
{{- $global := .Values.global.zuno.altGateways | default list -}}
{{- $urls := (index .Values "open-webui").openaiBaseApiUrls | default list -}}
{{- if ne (toJson $alt) (toJson $global) }}{{ fail "altGateways and global.zuno.altGateways must be the same list (the role sets both from open_webui_alt_gateways)" }}{{ end -}}
{{- range $alt -}}
{{- if not (regexMatch "^[a-z0-9]([a-z0-9-]{0,38}[a-z0-9])?$" (toString .name)) }}{{ fail (printf "altGateways: name %q must be a DNS label of at most 40 characters" (toString .name)) }}{{ end -}}
{{- if not (regexMatch "^https?://[^/ ]+" (toString .url)) }}{{ fail (printf "altGateways: %s: url must be an http(s) URL" .name) }}{{ end -}}
{{- end -}}
{{- if $alt -}}
{{- $want := list (first $urls) -}}
{{- range $alt }}{{ $want = append $want .url }}{{ end -}}
{{- if ne (toJson $urls) (toJson $want) }}{{ fail (printf "open-webui.openaiBaseApiUrls must be the ai-gateway's URL followed by the url of each altGateways entry, in order: want %s, got %s" (toJson $want) (toJson $urls)) }}{{ end -}}
{{- end -}}
{{- end -}}
