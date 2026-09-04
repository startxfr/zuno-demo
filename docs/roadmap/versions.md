# Version Roadmap

What each version band is *for*. Per-ADR status is in the
[ADR index](../adr/README.md), which is the sole authority for it; work-package
state is in the [implementation roadmap](implementation-roadmap.md). Neither is
restated here — this file carries goals, and the open items each goal is still
waiting on.

The history of how ADRs moved between these bands (retargetings, renumberings,
band creation) is in the [ADR change log](../adr/CHANGELOG.md), not here.

## MVP / v0

Seven-day internal vertical slice and five-agent demo, prioritizing Tekos as
the first end-to-end implementation.

**72 ADRs, all closed. No open work packages.**

## v0.1

Industrialization: HA shared services, resumable workflows, automated
ingestion and evaluation, stronger signing, source freshness, ACL
synchronization and SecNumCloud-oriented hardening.

**29 ADRs, all closed. No open work packages.**

## v0.2

Knowledge governance: logical knowledge domains, knowledge authorization as
policy intersection, multi-domain RAG generalization, indexed-vs-live routing,
standardized enterprise tool authentication, project-scoped agent memory. Also
carries ADR-0354, which installs Ansible Automation Platform as a Day 1
component (`aap`) plus an `aap-config` companion.

**14 ADRs, all closed.** Open: WP-098.

## v0.3

Multi-agent rollout and optimization: the four remaining agent slices (Arkos,
Comage, Advantage, Finage), multiple agent graph shapes, CDP and scoped
capabilities, the AIAgent CRD and operator, LoRA/PEFT with dataset-to-model
pipelines, benchmark-driven routing. Also carries ADR-0355 (the `mcp-aap`
server exposing AAP audits to agents) and ADR-0532, which accepts
`knowledge.adv` as sourceless pending a replacement adapter.

**Closed 2026-08-30** — ADR-0309/WP-42, the last open item, went `Implemented`
after a live verification (autonomy enabled, one full tune-evaluate cycle
observed, one rollback forced), which closed the whole v0.1–v0.3 roadmap.

**16 ADRs.** Open: ADR-0353 (stub); WP-34.

## v0.4

Agent-to-agent evolution: A2A protocol adoption, identity propagation across
agent calls, controlled shared memory, delegation traceability and limits,
task-oriented frontend views, automated removal of inaccessible private RAG
content, advanced human approval workflows (ADR-0401 – ADR-0409, all still
stubs). The band also carries the model-fleet, ingestion-throughput,
observability and project work actually delivered during it — ADR-0516,
ADR-0518 – ADR-0520, ADR-0524 – ADR-0531, ADR-0536.

**33 ADRs.** Open: ADR-0401 – ADR-0409 (stubs); WP-55, WP-093, WP-101, WP-112.

## v0.5

Make the OpenShift AI MaaS governance plane live and route agent model calls
through it end-to-end. Also carries the RHOAI monitoring stack enabled
side-by-side with the existing observability stack (ADR-0522, ADR-0523) and
per-run trace correlation (ADR-0543). ADR-0537 (RHOAI `HardwareProfile` CRs
for local models) closed `Implemented` 2026-09-03; its `ExternalModel`/MaaS
half, permanently blocked upstream, split out the same day to
[ADR-0541](../adr/0541-integrate-mistral-and-gpt-oss-120b-as-maas-externalmodels.md)
in the v0.7 band below.

**8 ADRs, all closed.** Open: WP-55, WP-101, WP-122.

## v0.6

Close out the roadmap-reprioritization cluster left over from v0.7:
source-specific ingestion cadences, Salesforce/SXA-legacy separation, and the
superseded role-based conversation sharing. All four items were already
delivered; the band exists to formalize their retargeted status.

**4 ADRs, all closed.** Open: WP-101.

## v0.7

Automate the release/supply-chain pipeline using GitHub Actions (build, sign,
publish, promote). ADR-0111 and ADR-0115 are both hard-blocked on an external
GitHub-billing/Quay-cutover decision with no repo-side fix. The band also
carries the OKF extraction-and-reconciliation chain (ADR-0506 – ADR-0510),
gated on an owner-created `zuno-okf` repository that does not yet exist, and
the RHOAI 3.5 workload surfaces (ADR-0538 – ADR-0540), TrustyAI (ADR-0534),
model autoscaling (ADR-0542), and mistral/gpt-oss-120b as MaaS
`ExternalModel`s (ADR-0541, split 2026-09-03 from ADR-0537's now-Implemented
HardwareProfile half - blocked upstream, see that ADR's body).

**13 ADRs.** Open: ADR-0111, ADR-0115 (both `Deferred`), ADR-0506 – ADR-0510,
ADR-0538, ADR-0541; WP-48 – WP-53, WP-115, WP-125.

## v0.8

Prove the platform's Day 0–3 automation is complete and portable by
redeploying the full stack from scratch on a new cluster (`demo333`). Also
holds the open question of whether Advantage or Finage is ever promoted to
`active` (ADR-0533).

**Widened 2026-09-03**, by the same finding twice over. WP-118 closed
ADR-0517's nine portability blockers by removing `demo222` literals; a second
audit pass found no further literals and three further blockers anyway — a
cluster-only mutation invisible to any `grep` (B10, closed by WP-123),
`demo222`'s ACME end state committed to git (B11), and seven S3 buckets a
second cluster would write straight into (B12, the only blocker that damages
the *existing* cluster). Removing literals one at a time was never going to
converge, so the band now also carries ADR-0546 (a cross-cluster source bucket
plus a per-cluster bucket convention, executed by WP-131) and ADR-0547 (every
cluster-specific value becomes an Ansible parameter, seeded through Vault when
secret — executed by WP-132, verified by WP-130's Day 0 readiness probe).
ADR-0517's own run stays blocked on an operator provisioning `demo333`.

**4 ADRs.** Open: ADR-0517, ADR-0546, ADR-0547. Open work packages: WP-131
(WP-130 and WP-132 done 2026-09-04).

## v0.9

Adopt RHTAS as the platform's artifact trust and supply-chain service
(ADR-0535) — a product-demonstration decision superseding ADR-0420's Vault
Transit signing, not a reversal of its technical reasoning. OKF bundle trust,
AI/model artifact trust and admission enforcement are deliberately left to
later ADRs. The band also carries the two agent-onboarding decisions parked
behind it (ADR-0307, ADR-0410 — WP-41 was cancelled 2026-08-23) and the day-0
internal/external tiering effort (ADR-0352), which has no work package yet.

**4 ADRs.** Open: ADR-0307, ADR-0352, ADR-0410. No open work packages.

## OKF stream

A standalone version line for the Open Knowledge Format initiative, decoupled
from the platform bands — [OKF roadmap](okf-roadmap.md).

- **OKF v0.1** — content excellence in-repo: the two-stage agent maturity
  model, generated per-agent authorization matrices, real `deployment/`
  content, the `tests/` target structure, per-conversation task tabs.
  **8 ADRs.** Open: ADR-0501. No open work packages.
- **OKF v0.2 / OKF v0.3** — extraction into `zuno-okf` and live operator
  reconciliation. Both milestones are **vacant**: every ADR that defined them
  (ADR-0506 – ADR-0510) was retargeted to platform v0.7 on 2026-08-30. Their
  work packages (WP-48 – WP-53) are tracked as phases 34–35 of the
  [implementation roadmap](implementation-roadmap.md).
