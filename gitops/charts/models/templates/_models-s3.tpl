{{- /*
ADR-0546/WP-131: model weights move from the per-cluster corpus bucket to the
shared cross-cluster source bucket ONE MODEL AT A TIME.

Every s3:// reference in this chart used to derive from the single
modelsS3.bucket, so changing it would have moved all five models at once - and
a model whose weights are not where its LLMInferenceService says they are does
not fail at apply time, it fails when the pod pulls, minutes later, as a
CrashLoop with an S3 404 buried in an init container. That is the opposite of
what "one model at a time" is for.

So each model carries an s3Source of "models" (the per-cluster bucket, the
default and the pre-ADR-0546 behaviour) or "sources" (the shared bucket). With
every model on "models" the render is byte-identical to before this template
existed, which is what makes landing it inert; flipping one model is then a
single value, and reverting it is the same value back.
*/ -}}

{{- /* Returns the S3 block a given source name selects. */ -}}
{{- define "models.s3Block" -}}
{{- $root := index . 0 -}}
{{- $source := index . 1 | default "models" -}}
{{- if eq $source "sources" -}}
{{- if not $root.Values.sourcesS3 -}}
{{- fail "s3Source: sources selected but .Values.sourcesS3 is not defined" -}}
{{- end -}}
{{- toYaml $root.Values.sourcesS3 -}}
{{- else if eq $source "models" -}}
{{- toYaml $root.Values.modelsS3 -}}
{{- else -}}
{{- fail (printf "unknown s3Source %q - expected \"models\" or \"sources\"" $source) -}}
{{- end -}}
{{- end -}}

{{- /*
Builds one model's weights URI. Call as:
  include "models.modelUri" (list $ $.Values.weshModel.s3Source $.Values.weshModel.servedModelName)

The endpoint/region guard is here rather than in a one-off check because the
KServe serving-credential Secrets carry serving.kserve.io/s3-endpoint and
s3-region as ANNOTATIONS on a single shared credential. Both buckets are
eu-west-2 today, so one credential serves both. If a future source bucket lands
in another region, a model pointed at it would authenticate against the wrong
endpoint and fail at pull time with a signature error rather than anything that
names the real cause - so refuse to render instead.
*/ -}}
{{- define "models.modelUri" -}}
{{- $root := index . 0 -}}
{{- $source := index . 1 | default "models" -}}
{{- $name := index . 2 -}}
{{- $block := include "models.s3Block" (list $root $source) | fromYaml -}}
{{- if ne $source "models" -}}
{{- if or (ne $block.endpoint $root.Values.modelsS3.endpoint) (ne $block.region $root.Values.modelsS3.region) -}}
{{- fail (printf "model %s selects s3Source %q whose endpoint/region (%s/%s) differ from modelsS3 (%s/%s); the shared KServe serving credential carries only one endpoint/region annotation pair, so this would fail at pull time with a signature error. Give that source its own credential Secret before pointing a model at it." $name $source $block.endpoint $block.region $root.Values.modelsS3.endpoint $root.Values.modelsS3.region) -}}
{{- end -}}
{{- end -}}
s3://{{ $block.bucket }}/{{ $block.prefix }}/{{ $name }}/
{{- end -}}
