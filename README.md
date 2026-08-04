# Zuno Demo

Zuno Demo is an internal MVP demonstrating a reusable agentic AI platform on Red Hat OpenShift AI. The platform hosts an initial catalog of five business agents while keeping runtime components generic and agent behavior declarative.

## Objectives

1. Demonstrate OpenShift AI capabilities for enterprise agentic applications.
2. Deliver five usable internal AI agents.
3. Build a reusable platform where new agents can be onboarded primarily through declarative configuration instead of bespoke platform code.

## MVP target

- Red Hat OpenShift Container Platform 4.20 on AWS, installed with IPI.
- Red Hat OpenShift AI 3.5 EA2.
- Two worker nodes with one NVIDIA L4 24 GB GPU each.
- About 50 named users, 10 expected concurrent users, and 5 concurrent active conversations as the initial sizing reference.
- First-token objective below 6 seconds for interactive chat paths.
- Long-running document workflows may run for up to 10 minutes.
- Internal MVP first; 99.9% availability is an industrialized-target objective.

## Initial agent catalog

- **Comage** — sales assistant.
- **Tekos** — technical consultant assistant.
- **Arkos** — architecture assistant.
- **Advantage** — sales administration assistant.
- **Finage** — finance assistant.

Each agent has a dedicated frontend and BFF deployment while consuming shared platform services such as the agent runtime, AI/inference gateway, MCP gateway, RAG services, model serving, identity, secrets, observability, and data services.

## Repository principles

- GitHub is the canonical source repository for the demo.
- Documentation and architecture deliverables are written in English and stored as Markdown.
- Architecture decisions are recorded as immutable ADRs covering v0, v1, v2, and v3 evolution.
- Agent definitions use Open Knowledge Format (OKF) v0.2 plus a Zuno-specific extension profile.
- Real commercial data and nominative data must never be committed to this public repository.
- `MEMORY.md` captures the project context so future work can resume consistently.

## Operator workflow

```bash
make precheck
make precheck keycloak
make prepare
make prepare openshift-ai
make configure
make configure models
make install
make check
```

See [docs/README.md](docs/README.md).
