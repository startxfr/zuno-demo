# Build from the REPOSITORY ROOT (not this directory), same pattern as
# components/agent-runtime/Dockerfile:
#
#   docker build -f components/supply-chain-signer/Dockerfile -t zuno/supply-chain-signer:local .
#
# ADR-0420/WP-068/WP-069/WP-070: this image is cosign + platform/supply-chain/
# sign_in_cluster.py + sign_okf_bundle.py + the committed Vault Transit
# public key, nothing else. Signing (sign-image, sign-okf-bundles)
# authenticates to Vault's platform-signer identity via Kubernetes auth
# and drives cosign's hashivault:// KMS mode; verifying (verify-images)
# needs the committed public key baked in below, never Vault access -
# the whole point of a verifier under ADR-0420. Backs one-off debug pods,
# the OKF/image signing Jobs, and the supply-chain check gate; never a
# long-running Deployment of its own.
ARG BASE_IMAGE=image-registry.openshift-image-registry.svc:5000/zuno-ai-build/python:3.11-slim
FROM ${BASE_IMAGE} AS base

WORKDIR /app

# Same cosign-fetch shape as components/agent-runtime/Dockerfile - bump both
# together. Unlike that image's cosign (keyless verify-blob only), this one
# also signs, which is exactly why it runs as its own narrowly-scoped
# identity (zuno-signer) rather than being folded into agent-runtime.
ARG COSIGN_VERSION=v2.4.1
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -sSL -o /usr/local/bin/cosign \
       "https://github.com/sigstore/cosign/releases/download/${COSIGN_VERSION}/cosign-linux-amd64" \
    && chmod +x /usr/local/bin/cosign \
    && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# ADR-0580/WP-161: the same image is the `okf-fetch` init container of the
# components that read agent definitions at start (mcp-gateway): it pulls the
# zuno-demo-agents release pinned in platform/okf/agents.lock, verifies it
# OFFLINE (keyless signatures of the release workflow, against the committed
# Sigstore trust root) and extracts it into an emptyDir. It needs oras, the
# admission script and its trust material, laid out as in the repository so
# the script finds platform/okf/sigstore/ from its own location.
ARG ORAS_VERSION=1.2.2
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -sSL "https://github.com/oras-project/oras/releases/download/v${ORAS_VERSION}/oras_${ORAS_VERSION}_linux_amd64.tar.gz" \
       | tar -xz -C /usr/local/bin oras \
    && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir pyyaml==6.0.2
COPY platform/supply-chain/admit_okf_bundle.py platform/supply-chain/okf_narrowing.py ./platform/supply-chain/
COPY platform/okf/sigstore ./platform/okf/sigstore
# OpenShift runs the container as an arbitrary non-root UID: the copied
# files must be world-readable whatever their mode in the checkout.
RUN chmod -R a+rX /app/platform

COPY platform/supply-chain/sign_in_cluster.py ./sign_in_cluster.py
COPY platform/supply-chain/sign_okf_bundle.py ./sign_okf_bundle.py
COPY agents/zuno-platform-signer.pub ./zuno-platform-signer.pub

ENTRYPOINT ["python3", "/app/sign_in_cluster.py"]
CMD ["dry-run"]
