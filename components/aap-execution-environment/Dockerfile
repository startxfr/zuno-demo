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

# oc/kustomize/cosign: none of the three are an RHEL9 dnf package
# reachable here - `dnf` itself doesn't exist in this stock EE image
# (confirmed live 2026-08-30: "dnf: command not found" - the original
# RHN-auto-attach assumption for oc was wrong, that applies to full RHEL
# hosts like the `aap` role's own VMs, not this minimal supported-EE
# container). All three are pinned-version release binaries instead,
# checksum-verified against each project's own published checksums
# manifest (oc's sha256sum.txt on mirror.openshift.com, kustomize's
# checksums.txt, cosign's cosign_checksums.txt). Digests below fetched
# live from those manifests for the exact pinned versions - re-verify
# all three on any version bump, never carry a digest forward or
# fabricate one.
#
# OC_VERSION pinned to this cluster's own server version (`oc version -o
# json`, confirmed live 4.22.8) for the closest client/server
# compatibility. COSIGN_VERSION matches components/supply-chain-signer/
# Dockerfile's own pin (v2.4.1) - keep both in sync on a bump, same
# binary shape.
ARG OC_VERSION=4.22.8
ARG OC_SHA256=22cb5df5206569ca2c8ca3b56f55f5af9dbd68fc35ea237a4069e06ffd6e9218
ARG KUSTOMIZE_VERSION=5.4.3
ARG KUSTOMIZE_SHA256=3669470b454d865c8184d6bce78df05e977c9aea31c30df3c669317d43bcc7a7
ARG COSIGN_VERSION=v2.4.1
ARG COSIGN_SHA256=8b24b946dd5809c6bd93de08033bcf6bc0ed7d336b7785787c080f574b89249b

RUN curl -sSL -o /tmp/oc.tar.gz \
      "https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/${OC_VERSION}/openshift-client-linux-${OC_VERSION}.tar.gz" \
    && echo "${OC_SHA256}  /tmp/oc.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/oc.tar.gz -C /usr/bin oc \
    && chmod +x /usr/bin/oc \
    && rm -f /tmp/oc.tar.gz

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
