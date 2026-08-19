# Build from the REPOSITORY ROOT (not this directory):
#
#   docker build -f components/mcp-gateway/Dockerfile -t zuno/mcp-gateway:local .
#
# A repo-root build context is required because this image bakes in the
# policy files owned by another track (Track B):
#   - policies/tools/tool-policy.yaml
#   - policies/data-classification/classification.yaml
# so that a policy change ships as an ordinary redeploy of this gateway.
# See app/policy.py for the graceful-degradation behavior if those files
# are still absent at build time (the service starts and serves /healthz,
# but every /v1/tools/*/invoke call fails closed with a clear 503/403
# until the files are present and the store is reloaded).
#
# ADR-0036/0038: also bakes in agents/ (the OKF v0.2 Markdown bundles) so
# app/agent_declarations.py can enforce the agent_declaration/task_rights
# factors - same reasoning, same reload path (/admin/reload-policy).
#
# FROM image below defaults to the zuno-ai-build ImageStream mirror
# (ansible/roles/image_mirrors), not docker.io directly - a local
# `docker build` therefore needs network access to the cluster's internal
# registry route. .github/workflows/build-publish.yml (ADR-0115) overrides
# this ARG to the real docker.io image, since its GitHub-hosted runners
# can't reach the cluster-internal mirror at all.
ARG BASE_IMAGE=image-registry.openshift-image-registry.svc:5000/zuno-ai-build/python:3.11-slim
FROM ${BASE_IMAGE} AS base

WORKDIR /app

COPY components/mcp-gateway/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY components/mcp-gateway/app ./app
COPY policies ./policies
COPY agents ./agents
# ADR-0116: the backend-binding registry rides the same bake-in/reload
# lifecycle as the policy files above.
COPY platform/bindings ./platform/bindings

ENV TOOL_POLICY_PATH=/app/policies/tools/tool-policy.yaml \
    DATA_CLASSIFICATION_PATH=/app/policies/data-classification/classification.yaml \
    AGENTS_DIR=/app/agents \
    TOOL_BINDINGS_PATH=/app/platform/bindings/tools/tool-bindings.yaml \
    PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
