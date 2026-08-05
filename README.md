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

- **Comage** - sales assistant.
- **Tekos** - technical consultant assistant.
- **Arkos** - architecture assistant.
- **Advantage** - sales administration assistant.
- **Finage** - finance assistant.

Each agent has a dedicated frontend and BFF deployment while consuming shared platform services such as the agent runtime, AI/inference gateway, MCP gateway, RAG services, model serving, identity, secrets, observability, and data services.

## v0 build status

Tekos is formally the sole mandatory end-to-end business path for v0
(ADR-0031): the v0 vertical slice implements **Tekos** end to end (frontend,
BFF, Agent Runtime with LangGraph orchestration, MCP Gateway, RAG service,
sales-db MCP tool, real Keycloak login with 13 anonymized demo personas
(ADR-0041) across two orthogonal group dimensions - agent entitlement and
business role (ADR-0040)). Comage, Advantage, Finage and Arkos remain catalog-only:
they exist as OKF definitions (structurally validated by `make check`,
ADR-0031), reserved namespaces and access-gated portal tiles, without a
running workflow - business-functional builds for all four move to v1, see
`platform/architecture/agent-platform-separation.md`. The
AIAgent CRD/operator (originally v0) is retargeted to v1 - see ADR-0026.

## Repository principles

- GitHub is the canonical source repository for the demo.
- Documentation and architecture deliverables are written in English and stored as Markdown.
- Architecture decisions are recorded as immutable ADRs covering v0, v1, v2, and v3 evolution.
- Agent definitions use Open Knowledge Format (OKF) v0.2 plus a Zuno-specific extension profile.
- Real commercial data and nominative data must never be committed to this public repository.
- `MEMORY.md` captures the project context so future work can resume consistently.
- Component images are built, scanned, SBOM'd and signed in CI and published under immutable tags (ADR-0051) - see `.github/README.md` and `RELEASING.md`.

## Operator workflow

The only manual input for the entire install is the OpenShift API endpoint
and a cluster-admin token (ADR-0024) - everything else is automated:

```bash
export K8S_AUTH_HOST=https://api.mycluster.com:6443
export K8S_AUTH_API_KEY=<cluster-admin token>
ansible-galaxy collection install -r ansible/requirements.yml

# Day 0 (ADR-0056): cluster prerequisites - operators, CRDs, namespaces,
# secrets. "d0" is a short alias for "day0".
make d0 check
make d0 check keycloak
make d0 install
make d0 configure
make d0 all openshift-ai   # check + install + configure, one component

# Day 1: build the platform's own component images, then run the platform.
make d1 build
make d1 run
make d1 check              # ADR-0053 acceptance/security gate for `agents`
```

See [docs/README.md](docs/README.md).
