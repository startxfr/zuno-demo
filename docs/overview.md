# Project Overview

## Purpose

Zuno Demo uses Red Hat OpenShift AI to provide a reusable internal agent platform and an initial catalog of five agents (catalog: [README.md](../README.md#initial-agent-catalog)). The same platform must be able to onboard future agents primarily through declarative definitions.

## Shared platform principles

- Dedicated frontend and BFF per agent.
- Shared agent runtime and AI/inference gateway.
- Central MCP gateway in front of MCP servers.
- Keycloak-based authentication and authorization.
- PostgreSQL for business persistence and pgvector-based vector storage.
- OpenShift AI model serving for local models plus controlled SaaS providers.
- Declarative agent behavior with OKF v0.2 plus the Zuno extension profile.
- GitOps review workflow for agent definitions, prompts, policies and tools.
