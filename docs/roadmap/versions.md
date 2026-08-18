# Version Roadmap

## MVP / v0

Seven-day internal vertical slice and five-agent demo, prioritizing Tekos as the first end-to-end implementation.

## v0.1

Industrialization: HA shared services, resumable workflows, automated ingestion/evaluation, stronger signing, source freshness, ACL synchronization and SecNumCloud-oriented hardening. Open ADRs: 0101–0117 plus 0322/0330 — [implementation roadmap](v0.1-v0.3-implementation-roadmap.md) Phase 1.

## v0.2

Knowledge governance: logical knowledge domains, knowledge authorization as policy intersection, multi-domain RAG generalization, indexed-vs-live routing, Salesforce/SXA-legacy separation, standardized tool authentication, project-scoped agent memory, MaaS governance-plane completion. Open ADRs: 0201–0209 — [implementation roadmap](v0.1-v0.3-implementation-roadmap.md) Phase 2.

## v0.3

Multi-agent rollout and optimization: the four remaining agent slices (Arkos, Comage, Advantage, Finage), multiple agent graph shapes, CDP/scoped capabilities, the AIAgent CRD/operator, LoRA/PEFT with dataset-to-model pipelines, dynamic adapters, benchmark-driven routing, self-service agent onboarding. Open ADRs: 0301–0309, 0326, 0327, 0340, 0342 — [implementation roadmap](v0.1-v0.3-implementation-roadmap.md) Phase 3.

## v0.4

Agent-to-agent evolution (ADR-0401 – ADR-0409): A2A protocol adoption, identity propagation across agent calls, controlled shared memory, delegation traceability and limits, specialized task-oriented frontend views, automated removal of inaccessible private RAG content and advanced human approval workflows.

## OKF stream

A standalone version line for the Open Knowledge Format initiative (ADR-0501 – ADR-0512), decoupled from the platform bands above — [OKF roadmap](okf-roadmap.md).

- **OKF v0.1** — content excellence in-repo: two-stage agent maturity model, generated per-agent authorization matrices, real `deployment/` content, `tests/` target structure, per-agent task tabs, quota policy via Kuadrant, project-bound tasks.
- **OKF v0.2** — extraction: OKF content moves to the standalone `zuno-okf` repository, consumed through a single pinned reference, with per-component adaptation hooks and a shared conformance suite.
- **OKF v0.3** — live reconciliation: the AIAgent operator watches the `zuno-okf` repository and reconciles running agent configuration within CR-declared boundaries.
