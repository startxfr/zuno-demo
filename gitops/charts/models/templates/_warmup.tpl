{{/*
models.vllmWarmupPostStart - a postStart hook that warms a vLLM model before
the pod takes traffic.

The qwen models run --enforce-eager (MIG/NVML CUDA-graph crash, ADR-0518),
so vLLM precompiles nothing at start: the first request compiles the Triton
kernels it needs. On 2026-10-31 qwen35-9b's first request after a restart
compiled 4 kernels ("JIT compilation during inference ... latency spike"),
ran past the 60 s MaaS timeout and fell back to the direct endpoint.

Kubernetes starts the probes only once postStart returns, so the pod becomes
Ready (and gets traffic) after this warm-up. The script waits for vLLM's
/health, then sends short chat completions: one, then 2 and 4 concurrent
(decode batch shapes), then one ~2k-token prompt (prefill). TLS is verified
against the pod's own serving CA (the cert covers localhost). It has its own
deadline and ALWAYS exits 0: a failed warm-up leaves the model as before
(cold), never in a restart loop. Its lines ("[warmup] ...") go to the
container log through /proc/1/fd/1.

Parameters (dict): model (served model name), waitSeconds (for /health),
maxSeconds (whole warm-up, after /health).
*/}}
{{- define "models.vllmWarmupPostStart" -}}
lifecycle:
  postStart:
    exec:
      command:
        - /bin/sh
        - -c
        - |
          [ -w /proc/1/fd/1 ] && exec >/proc/1/fd/1 2>&1
          M={{ .model | quote }}
          U=https://localhost:8000
          CA=/var/run/kserve/tls/ca.crt
          log() { echo "[warmup] $(date -u +%H:%M:%SZ) $*"; }
          now() { date +%s; }
          ready_by=$(( $(now) + {{ int .waitSeconds }} ))
          log "waiting for vLLM /health (model $M)"
          until curl -sf --cacert "$CA" --max-time 5 -o /dev/null "$U/health"; do
            if [ "$(now)" -ge "$ready_by" ]; then log "vLLM not healthy after {{ int .waitSeconds }}s, skipping"; exit 0; fi
            sleep 5
          done
          end=$(( $(now) + {{ int .maxSeconds }} ))
          left() { l=$(( end - $(now) )); [ "$l" -gt 120 ] && l=120; [ "$l" -lt 1 ] && l=1; echo "$l"; }
          chat() {
            curl -sS --cacert "$CA" --max-time "$(left)" -o /dev/null -w '%{http_code}' \
              -H 'Content-Type: application/json' \
              -d "{\"model\":\"$M\",\"max_tokens\":16,\"messages\":[{\"role\":\"user\",\"content\":\"$1\"}]}" \
              "$U/v1/chat/completions"
          }
          step() {
            n=$1; text=$2; t0=$(now); codes=""
            i=0; while [ "$i" -lt "$n" ]; do chat "$text" > "/tmp/warmup.$i" & i=$((i + 1)); done
            wait
            i=0; while [ "$i" -lt "$n" ]; do codes="$codes $(cat "/tmp/warmup.$i" 2>/dev/null)"; rm -f "/tmp/warmup.$i"; i=$((i + 1)); done
            log "$n concurrent: HTTP$codes in $(( $(now) - t0 ))s"
          }
          t_start=$(now)
          step 1 "Say hello in five words."
          step 2 "Name one Kubernetes object."
          step 4 "Give one word for a container."
          long=""
          i=0; while [ "$i" -lt 200 ]; do long="$long The cluster runs several workloads on its GPU nodes."; i=$((i + 1)); done
          step 1 "Summarize in one word:$long"
          log "done in $(( $(now) - t_start ))s"
          exit 0
{{- end }}
