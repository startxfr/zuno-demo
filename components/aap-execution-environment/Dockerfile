# Hand-authored to match what `ansible-builder create -f
# execution-environment.yml -c .` would generate for that file - this
# sandbox's `ansible-builder` binary is broken (wrong python3.8 shebang,
# no ansible_builder module installed), so it could not be run to
# generate this file directly. Regenerate and diff carefully once a
# working ansible-builder toolchain is available; keep the
# additional_build_steps.append_final content (oc/kustomize/cosign) in
# sync with execution-environment.yml either way - that file is the
# source of truth.
#
# Build from the REPOSITORY ROOT, same convention as every other
# components/<name>/Dockerfile:
#   docker build -f components/aap-execution-environment/Dockerfile \
#     -t aap-execution-environment:local .

FROM registry.redhat.io/ansible-automation-platform-27/ee-supported-rhel9:latest

# oc: available as an RPM under this cluster's RHN subscription
# auto-attach (already proven for the `aap` role's own install).
RUN dnf install -y openshift-clients && dnf clean all

# kustomize/cosign: no RHEL9 package - pinned-version release binaries,
# checksum-verified against each project's own published checksums
# manifest (kustomize's checksums.txt, cosign's cosign_checksums.txt).
# Digests below fetched live from those manifests for the exact pinned
# versions - re-verify both on any version bump, never carry a digest
# forward or fabricate one.
#
# COSIGN_VERSION matches components/supply-chain-signer/Dockerfile's own
# pin (v2.4.1) - keep both in sync on a bump, same binary shape.
ARG KUSTOMIZE_VERSION=5.4.3
ARG KUSTOMIZE_SHA256=3669470b454d865c8184d6bce78df05e977c9aea31c30df3c669317d43bcc7a7
ARG COSIGN_VERSION=v2.4.1
ARG COSIGN_SHA256=8b24b946dd5809c6bd93de08033bcf6bc0ed7d336b7785787c080f574b89249b

RUN curl -sSL -o /tmp/kustomize.tar.gz \
      "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2Fv${KUSTOMIZE_VERSION}/kustomize_v${KUSTOMIZE_VERSION}_linux_amd64.tar.gz" \
    && echo "${KUSTOMIZE_SHA256}  /tmp/kustomize.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/kustomize.tar.gz -C /usr/bin kustomize \
    && chmod +x /usr/bin/kustomize \
    && rm -f /tmp/kustomize.tar.gz

RUN curl -sSL -o /usr/bin/cosign \
      "https://github.com/sigstore/cosign/releases/download/${COSIGN_VERSION}/cosign-linux-amd64" \
    && echo "${COSIGN_SHA256}  /usr/bin/cosign" | sha256sum -c - \
    && chmod +x /usr/bin/cosign
