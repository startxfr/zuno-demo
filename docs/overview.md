# Project Overview

Last reviewed: 2026-11-19

## Purpose

Zuno Demo is an internal demonstration of a reusable, governed agentic AI platform on Red Hat OpenShift AI. It serves business
agents (sales, technical consulting, architecture, finance and others) and several user experiences from one governed backend, and it
onboards a new agent through a declarative, signed definition rather than platform code. The agent catalogue is in
[the repository README](../README.md#initial-agent-catalog) and in [functional architecture](architecture/functional-architecture.md).

## Platform principles

- **One governed backend for every experience.** UnifAI runs the agents; Open WebUI, OpenClaw, Dify, kagent, OpenShift Lightspeed, Claude
  Code and the Blender add-on are clients of the same gateways and hold no model key, document store or tool credential of their own
  ([ADR-0561](adr/0561-adopt-unifai-as-the-agent-platform.md), [ADR-0587](adr/0587-admit-additional-user-experiences-over-the-one-governed-backend.md)).
- **Two gateways with the caller's own token.** The ai-gateway classifies the data (C1 to C3, it can only be raised), routes to a local
  model or an allowed SaaS model, applies guardrails and the per-persona budget; the mcp-gateway filters the tool catalogue by the
  caller's groups. The a2a-gateway carries agent-to-agent delegation with human approval of writes.
- **Keycloak for identity.** Personas, groups and token issuing for every service ([identity architecture](architecture/identity-architecture.md)).
- **Models on OpenShift AI.** Local models on MIG slices through KServe and llm-d, published by MaaS, plus controlled SaaS providers
  ([AI architecture](architecture/ai-architecture.md)).
- **Agents as signed releases.** Definitions and corp policies live in `startxfr/zuno-demo-agents` in the OKF profile 1.0, are signed
  keyless, pinned by one digest in `platform/okf/agents.lock` and admitted before they reach a pod
  ([agent platform architecture](architecture/agent-platform-architecture.md), [agents release integration](platform/agents-release-integration.md)).
- **GitOps as the only source of cluster state.** Argo CD applies the repository; Ansible and AAP run the Day 0 to Day 3 operations
  ([ADR-0608](adr/0608-keep-the-repository-the-only-source-of-cluster-state.md), [operations architecture](architecture/operations-architecture.md)).
- **Structured data.** PostgreSQL for platform state, MariaDB for the products that need it, Qdrant inside the UnifAI stack for
  knowledge vectors, S3 for objects ([data architecture](architecture/data-architecture.md)).

## Where to go next

| You want | Read |
|---|---|
| The platform map and every architecture view | [architecture/README.md](architecture/README.md) |
| To play a demonstration | [demo/README.md](demo/README.md) (catalogue, personas, lifecycle) |
| To install or operate the platform | [platform/README.md](platform/README.md) |
| Why a decision was taken | [adr/README.md](adr/README.md) |
| What is done and what is left | [roadmap/README.md](roadmap/README.md) |
