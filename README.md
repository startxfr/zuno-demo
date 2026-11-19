# Zuno Demo

Zuno Demo is an internal MVP demonstrating a reusable agentic AI platform on Red Hat OpenShift AI. The platform hosts an initial catalog of five business agents while keeping runtime components generic and agent behavior declarative.

## Objectives

1. Demonstrate OpenShift AI capabilities for enterprise agentic applications.
2. Deliver usable internal AI agents (three are `active` today, see the catalog below).
3. Build a reusable platform where new agents can be onboarded primarily through declarative configuration instead of bespoke platform code.

## MVP target

- Red Hat OpenShift Container Platform 4.22 on AWS, installed with IPI.
- Red Hat OpenShift AI 3.5 (`rhods-operator.3.5.0` GA, `stable-3.5` channel) as the platform default. demo333 runs the 3.6.0-ea.2 early access on `beta` on purpose (WP-195 step 6, pinned in `ansible/clusters/demo333.yml`).
- GPU inference on NVIDIA RTX PRO 6000 Blackwell 96 GB nodes (`g7e.4xlarge`) partitioned by MIG, next to infra and general node pools ([ADR-0614](docs/adr/0614-split-the-cluster-into-infra-general-worker-and-gpu-node-pools.md), [physical architecture](docs/architecture/physical-architecture.md)).
- About 50 named users, 10 expected concurrent users, and 5 concurrent active conversations as the initial sizing reference.
- First-token objective below 6 seconds for interactive chat paths.
- Long-running document workflows may run for up to 10 minutes.
- Internal MVP first; 99.9% availability is an industrialized-target objective.

## Initial agent catalog

The initial catalog had five agents; eight definitions exist today in the agents repository. Status is read from the admitted release
(2026-11-18) and can change with it; the per-agent view is in [docs/agents/README.md](docs/agents/README.md).

- **Tekos** - technical consultant assistant (`active`).
- **Arkos** - architecture assistant (`active`).
- **Comage** - sales assistant (`active`).
- **Advantage** - sales administration assistant (`draft`).
- **Finage** - finance assistant (`draft`).
- **Naveo** - onboarding assistant, **Soursage** - recruiting assistant, **Cognos** - board-level assistant (`draft`).

The agents are served by UnifAI (ADR-0561), deployed from the admitted zuno-demo-agents release (ADR-0580), and consume shared platform services such as the AI/inference gateway, MCP gateway, RAG services, model serving, identity, secrets, observability, and data services. The original per-agent frontend/BFF deployments, the agent runtime and the AIAgent operator were retired in WP-156.

## History

The first build (v0, ADR-0031) ran Tekos end to end with its own frontend, BFF and Agent Runtime, and kept the other agents as catalog
entries. That stack was retired on 2026-10-23 (WP-156) when UnifAI became the agent platform. What exists now is described in the
[project overview](docs/overview.md) and the [architecture documentation](docs/architecture/README.md); the decisions and their dates are
in the [ADR index](docs/adr/README.md).

## Repository principles

- GitHub is the canonical source repository for the demo.
- Documentation and architecture deliverables are written in English and stored as Markdown.
- Architecture decisions are recorded as ADRs, immutable except for dated amendment notes, with a status index in `docs/adr/README.md`.
- Agent definitions use Open Knowledge Format (OKF) 0.2 with the frozen Zuno profile 1.0 ([ADR-0615](docs/adr/0615-align-the-zuno-okf-profile-with-upstream-okf-0-2-and-freeze-it-as-profile-1-0.md)), and live in [zuno-demo-agents](https://github.com/startxfr/zuno-demo-agents).
- Real commercial data and nominative data must never be committed to this public repository.
- `MEMORY.md` captures the project context so future work can resume consistently.
- Component images are built, scanned, SBOM'd and signed in CI and published under immutable tags (ADR-0115) - see `.github/README.md` and `RELEASING.md`.

## Operator workflow

Three manual inputs, and no secret is ever committed (ADR-0024): the
OpenShift API endpoint and a cluster-admin token; `ansible/confidential.yml`,
copied from the gitignored example and holding this environment's credentials
and per-cluster configuration; and, on a cluster whose catalog has moved past
the pinned build, a deliberate OpenShift AI version choice. Everything else is
automated - `make d0 check` reports anything missing before a first install and
applies nothing. See
[docs/platform/prerequisites.md](docs/platform/prerequisites.md).

```bash
oc login https://api.mycluster.com:6443 --token=<cluster-admin token>
ansible-galaxy collection install -r ansible/requirements.yml

# Day 0 (ADR-0056): cluster prerequisites - operators, CRDs, namespaces,
# secrets. "d0" is a short alias for "day0".
make d0 check
make d0 check namespaces
make d0 install
make d0 all argocd   # check + install, one component

# Day 1 (ADR-0060/ADR-0421): the remaining AI-platform-operator stack -
# mesh, databases, Kueue, OpenShift AI, etc.
make d1 check
make d1 check kiali
make d1 install
make d1 all openshift-ai   # check + install, one component
make d1 reconcile openshift-ai   # diagnose blockers and apply known remediations

# Day 2 (ADR-0060): AI infrastructure (llm, models) and content
# ingestion - build the platform's own component images, then run them.
make d2 build
make d2 install
make d2 check              # ADR-0053 acceptance/security gate for `agents`
make d2 reconcile models   # unwedge a model rollout blocked by the GPU quota (asks first)

# Day 3 (ADR-0057/0058): agent availability test and stresstest.
make d3 test
```

See [docs/README.md](docs/README.md).
