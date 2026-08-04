# Project Overview

## Purpose

Zuno Demo uses Red Hat OpenShift AI to provide a reusable internal agent platform and an initial catalog of five agents. The same platform must be able to onboard future agents primarily through declarative definitions.

## Initial agents

| Agent | Audience | Primary capabilities |
|---|---|---|
| Comage | Sales | Follow-up prioritization, current deals, weekly sales synthesis |
| Tekos | Technical consultants | Official technical documentation RAG and internal Confluence knowledge |
| Arkos | Architects | DAT creation, Odyssey workshop preparation, Google Drive/Docs workflows |
| Advantage | Sales administration | New confirmed business and monthly sales reporting |
| Finage | Finance | Billable business and monthly invoice reporting |

## Shared platform principles

- Dedicated frontend and BFF per agent.
- Shared agent runtime and AI/inference gateway.
- Central MCP gateway in front of MCP servers.
- Keycloak-based authentication and authorization.
- PostgreSQL for business persistence and pgvector-based vector storage.
- OpenShift AI model serving for local models plus controlled SaaS providers.
- Declarative agent behavior with OKF v0.2 plus the Zuno extension profile.
- GitOps review workflow for agent definitions, prompts, policies and tools.
