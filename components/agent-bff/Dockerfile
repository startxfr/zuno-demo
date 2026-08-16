# Build context is this directory (unlike agent-frontend/agent-runtime/
# mcp-gateway, the BFF needs no repository-root context - it has no
# agent.okf.md OKF bundles to bake in).
#
#   docker build -t zuno/agent-bff:dev components/agent-bff
#
# FROM images below pull through the zuno-ai-build ImageStream mirrors
# (ansible/roles/image_mirrors), not the public registries directly - a
# local `docker build` therefore needs network access to the cluster's
# internal registry route, not just docker.io/registry.access.redhat.com.

FROM image-registry.openshift-image-registry.svc:5000/zuno-ai-build/golang:1.22 AS build
WORKDIR /src
COPY go.mod ./
COPY . ./
RUN CGO_ENABLED=0 GOOS=linux go build -o /out/agent-bff .

# Pinned to ubi9/ubi-minimal 9.8 by digest rather than :latest (ADR-0051
# gap 5) - the digest pin now lives on the zuno-ai-build/ubi9-ubi-minimal:9
# ImageStream tag (importPolicy.scheduled: false, see
# ansible/roles/image_mirrors/tasks/install.yml); re-pin deliberately there
# (skopeo inspect --format '{{.Digest}}'
# docker://registry.access.redhat.com/ubi9/ubi-minimal:latest) when a
# base-image update is wanted, rather than letting it float.
FROM image-registry.openshift-image-registry.svc:5000/zuno-ai-build/ubi9-ubi-minimal:9
RUN microdnf install -y shadow-utils && \
    useradd -u 1001 -r -g 0 -d /app -s /sbin/nologin zuno && \
    microdnf remove -y shadow-utils && microdnf clean all

WORKDIR /app
COPY --from=build /out/agent-bff ./agent-bff

ENV LISTEN_ADDR=:8080

USER 1001
EXPOSE 8080
ENTRYPOINT ["./agent-bff"]
