#!/usr/bin/env bash
# Local end-to-end run of the world-model experience without a GPU (ADR-0604 WP-234).
#   PY=/path/to/venv/bin/python NODE_DIR=/path/to/node20 UI_DIST=/path/to/ui/dist ./run.sh
# PY needs the requirements of both components plus pytest-free runtime deps (numpy, pillow, av);
# NODE_DIR holds bin/node and node_modules/playwright-core; Chrome is /usr/bin/google-chrome unless CHROME is set.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../../../.." && pwd)"
: "${PY:?PY (python with the component dependencies) is required}"
: "${NODE_DIR:?NODE_DIR (node >= 18 with playwright-core installed) is required}"
: "${UI_DIST:?UI_DIST (the built ui/dist) is required}"
rt_port="${RT_PORT:-18082}"; web_port="${WEB_PORT:-18081}"
pids=()
cleanup() { for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT

# `exec` so that $! is the server itself: the trap then really stops it.
(cd "$repo/components/world-model-runtime" && exec env WORLD_MODEL_ENGINE=mock WORLD_MODEL_IMAGE=mock WORLD_MODEL_ENCODER=x264 \
  "$PY" -m uvicorn app.main:get_app --factory --port "$rt_port" --log-level warning) & pids+=($!)
(cd "$repo/components/world-model-web" && exec env WORLD_MODEL_AUTH=dev WORLD_MODEL_RUNTIME_URL="http://127.0.0.1:$rt_port" \
  UI_DIR="$UI_DIST" PRESETS_FILE="$here/presets.e2e.yaml" \
  "$PY" -m uvicorn app.main:get_app --factory --port "$web_port" --log-level warning) & pids+=($!)

for _ in $(seq 1 60); do
  curl -fs "http://127.0.0.1:$rt_port/readyz" >/dev/null && curl -fs "http://127.0.0.1:$web_port/healthz" >/dev/null && break
  sleep 1
done
curl -fs "http://127.0.0.1:$rt_port/readyz" >/dev/null || { echo "runtime not ready" >&2; exit 2; }
# ES modules resolve imports from the script's own directory: run a copy next to playwright-core.
cp "$here/e2e.mjs" "$NODE_DIR/e2e.run.mjs"
cd "$NODE_DIR" && BASE_URL="http://127.0.0.1:$web_port" "$NODE_DIR/bin/node" "$NODE_DIR/e2e.run.mjs"
