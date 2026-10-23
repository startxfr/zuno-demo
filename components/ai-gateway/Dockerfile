# Build from the REPOSITORY ROOT (not this directory):
#
#   docker build -f components/ai-gateway/Dockerfile -t zuno/ai-gateway:local .
#
# A repo-root build context is required as of ADR-0303/WP-39: this image
# bakes in the model-routing policy (per agent/task preferences, adapters
# and the ADR-0550 local_only_for constraints) and the platform's own
# optimization policy - a policy change ships as an ordinary rebuild and
# redeploy of this gateway.
#
# ADR-0580/WP-165: the model-routing policy is a corp policy of the
# zuno-demo-agents release, no longer a file of this repository. The
# okf-release stage below takes it from the release pinned in
# platform/okf/agents.lock, verified offline at build time, so a promotion
# PR moving the lock is followed by a rebuild of this image. Read at build
# time rather than fetched at start (ADR-0580 clause 4) on purpose: this
# gateway is in front of every model call, and a pod start must not depend
# on the agents registry; ADR-0581 plans a generated, mounted file instead
# once WP-157 reshapes routing.
#
# FROM image below defaults to the zuno-ai-build ImageStream mirror
# (ansible/roles/image_mirrors), not docker.io directly - a local
# `docker build` therefore needs network access to the cluster's internal
# registry route. .github/workflows/build-publish.yml (ADR-0115) overrides
# this ARG to the real docker.io image, since its GitHub-hosted runners
# can't reach the cluster-internal mirror at all.
ARG BASE_IMAGE=image-registry.openshift-image-registry.svc:5000/zuno-ai-build/python:3.11-slim
# ADR-0580/WP-165: content of the admitted zuno-demo-agents release this
# image bakes is read from the release pinned in platform/okf/agents.lock,
# never from a copy in this repository. This stage installs cosign and oras
# (pinned, checksum-verified), then platform/okf/release_cache.py verifies
# the release offline against the committed Sigstore trust root - exactly
# what `make d3 admit agents` checks - and extracts it to /okf. A release
# that does not verify fails the build. Needs egress to github.com (the two
# binaries) and quay.io (the release), like the pip installs already do.
FROM ${BASE_IMAGE} AS okf-release
USER 0
WORKDIR /src
COPY platform/okf/install_release_tools.py platform/okf/release_cache.py platform/okf/agents.lock ./platform/okf/
COPY platform/okf/sigstore ./platform/okf/sigstore
COPY platform/supply-chain/admit_okf_bundle.py platform/supply-chain/okf_narrowing.py ./platform/supply-chain/
RUN python3 platform/okf/install_release_tools.py /src/bin \
    && python3 -m pip install --no-cache-dir pyyaml==6.0.2 \
    && PATH="/src/bin:${PATH}" python3 platform/okf/release_cache.py > /src/release-path \
    && cp -r "$(cat /src/release-path)" /okf \
    && chmod -R a+rX /okf

FROM ${BASE_IMAGE} AS base

# ADR-0115 (WP-04): patch known HIGH CVEs baked into the upstream base image
# at build time - apt upgrade picks up Debian's patched util-linux/bsdutils
# (CVE-2026-53615), pip upgrade picks up patched pip/setuptools/wheel.
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /app

COPY components/ai-gateway/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY components/ai-gateway/app ./app
# ADR-0303/WP-39: per-agent/task adapter declarations - see
# app/model_routing_policy.py for the graceful-degradation behavior if
# this directory is ever absent (every request just uses the base model,
# never a startup failure). From the verified release (WP-165).
COPY --from=okf-release /okf/policies/model-routing ./policies/model-routing
# ADR-0309/WP-42: the autonomous-optimization governance policy - same
# graceful degradation (absent file = autonomy fully disabled, the
# fail-safe direction).
COPY policies/optimization ./policies/optimization

ENV PYTHONUNBUFFERED=1 \
    PROVIDER_ROUTING_PATH=/app/config/provider-routing.yaml \
    MODEL_ROUTING_POLICY_PATH=/app/policies/model-routing/model-routing-policy.yaml \
    OPTIMIZATION_POLICY_PATH=/app/policies/optimization/optimization-policy.yaml

# provider-routing.yaml is NOT baked into the image: it is mounted at
# /app/config/provider-routing.yaml from the `zuno-provider-routing`
# ConfigMap (generated from platform/ai-gateway/provider-routing.yaml by
# ansible/roles/llm's GitOps app) so a routing-policy change doesn't
# require rebuilding/redeploying this image - see gitops/charts/ai-gateway.
# model-routing-policy.yaml deliberately does NOT follow that same
# mounted-ConfigMap pattern: it is baked in from the verified agents
# release (okf-release stage above), not platform/ai-gateway/ (mounted).

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
