# Build from the REPOSITORY ROOT (not this directory), same pattern as
# components/mcp-gateway/Dockerfile and components/agent-runtime/Dockerfile -
# this image bakes in platform/bindings/knowledge/bindings.yaml (ADR-0204,
# WP-21), the per-domain knowledge-domain -> backend binding registry
# app/bindings.py's KnowledgeBindingRegistry loads at startup, so a binding
# change (e.g. moving a domain to a different database) ships as an
# ordinary redeploy of this service:
#
#   docker build -f components/rag-service/Dockerfile -t zuno/rag-service:local .
FROM python:3.11-slim AS base

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
