# Build context MUST be the repository root (see gitops/charts/tekos'
# generated build instructions / CI), because this image bakes each agent's
# agent.okf.yaml into /agents/<name>/agent.okf.yaml at build time - the
# simplest way for this stateless portal to read every agent's declarative
# definition without wiring a ConfigMap-per-agent-file at deploy time.
#
#   docker build -f components/agent-frontend/Dockerfile -t zuno/agent-frontend:dev .

FROM golang:1.22 AS build
WORKDIR /src
COPY components/agent-frontend/go.mod ./
RUN go mod download
COPY components/agent-frontend/ ./
RUN CGO_ENABLED=0 GOOS=linux go build -o /out/agent-frontend .

FROM registry.access.redhat.com/ubi9/ubi-minimal:latest
RUN microdnf install -y shadow-utils && \
    useradd -u 1001 -r -g 0 -d /app -s /sbin/nologin zuno && \
    microdnf remove -y shadow-utils && microdnf clean all

WORKDIR /app
COPY --from=build /out/agent-frontend ./agent-frontend
COPY components/agent-frontend/static ./static
COPY agents ./agents

ENV AGENTS_DIR=/app/agents
ENV LISTEN_ADDR=:8080

USER 1001
EXPOSE 8080
ENTRYPOINT ["./agent-frontend"]
