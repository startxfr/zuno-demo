# Build from the REPOSITORY ROOT (not this directory), same pattern as
# components/agent-runtime/Dockerfile:
#
#   docker build -f components/supply-chain-signer/Dockerfile -t zuno/supply-chain-signer:local .
#
# ADR-0420/WP-068/WP-069: this image is cosign + platform/supply-chain/
# sign_in_cluster.py + sign_okf_bundle.py, nothing else - it authenticates to
# Vault's Transit-backed platform-signer identity via Kubernetes auth and
# drives cosign's hashivault:// KMS mode. Backs one-off debug pods and the
# OKF bundle signing Job; never a long-running Deployment of its own.
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

COPY platform/supply-chain/sign_in_cluster.py ./sign_in_cluster.py
COPY platform/supply-chain/sign_okf_bundle.py ./sign_okf_bundle.py

ENTRYPOINT ["python3", "/app/sign_in_cluster.py"]
CMD ["dry-run"]
