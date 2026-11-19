# Zuno Demo Documentation

Last reviewed: 2026-11-19

This directory is the canonical documentation set for the Zuno Demo platform: what it is, how it is built, how to run it, how to demonstrate
it, and why each decision was taken.

## Reading order

1. [Project overview](overview.md)
2. [Architecture](architecture/README.md): the platform map (HLD) and every view, from functional to physical.
   - Core views: [functional](architecture/functional-architecture.md), [logical](architecture/logical-architecture.md),
     [physical](architecture/physical-architecture.md), [security](architecture/security-architecture.md),
     [identity](architecture/identity-architecture.md), [network](architecture/network-architecture.md),
     [data](architecture/data-architecture.md), [AI](architecture/ai-architecture.md), [sequence flows](architecture/sequence-flows.md).
   - Domain views: [agent platform](architecture/agent-platform-architecture.md), [experiences](architecture/experiences-architecture.md),
     [gateways](architecture/gateways-architecture.md), [MLOps](architecture/mlops-architecture.md),
     [supply chain](architecture/supply-chain-architecture.md), [observability](architecture/observability-architecture.md),
     [operations](architecture/operations-architecture.md).
3. [Agent catalog](agents/README.md), [agent request workflow](agents/request-workflow.md) and the [OKF workflow](agents/okf-workflow.md).
4. [Demonstrations](demo/README.md): the catalogue of scenarios with their personas, status and stress coverage, the lifecycle
   (`make demo`), the [golden path](demo/golden-path.md) and the [freeze protocol](demo/freeze-protocol.md).
5. [Platform runbooks](platform/README.md): prerequisites, installation, operations, key and password rotation, release sequence,
   backup, troubleshooting, the [stresstest](platform/stresstest.md).
6. [Security](security/README.md), [data](data/README.md) and [testing](testing/README.md).
7. [Architecture Decision Records](adr/README.md) and the [roadmap](roadmap/README.md).

## Where do I find...

| You want | Go to |
|---|---|
| The platform map, or one component's low-level design | [architecture/README.md](architecture/README.md) and the domain view of that component |
| Why a decision was taken, or whether it still holds | [adr/README.md](adr/README.md) (the status column is the authority) and its [change log](adr/CHANGELOG.md) |
| To play a demo, or to know whether one is show-ready | [demo/README.md](demo/README.md) and the status banner of the scenario page |
| To roll an agents release or a UnifAI release | [platform/agents-release-integration.md](platform/agents-release-integration.md), [platform/release-sequence.md](platform/release-sequence.md) |
| To fix a failing SaaS model or an expired key | [platform/saas-provider-key-rotation.md](platform/saas-provider-key-rotation.md) |
| What is done, what is next | [roadmap/README.md](roadmap/README.md) and the [implementation roadmap](roadmap/implementation-roadmap.md) |
| The security model and the control matrix | [security/README.md](security/README.md) |

## Documentation policy

All project documentation and architecture deliverables are maintained in English Markdown. Diagrams should use Mermaid whenever practical so they remain reviewable and version-controlled as text.
`python3 platform/docs/check_docs.py` checks the documentation against the code (links, ADR index, Makefile verbs, scenario tables) and runs in CI;
run it before every documentation commit.
