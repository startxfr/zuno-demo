# Build from the REPOSITORY ROOT (not this directory), same pattern as
# components/mcp-gateway/Dockerfile and components/agent-runtime/Dockerfile -
# this image bakes in platform/bindings/knowledge/bindings.yaml (ADR-0204,
# WP-21), the per-domain knowledge-domain -> backend binding registry
# app/bindings.py's KnowledgeBindingRegistry loads at startup, so a binding
# change (e.g. moving a domain to a different database) ships as an
# ordinary redeploy of this service:
#
#   docker build -f components/rag-service/Dockerfile -t zuno/rag-service:local .
#
# FROM image below defaults to the zuno-ai-build ImageStream mirror
# (ansible/roles/image_mirrors), not docker.io directly - a local
# `docker build` therefore needs network access to the cluster's internal
# registry route. .github/workflows/build-publish.yml (ADR-0115) overrides
# this ARG to the real docker.io image, since its GitHub-hosted runners
# can't reach the cluster-internal mirror at all.
ARG BASE_IMAGE=image-registry.openshift-image-registry.svc:5000/zuno-ai-build/python:3.11-slim
FROM ${BASE_IMAGE} AS base

# ADR-0115 (WP-04): patch known HIGH CVEs baked into the upstream base image
# at build time - apt upgrade picks up Debian's patched util-linux/bsdutils
# (CVE-2026-53615), pip upgrade picks up patched pip/setuptools/wheel.
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /app

COPY components/rag-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY components/rag-service/app ./app
# ADR-0204: platform-controlled, never caller-supplied - same
# graceful-degradation posture as mcp-gateway's tool bindings if this is
# ever absent at build time (see app/bindings.py's KnowledgeBindingRegistry).
COPY platform/bindings/knowledge ./platform/bindings/knowledge

ENV KNOWLEDGE_BINDINGS_PATH=/app/platform/bindings/knowledge/bindings.yaml \
    PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
