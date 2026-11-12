# Build from the REPOSITORY ROOT (not this directory), same pattern as
# components/agent-runtime/Dockerfile:
#
#   docker build -f components/supply-chain-signer/Dockerfile -t zuno/supply-chain-signer:local .
#
# ADR-0420/WP-068/WP-070/ADR-0535: this image is cosign + platform/
# supply-chain/sign_in_cluster.py, plus the okf-fetch admission files
# below. Image signing (sign-image) and verification (verify-images) run
# keyless through RHTAS; sign-blob/verify-blob keep the Vault Transit
# platform-signer identity (Kubernetes auth, cosign's hashivault:// KMS
# mode). Backs one-off debug pods, the image signing Jobs, the
# supply-chain check gate and the okf-fetch init container; never a
# long-running Deployment of its own. WP-165 removed the OKF Transit
# signing (sign-okf-bundles) and the public key it shipped: OKF releases
# are signed keyless by zuno-demo-agents (ADR-0578).
ARG BASE_IMAGE=image-registry.openshift-image-registry.svc:5000/zuno-ai-build/python:3.11-slim
FROM ${BASE_IMAGE} AS base

WORKDIR /app

# Same cosign-fetch shape as components/agent-runtime/Dockerfile - bump both
# together. Unlike that image's cosign (keyless verify-blob only), this one
# also signs, which is exactly why it runs as its own narrowly-scoped
# identity (zuno-signer) rather than being folded into agent-runtime.
#
# ADR-0603 M18 (WP-226): the download is checked against the sha256 of the
# release's cosign_checksums.txt (same pin and digest as
# components/aap-execution-environment/Dockerfile); a mismatch fails the build.
# Re-read the digest from the release's checksums file on any version bump,
# never carry it forward.
ARG COSIGN_VERSION=v2.4.1
ARG COSIGN_SHA256=8b24b946dd5809c6bd93de08033bcf6bc0ed7d336b7785787c080f574b89249b
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -sSL -o /usr/local/bin/cosign \
       "https://github.com/sigstore/cosign/releases/download/${COSIGN_VERSION}/cosign-linux-amd64" \
    && echo "${COSIGN_SHA256}  /usr/local/bin/cosign" | sha256sum -c - \
    && chmod +x /usr/local/bin/cosign \
    && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# ADR-0580/WP-161: the same image is the `okf-fetch` init container of the
# components that read agent definitions at start (mcp-gateway): it pulls the
# zuno-demo-agents release pinned in platform/okf/agents.lock, verifies it
# OFFLINE (keyless signatures of the release workflow, against the committed
# Sigstore trust root) and extracts it into an emptyDir. It needs oras, the
# admission script and its trust material, laid out as in the repository so
# the script finds platform/okf/sigstore/ from its own location.
# Checksum from the release's oras_1.2.2_checksums.txt (ADR-0603 M18).
ARG ORAS_VERSION=1.2.2
ARG ORAS_SHA256=bff970346470e5ef888e9f2c0bf7f8ee47283f5a45207d6e7a037da1fb0eae0d
COPY platform/python/bootstrap/pyyaml/requirements.txt /tmp/bootstrap-pyyaml.txt
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -sSL -o /tmp/oras.tar.gz "https://github.com/oras-project/oras/releases/download/v${ORAS_VERSION}/oras_${ORAS_VERSION}_linux_amd64.tar.gz" \
    && echo "${ORAS_SHA256}  /tmp/oras.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/oras.tar.gz -C /usr/local/bin oras && rm -f /tmp/oras.tar.gz \
    && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --require-hashes -r /tmp/bootstrap-pyyaml.txt
COPY platform/supply-chain/admit_okf_bundle.py platform/supply-chain/okf_narrowing.py ./platform/supply-chain/
COPY platform/okf/sigstore ./platform/okf/sigstore
# OpenShift runs the container as an arbitrary non-root UID: the copied
# files must be world-readable whatever their mode in the checkout.
RUN chmod -R a+rX /app/platform

COPY platform/supply-chain/sign_in_cluster.py ./sign_in_cluster.py

ENTRYPOINT ["python3", "/app/sign_in_cluster.py"]
CMD ["dry-run"]
