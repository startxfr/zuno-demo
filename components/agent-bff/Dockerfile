# Build context is this directory (unlike agent-frontend/agent-runtime/
# mcp-gateway, the BFF needs no repository-root context - it has no
# agent.okf.md OKF bundles to bake in).
#
#   docker build -t zuno/agent-bff:dev components/agent-bff

FROM golang:1.22 AS build
WORKDIR /src
COPY go.mod ./
COPY . ./
RUN CGO_ENABLED=0 GOOS=linux go build -o /out/agent-bff .

FROM registry.access.redhat.com/ubi9/ubi-minimal:latest
RUN microdnf install -y shadow-utils && \
    useradd -u 1001 -r -g 0 -d /app -s /sbin/nologin zuno && \
    microdnf remove -y shadow-utils && microdnf clean all

WORKDIR /app
COPY --from=build /out/agent-bff ./agent-bff

ENV LISTEN_ADDR=:8080

USER 1001
EXPOSE 8080
ENTRYPOINT ["./agent-bff"]
