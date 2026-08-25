# Build from the REPOSITORY ROOT (not this directory), same pattern as
# components/mcp-gateway/Dockerfile - this image bakes in the OKF v0.2
# Markdown bundles (ADR-0038, agents/<name>/agent.okf.md + tasks/*.md +
# prompts/*.md) that app/registry.py's AgentRegistry (ADR-0039) loads at
# startup, plus policies/knowledge/knowledge-policy.yaml (ADR-0203) that
# app/knowledge.py's KnowledgePolicyStore loads at startup - both ship as
# an ordinary redeploy of this runtime:
#
#   docker build -f components/agent-runtime/Dockerfile -t zuno/agent-runtime:local .
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

# ADR-0106/ADR-0420: cosign verify-blob against the committed
# agents/zuno-platform-signer.pub, used by
# app/_sign_okf_bundle.py (baked in below) only when
# ZUNO_REQUIRE_SIGNED_BUNDLES=true (default false - see app/registry.py).
# Pinned to the same version components/supply-chain-signer/Dockerfile
# uses; bump both together. Needs no network egress at all - verification
# is a pure offline check against the local public key file.
ARG COSIGN_VERSION=v2.4.1
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -sSL -o /usr/local/bin/cosign \
       "https://github.com/sigstore/cosign/releases/download/${COSIGN_VERSION}/cosign-linux-amd64" \
    && chmod +x /usr/local/bin/cosign \
    && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY components/agent-runtime/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY components/agent-runtime/app ./app
COPY agents ./agents
# ADR-0203: knowledge-domain policy, same graceful-degradation posture as
# mcp-gateway's policy files if this is ever absent at build time - see
# app/knowledge.py's KnowledgePolicyStore.
COPY policies/knowledge ./policies/knowledge
# ADR-0511/ADR-0512: project_binding.validity_window - app/project_binding.py
# reads this at import time to decide how long a verified Salesforce
# binding stays cached before a resumed conversation must re-verify.
COPY policies/quotas ./policies/quotas
# ADR-0106: the same digest/verify logic build-publish.yml's signing job
# and platform/supply-chain/verify_signatures.py use - imported by
# app/registry.py as `app._sign_okf_bundle`, never duplicated, so the
# runtime can never disagree with CI about what a bundle's digest is.
COPY platform/supply-chain/sign_okf_bundle.py ./app/_sign_okf_bundle.py

ENV AGENTS_DIR=/app/agents \
    ZUNO_REQUIRE_SIGNED_BUNDLES=false \
    ZUNO_OKF_SIGNATURES_DIR=/app/okf-signatures \
    KNOWLEDGE_POLICY_PATH=/app/policies/knowledge/knowledge-policy.yaml \
    QUOTA_POLICY_PATH=/app/policies/quotas/quota-policy.yaml \
    PYTHONUNBUFFERED=1

# No provider-routing config or provider API keys here anymore (ADR-0009
# split) - this service only needs AI_GATEWAY_URL, set at deploy time; see
# components/ai-gateway for where the routing config now lives.

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
