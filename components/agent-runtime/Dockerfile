# Build from the REPOSITORY ROOT (not this directory), same pattern as
# components/mcp-gateway/Dockerfile - this image bakes in the OKF v0.2
# Markdown bundles (ADR-0038, agents/<name>/agent.okf.md + tasks/*.md +
# prompts/*.md) that app/registry.py's AgentRegistry (ADR-0039) loads at
# startup, plus policies/knowledge/knowledge-policy.yaml (ADR-0203) that
# app/knowledge.py's KnowledgePolicyStore loads at startup - both ship as
# an ordinary redeploy of this runtime:
#
#   docker build -f components/agent-runtime/Dockerfile -t zuno/agent-runtime:local .
FROM python:3.11-slim AS base

WORKDIR /app

# ADR-0106: keyless cosign verify-blob, used by app/_sign_okf_bundle.py
# (baked in below) only when ZUNO_REQUIRE_SIGNED_BUNDLES=true (default
# false - see app/registry.py). Pinned to the same major release
# .github/workflows/build-publish.yml's sigstore/cosign-installer@v3
# currently resolves; bump both together. verify-blob needs no network
# egress beyond Rekor/Fulcio's public endpoints, already reachable from
# any pod with normal internet access.
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
# ADR-0106: the same digest/verify logic build-publish.yml's signing job
# and platform/supply-chain/verify_signatures.py use - imported by
# app/registry.py as `app._sign_okf_bundle`, never duplicated, so the
# runtime can never disagree with CI about what a bundle's digest is.
COPY platform/supply-chain/sign_okf_bundle.py ./app/_sign_okf_bundle.py

ENV AGENTS_DIR=/app/agents \
    ZUNO_REQUIRE_SIGNED_BUNDLES=false \
    ZUNO_OKF_SIGNATURES_DIR=/app/okf-signatures \
    KNOWLEDGE_POLICY_PATH=/app/policies/knowledge/knowledge-policy.yaml \
    PYTHONUNBUFFERED=1

# No provider-routing config or provider API keys here anymore (ADR-0009
# split) - this service only needs AI_GATEWAY_URL, set at deploy time; see
# components/ai-gateway for where the routing config now lives.

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
