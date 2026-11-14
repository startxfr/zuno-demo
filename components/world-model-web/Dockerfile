# Build from the REPOSITORY ROOT (not this directory):
#
#   docker build -f components/world-model-web/Dockerfile -t zuno/world-model-web:local .
#
# ADR-0604 (WP-234): the browser API (FastAPI) and the PatternFly UI it serves. No GPU and no model
# weights here: it talks to world-model-runtime. Stage 1 builds the UI from its lockfile; stage 2 is
# the Python service from the hash-checked lock, with the built UI copied in.
ARG NODE_IMAGE=image-registry.openshift-image-registry.svc:5000/zuno-ai-build/node:20-alpine
ARG BASE_IMAGE=image-registry.openshift-image-registry.svc:5000/zuno-ai-build/python:3.11-slim

FROM ${NODE_IMAGE} AS ui
WORKDIR /ui
COPY components/world-model-web/ui/package.json components/world-model-web/ui/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY components/world-model-web/ui/ ./
RUN npm run build

FROM ${BASE_IMAGE}

COPY platform/python/bootstrap/tools/requirements.txt /tmp/bootstrap-tools.txt
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --require-hashes --upgrade -r /tmp/bootstrap-tools.txt

WORKDIR /app

COPY components/world-model-web/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

COPY components/world-model-web/app ./app
COPY --from=ui /ui/dist ./ui/dist
# The pod runs as an arbitrary non-root UID (group 0): files must be world-readable whatever the
# build context's umask was (a workstation build copies 0600 files).
RUN chmod -R a+rX /app

ENV PYTHONUNBUFFERED=1 \
    UI_DIR=/app/ui/dist \
    PRESETS_FILE=/app/config/presets.yaml

USER 1001
EXPOSE 8080

CMD ["uvicorn", "app.main:get_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips=*"]
