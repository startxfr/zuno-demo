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

Agent-to-agent evolution (ADR-0401 – ADR-0409): A2A protocol adoption, identity propagation across agent calls, controlled shared memory, delegation traceability and limits, specialized task-oriented frontend views, automated removal of inaccessible private RAG content and advanced human approval workflows. Also carries ADR-0516 (diagram generation from LLM-authored Mermaid, rendered in-cluster by the `diagram-render` component alongside ADR-0415's SDXL `generate_image`), which is Implemented — landed 2026-08-23, status closed out 2026-08-26 with no work package, see [evidence](evidence/adr-0516-diagram-render.md). Six further v0.4 decisions were closed out to Implemented on 2026-08-27, having been delivered and in service while still reading `Proposed`: ADR-0415 (SDXL image generation via OVHcloud), ADR-0416 (gpt-oss-120b via OVHcloud) and ADR-0417 (Codestral via the Mistral API) — the latter two smoke-tested live that day, each returning a real completion; ADR-0518 (the Qwen3.6-27B / Qwen3-Embedding-0.6B / Qwen3.5-9B local model fleet, live-verified down to the re-ingested `vector(1024)` corpus); and ADR-0519 / ADR-0520 (RAG ingestion throughput, live-verified via WP-57 and WP-58 — `detect-changes` alone went from 3h48m to 13m25s). ADR-0415/0416/0417/0518 have no work package; ADR-0519/0520 are tracked as Phase 15. Added 2026-08-27, `Implemented` as of 2026-08-29 (three-half gate PASS and `comage-lora` version `wesh-20260829-145123` registered; the fine-tune initially broke Comage's tool calling, corrected by a two-sided tool-call corpus and now gated by a third half — see the ADR's amendment): ADR-0526, which fine-tunes a French urban-register variant of ADR-0518's Qwen3.5-9B training base, serves it as `qwen3.5-9b-wesh` beside its unmodified base on a different MIG node, and routes Comage to it by default and Tekos to it second. It supersedes ADR-0301 (decisions 1, 5) and ADR-0302 (decisions 2, 4) in part, replacing WP-34's never-run `comage-lora` objective; tracked as Phase 20 via WP-087. Added 2026-08-27: ADR-0527 and ADR-0528 (both `Proposed`), which make the project a first-class object — a `projects` table owning every `project_id`, four roles (`read < clone < write < admin`) granted to subjects or business-role groups, no owner column but a last-admin guard, a 54 000-character engagement context injected as budgeted background rather than instructions, cascade-archive deletion, and ADR-0209's `project_memberships` demoted to a projection — and then separate the Salesforce opportunity from the project's identity (an optional attribute making a project *customer* or *free*, verified at project save rather than at conversation start), re-keying quota and telemetry onto the Zuno `project_id` and adding the `zuno.project_id` span attribute. ADR-0527 supersedes ADR-0213 in full and ADR-0528 supersedes ADR-0512's clause 3 and its quota/observability keying; both land as Phase 21 via WP-088/WP-089/WP-090. They occupy the ground ADR-0404 (controlled shared memory) and ADR-0407 (task-oriented frontend views) had reserved without specifying.

## v0.5

Make the OpenShift AI MaaS governance plane live and route agent model calls through it end-to-end. Carries ADR-0201 (MaaS governance plane), ADR-0511 (OKF quota policy via Kuadrant), ADR-0512 (project-bound tasks with Salesforce-verified context) and ADR-0521 (route ai-gateway's local model traffic through MaaS, added 2026-08-25 as the direction-change ADR-0114's evidence doc anticipated once WP-27 proved the governance plane live) — all grouped here since their live-MaaS objective is one and the same milestone. Open WPs: WP-55 (ADR-0512's clause 3 and its quota/telemetry keying were superseded by ADR-0528 on 2026-08-27 — see the v0.4 band; WP-55's merged work stands, its remaining live-Salesforce pass moves to WP-090). (WP-27 and WP-54 closed Done 2026-08-25 — ADR-0201/ADR-0511 both Implemented; WP-076 closed Done 2026-08-26 — ADR-0521 Implemented, both local models routed through MaaS with drill-proven direct fallback). This band also carries ADR-0522 (enable OpenShift AI's built-in monitoring stack side-by-side with the existing observability stack), Implemented 2026-08-26 via WP-078 (metrics), WP-079 (traces) and WP-080 (Perses/Route/Dashboard), all three Done and live-verified — tracked as Phase 17. Phase 1 deliberately ends with zero cross-stack data flow; unifying the two stacks is a separate, not-yet-started follow-up.

## v0.6

Close out the roadmap-reprioritization cluster carried in v0.7 through 2026-08-30. Retargeted here on 2026-08-30, splitting v0.7 by done-ness into this short-term closeout band and a long-term/harder v0.7: ADR-0105 (automate source-specific knowledge ingestion), ADR-0206 (separate current Salesforce knowledge from legacy SXA), ADR-0213 (role-based conversation sharing) and ADR-0218 (drop the Aramis ingestion adapter and defer the Salesforce ingestion cadence). All four are already delivered — WP-22 and WP-23 are `Done`, ADR-0213 is `Superseded by ADR-0527` (WP-066 `Abandoned` with it — sharing moved from the conversation to the project; see the v0.4 band), and ADR-0218 is `Implemented` (the Aramis adapter physically removed from the repository: code, ansible, gitops, knowledge contracts, platform bindings and the Advantage OKF prose). Only `Target` moves for ADR-0105/0206/0213; their status fields and WP states are unchanged. What ADR-0218 leaves deferred (not tracked by any WP in this band) is the Salesforce half only — `fetch-salesforce` and its hours-scale cadence, with `domains.sales` still shipped `enabled: false` in the tree; `knowledge.adv` keeps its domain descriptor and `rag-adv` binding with no ingestion adapter, and Comage's live Salesforce MCP-tool access is untouched. This band reuses the slot vacated when ADR-0517 retargeted out to v0.8 (see that band below).

## v0.7

Automate the release/supply-chain pipeline using GitHub Actions (build, sign, publish, promote). Carries ADR-0115 (immutable/verifiable software supply-chain artifacts), retargeted from v0.1 on 2026-08-24 — WP-04's three-stage GitHub Actions + Quay release work. Also carries ADR-0111 (strengthen SecNumCloud-oriented security controls), retargeted from v0.1 on 2026-08-26 — its one remaining gap (immutable chart image tags) is blocked on the same WP-04 GitHub billing lock as ADR-0115. Both are hard-blocked on an external GitHub-billing/Quay-cutover decision with no repo-side fix, which is why they anchor the long-term/harder half of the 2026-08-30 v0.6/v0.7 split.

Separately, this band also carries ADR-0352 (run day-0 platform services in internal or external mode), `Proposed` and not yet started: reclassifying the platform's 28 day-0 components into three tiers (internal-only, externally-substitutable, and externally-required) with a `confidential.yml` schema per Tier-A component, planned to land one component-per-work-package starting with MariaDB as the pilot, then Keycloak ("the first hard one"), then Vault, then the rest. No work package exists for it yet. This is the largest not-started item in the v0.7 band and, alongside ADR-0111/ADR-0115's external blocker, is why it stays in the long-term/harder half of the split rather than moving to v0.6 with the closed-out cluster above.

## v0.8

Prove the platform's Day 0–3 automation is complete and portable by redeploying the full stack from scratch on a new cluster (`demo333`). Carries [ADR-0517](../adr/0517-redeploy-the-full-platform-from-scratch-on-a-new-demo333-cluster.md), retargeted from v0.6 on 2026-08-30 — deprioritized behind v0.7's release-automation work. Also carries [ADR-0533](../adr/0533-consolidate-advantage-and-finage-non-promotion-into-a-dedicated-decision.md) (consolidate Advantage's and Finage's non-promotion into a dedicated decision), a new small ADR authored 2026-08-30 to hold the open question of whether either agent is ever promoted to `active`.

## v0.9

Adopt RHTAS as the platform's artifact trust and supply-chain service.
Carries [ADR-0535](../adr/0535-adopt-rhtas-as-the-artifact-trust-and-supply-chain-service.md),
a new ADR authored 2026-08-30 that supersedes ADR-0420 (v0.4, in-cluster
Vault Transit signing) — a product-demonstration decision (showing Red
Hat's own trusted-software-supply-chain product on this platform), not a
reversal of ADR-0420's technical reasoning, which remains valid: Vault
Transit is smaller, cheaper and fully sufficient for the signing problem on
its own. WP-104 deploys RHTAS, wires Keycloak/OIDC signing identities, cuts
the existing 14 signed first-party images over to RHTAS/Cosign keyless
signing, and deploys the Sigstore Policy Controller in audit-only mode.
OKF bundle trust (blocked on ADR-0506/ADR-0507's still-`Proposed` `zuno-okf`
extraction), AI/model artifact trust, and admission enforcement (reject
mode) are deliberately left for later ADRs/WPs, authored once each is
actually ready to start rather than pre-declared now. This band reuses no
prior vacated slot — v0.6 was reused earlier the same day for an unrelated
closeout cluster, and v0.7/v0.8 already carry differently-blocked work — so
v0.9 is a genuinely new band.

## OKF stream

A standalone version line for the Open Knowledge Format initiative (ADR-0501 – ADR-0512), decoupled from the platform bands above — [OKF roadmap](okf-roadmap.md).

- **OKF v0.1** — content excellence in-repo: two-stage agent maturity model, generated per-agent authorization matrices, real `deployment/` content, `tests/` target structure, per-agent task tabs. (Quota policy via Kuadrant and project-bound tasks — ADR-0511/ADR-0512 — retargeted to platform v0.5 on 2026-08-24, see that band above.)
- **OKF v0.2** — extraction: OKF content moves to the standalone `zuno-okf` repository, consumed through a single pinned reference, with per-component adaptation hooks and a shared conformance suite.
- **OKF v0.3** — live reconciliation: the AIAgent operator watches the `zuno-okf` repository and reconciles running agent configuration within CR-declared boundaries.
