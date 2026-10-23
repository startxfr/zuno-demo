# Build from the REPOSITORY ROOT (not this directory):
#
#   docker build -f components/mcp-gateway/Dockerfile -t zuno/mcp-gateway:local .
#
# A repo-root build context is required because this image bakes in the
# platform's own data-classification policy
# (policies/data-classification/classification.yaml) and the backend
# bindings (platform/bindings/).
#
# ADR-0580/WP-165: the agent bundles (ADR-0036/0038, read by
# app/agent_declarations.py) and the corp tool policy
# (policies/tools/tool-policy.yaml) are NOT baked any more: they left this
# repository for the zuno-demo-agents release, which the chart's okf-fetch
# init container verifies and extracts into /okf at pod start
# (gitops/charts/mcp-gateway, okf.fetch; enabled by ansible/roles/mcp). The
# defaults below point there. Without that volume the gateway starts and
# serves /healthz, but every agent-scoped call fails closed (see
# app/policy.py and app/agent_declarations.py).
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

COPY components/mcp-gateway/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY components/mcp-gateway/app ./app
COPY policies/data-classification ./policies/data-classification
# ADR-0116: the backend-binding registry rides the same bake-in/reload
# lifecycle as the policy files above.
COPY platform/bindings ./platform/bindings

ENV TOOL_POLICY_PATH=/okf/policies/tools/tool-policy.yaml \
    DATA_CLASSIFICATION_PATH=/app/policies/data-classification/classification.yaml \
    AGENTS_DIR=/okf/agents \
    TOOL_BINDINGS_PATH=/app/platform/bindings/tools/tool-bindings.yaml \
    PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
