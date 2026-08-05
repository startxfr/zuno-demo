# Build context MUST be the repository root (see gitops/charts/tekos'
# generated build instructions / CI), because this image bakes each agent's
# agent.okf.md OKF v0.2 Markdown bundle (ADR-0038) into /agents/<name>/ at
# build time - the simplest way for this stateless portal to read every
# agent's declarative definition without wiring a ConfigMap-per-agent-file
# at deploy time.
#
#   docker build -f components/agent-frontend/Dockerfile -t zuno/agent-frontend:dev .

# ADR-0044: reproducible frontend toolchain (Vite) producing static PatternFly
# React assets at build time - see components/agent-frontend/web. `npm ci`
# installs exactly what package-lock.json pins, not whatever `npm install`
# would resolve at build time, for a reproducible image.
FROM node:20-alpine AS webbuild
WORKDIR /src/web
COPY components/agent-frontend/web/package.json components/agent-frontend/web/package-lock.json ./
RUN npm ci
COPY components/agent-frontend/web/ ./
RUN npm run build

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
COPY --from=webbuild /src/web/dist ./web/dist
COPY agents ./agents

ENV AGENTS_DIR=/app/agents
ENV WEB_DIST_DIR=/app/web/dist
ENV LISTEN_ADDR=:8080

USER 1001
EXPOSE 8080
ENTRYPOINT ["./agent-frontend"]
