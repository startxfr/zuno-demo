# Version Roadmap

## MVP / v0

Seven-day internal vertical slice and five-agent demo, prioritizing Tekos as the first end-to-end implementation.

## v0.1

Industrialization: HA shared services, resumable workflows, automated ingestion/evaluation, stronger signing, source freshness, ACL synchronization and SecNumCloud-oriented hardening. Open ADRs: 0101–0117 plus 0322/0330 — [implementation roadmap](v0.1-v0.3-implementation-roadmap.md) Phase 1. (ADR-0111, SecNumCloud-oriented hardening, retargeted to v0.7 on 2026-08-26 — see that band below.) (ADR-0105, source-specific ingestion cadences, retargeted to v0.7 on 2026-08-26 — see that band below.)

## v0.2

Knowledge governance: logical knowledge domains, knowledge authorization as policy intersection, multi-domain RAG generalization, indexed-vs-live routing, Salesforce/SXA-legacy separation, standardized tool authentication, project-scoped agent memory. Open ADRs: 0202–0209 — [implementation roadmap](v0.1-v0.3-implementation-roadmap.md) Phase 2. (ADR-0201, MaaS governance-plane completion, retargeted to v0.5 on 2026-08-24 — see that band below.) (ADR-0206, Salesforce/SXA-legacy separation, retargeted to v0.7 on 2026-08-26 — see that band below.) (ADR-0213, role-based conversation sharing, retargeted to v0.7 on 2026-08-26 — see that band below.) (ADR-0218, which drops the Aramis ingestion adapter and defers the Salesforce ingestion cadence, retargeted from `Unscheduled (backlog)` to v0.7 on 2026-08-26 — see that band below.) Also carries ADR-0354 (retargeted from v0.3 on 2026-08-24), installing Ansible Automation Platform as a new Day 1 component (`aap`) plus a companion `aap-config` component that registers this repository as an AAP Project with a `day0_check` Job Template. (ADR-0216 and ADR-0217, the two SXA import/ingestion decisions, superseded by ADR-0219 on 2026-08-26 — SXA is now served as a RAG-only pre-2021 historical corpus; ADR-0219 is v0.2 and Implemented.) Open WPs: WP-072, WP-073, WP-084 (operator steps).

## v0.3

Multi-agent rollout and optimization: the four remaining agent slices (Arkos, Comage, Advantage, Finage), multiple agent graph shapes, CDP/scoped capabilities, the AIAgent CRD/operator, LoRA/PEFT with dataset-to-model pipelines, dynamic adapters, benchmark-driven routing, self-service agent onboarding. Open ADRs: 0301–0309, 0326, 0327, 0340, 0342 — [implementation roadmap](v0.1-v0.3-implementation-roadmap.md) Phase 3. Also carries ADR-0355, a new `mcp-aap` server exposing AAP cluster/platform audits to Tekos and Arkos once v0.2's `aap`/`aap-config` are live. Open WP: WP-074.

## v0.4

Agent-to-agent evolution (ADR-0401 – ADR-0409): A2A protocol adoption, identity propagation across agent calls, controlled shared memory, delegation traceability and limits, specialized task-oriented frontend views, automated removal of inaccessible private RAG content and advanced human approval workflows.

## v0.5

Make the OpenShift AI MaaS governance plane live and route agent model calls through it end-to-end. Carries ADR-0201 (MaaS governance plane), ADR-0511 (OKF quota policy via Kuadrant), ADR-0512 (project-bound tasks with Salesforce-verified context) and ADR-0521 (route ai-gateway's local model traffic through MaaS, added 2026-08-25 as the direction-change ADR-0114's evidence doc anticipated once WP-27 proved the governance plane live) — all grouped here since their live-MaaS objective is one and the same milestone. Open WPs: WP-55 (WP-27 and WP-54 closed Done 2026-08-25 — ADR-0201/ADR-0511 both Implemented; WP-076 closed Done 2026-08-26 — ADR-0521 Implemented, both local models routed through MaaS with drill-proven direct fallback).

## v0.6

Prove the platform's Day 0–3 automation is complete and portable by redeploying the full stack from scratch on a new cluster (`demo333`). New ADR: [ADR-0517](../adr/0517-redeploy-the-full-platform-from-scratch-on-a-new-demo333-cluster.md).

## v0.7

Automate the release/supply-chain pipeline using GitHub Actions (build, sign, publish, promote). Carries ADR-0115 (immutable/verifiable software supply-chain artifacts), retargeted from v0.1 on 2026-08-24 — WP-04's three-stage GitHub Actions + Quay release work. Also carries ADR-0111 (strengthen SecNumCloud-oriented security controls), retargeted from v0.1 on 2026-08-26 — its one remaining gap (immutable chart image tags) is blocked on the same WP-04 GitHub billing lock as ADR-0115.

Separately, and unrelated to the GitHub-Actions release-automation goal above, this band also carries ADR-0105 (automate source-specific knowledge ingestion, retargeted from v0.1 on 2026-08-26), ADR-0206 (separate current Salesforce knowledge from legacy SXA, retargeted from v0.2 on 2026-08-26), ADR-0213 (role-based conversation sharing, retargeted from v0.2 on 2026-08-26) and ADR-0218 (drop the Aramis ingestion adapter and defer the Salesforce ingestion cadence, retargeted from `Unscheduled (backlog)` on 2026-08-26) as a roadmap reprioritization. For ADR-0105/0206/0213 only their `Target` moved — WP-22 remains `Done`, WP-23 remains `Operator pending`, WP-066 is unchanged, and their status fields are unchanged. ADR-0218 also changed substance on 2026-08-26: the Aramis adapter is no longer merely untracked but physically removed from the repository (code, ansible, gitops, knowledge contracts, platform bindings and the Advantage OKF prose), taking that ADR to `Implemented`. What lands in this band is the Salesforce half only — `fetch-salesforce` and its hours-scale cadence, deferred rather than dropped, with `domains.sales` still shipped `enabled: false` in the tree. `knowledge.adv` keeps its domain descriptor and `rag-adv` binding with no ingestion adapter; Comage's live Salesforce MCP-tool access is untouched.

## OKF stream

A standalone version line for the Open Knowledge Format initiative (ADR-0501 – ADR-0512), decoupled from the platform bands above — [OKF roadmap](okf-roadmap.md).

- **OKF v0.1** — content excellence in-repo: two-stage agent maturity model, generated per-agent authorization matrices, real `deployment/` content, `tests/` target structure, per-agent task tabs. (Quota policy via Kuadrant and project-bound tasks — ADR-0511/ADR-0512 — retargeted to platform v0.5 on 2026-08-24, see that band above.)
- **OKF v0.2** — extraction: OKF content moves to the standalone `zuno-okf` repository, consumed through a single pinned reference, with per-component adaptation hooks and a shared conformance suite.
- **OKF v0.3** — live reconciliation: the AIAgent operator watches the `zuno-okf` repository and reconciles running agent configuration within CR-declared boundaries.
