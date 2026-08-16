# SecNumCloud-oriented control matrix (ADR-0111)

Derived documentation - the authoritative sources are the policy/checker
files each row cites, not this file. Status values: `enforced-in-ci`
(a script blocks the change on failure), `enforced-on-cluster` (verified
against a live deployment, not re-derivable from the repo alone),
`gap` (not yet closed).

## Deployment

| Control | Status | Mechanism |
|---|---|---|
| Non-root, no privilege escalation, all capabilities dropped, seccomp `RuntimeDefault`, read-only root filesystem, dedicated ServiceAccount, no auto-mounted SA token unless needed | `enforced-in-ci` | `platform/security/check_workload_hardening.py` (ADR-0052), run in `.github/workflows/lint.yml`'s `helm` job |
| Every first-party Deployment chart is covered by the checker above | `enforced-in-ci` | `check_workload_hardening.py`'s `DEPLOYMENT_CHARTS` list - must be updated whenever a new chart is added |
| Deployed pods actually run under OpenShift's restricted SCC as claimed | `enforced-on-cluster` (2026-08-16) | verified live on demo222: every sampled first-party pod (agent-runtime, ai-gateway, mcp-gateway, tekos-bff, arkos-frontend) carries `openshift.io/scc: restricted-v2` |

## Supply chain

| Control | Status | Mechanism |
|---|---|---|
| Every first-party image is built, scanned (Trivy, HIGH/CRITICAL blocking) and SBOM'd in CI | `enforced-in-ci` | `.github/workflows/build-publish.yml` (ADR-0115) |
| Every first-party image is keyless-signed and the build inventory is reconciled against the real Dockerfile set | `enforced-in-ci` | `build-publish.yml`'s cosign step; `platform/supply-chain/check_build_matrix.py` (ADR-0324) |
| Deployable chart image tags are immutable (no `latest`) | `gap` (checker exists, non-blocking) | `platform/supply-chain/check_no_latest_tags.py`, `continue-on-error: true` in `lint.yml` until WP-04 stage 3 |
| First-party image signatures are verified before trusted deployment | `gap` (checker exists, nothing to verify yet) | `platform/supply-chain/verify_signatures.py` - see ADR-0115's Implementation state for the exact blocker (gap 7: no real release has run yet) |
| OKF agent bundles are signed and schema/policy-validated | `enforced-in-ci` (schema/policy); `gap` (signature - no real signed bundle yet) | `platform/supply-chain/sign_okf_bundle.py`, `validate_okf_bundle.py` (ADR-0106) |

## Identity

| Control | Status | Mechanism |
|---|---|---|
| End-user identity propagated via validated JWT, never trusted from request body | `enforced-in-ci` (tested) | `app/auth.py` in every service; `tests/test_auth.py` per component |
| Tool/knowledge access is a fail-closed policy intersection (agent declaration ∩ task rights ∩ user groups ∩ classification ∩ platform policy) | `enforced-in-ci` (tested) | `components/mcp-gateway/app/policy.py` (ADR-0011/0036); `tests/test_bindings.py` |
| No nominative/static demo credentials committed to git | `enforced-in-ci` | `ansible/roles/vault`'s self-generated-credentials pattern (ADR-0041); no automated repo scan for this yet - see Data row below |
| Every physical tool binding declares an explicit, non-inferred authentication mode | `enforced-in-ci` (2026-08-15) | `platform/bindings/tools/tool-bindings.yaml` (ADR-0208); enforced in `main.py`'s `invoke_tool` between the policy decision and `invoke_downstream`, `app/delegation.py`; `test_auth_mode_enforcement.py` (WP-26) |

## Network

| Control | Status | Mechanism |
|---|---|---|
| Every `zuno-ai-run` workload has its own precise, least-privilege NetworkPolicy (no namespace-wide same-namespace trust) | `enforced-in-ci` | `check_workload_hardening.py`'s `check_networkpolicies`, one call per workload chart |
| Platform namespaces (`zuno-auth`, `zuno-vault`, `zuno-data`, `zuno-monitoring`, `zuno-ai-platform`, `zuno-ai-build`, `zuno-mesh`) get a default-deny-other-namespaces baseline with explicit allow-lists | `enforced-in-ci` | `gitops/charts/namespaces/templates/networkpolicy-platform.yaml` |
| `zuno-ai-run` is excluded from the platform baseline (a namespace-wide same-namespace allow would defeat per-workload isolation, e.g. `mcp-sales-db`) | `enforced-in-ci` (2026-08-14) | `skipNetworkPolicy: true` on the `zuno-ai-run` entry in `gitops/charts/namespaces/values.yaml`, confirmed via `helm template --set policy.enabled=true` |
| MCP servers require a workload-identity token in addition to NetworkPolicy | `enforced-in-ci` (tested) | `X-Zuno-Gateway-Token` middleware, every `components/mcp-servers/*/server.py` (ADR-0037); each server's `tests/test_mcp_protocol.py` |
| Deployed NetworkPolicies actually block traffic as rendered (not just as authored) | `enforced-on-cluster` (2026-08-16) | verified live on demo222 in both directions: mcp-gateway (allow-listed) → sales-db-mcp:8000 returns 200; tekos-frontend (not allow-listed) → the same endpoint is dropped (curl exit 28 timeout) |

## Data

| Control | Status | Mechanism |
|---|---|---|
| No literal secret value (as opposed to `secretKeyRef`) is ever committed in a rendered chart manifest | `enforced-in-ci` (2026-08-14) | `check_workload_hardening.py`'s `check_no_hardcoded_secret_values` |
| Every credential is sourced from Vault via an ExternalSecret, never hardcoded | `enforced-in-ci` (spot-checked, no full-repo scanner yet) | `ansible/roles/vault`; every chart's `templates/externalsecret*.yaml` |
| Data classification (C1/C2/C3) is computed from the complete context and never silently downgraded | `enforced-in-ci` (tested) | `policies/data-classification/`; ADR-0034; per-service classification tests |
| Restricted-context (C2/C3, `external_model_policy.allow_context: false`) sources never reach an external model | `enforced-in-ci` (tested) | ADR-0035; `app/routing.py`'s `local_only` gate, `X-Zuno-Local-Only` propagation |
| Public repository fixtures contain no real/nominative commercial data | `enforced-on-cluster` (human review, no automated scanner) | ADR-0025 |
| Backup/recovery objectives are defined, mechanism configured and recency-checked | `enforced-in-ci` (2026-08-15) | `docs/platform/backup-recovery.md`; PostgreSQL pgBackRest (confirmed live) + `ansible/roles/postgresql/tasks/precheck.yml`; Vault CSI VolumeSnapshot `cronjob-backup.yaml` + `ansible/roles/vault/tasks/precheck.yml` (ADR-0112 / WP-13) |
| A restore has actually been executed and RTO/RPO validated live | `gap` | ADR-0112 / WP-13 — documented runbook exists, drill unexecuted |

## Availability (mechanism closed by WP-12; live measurement still pending)

| Control | Status | Mechanism |
|---|---|---|
| Shared platform services run with production-oriented availability (replicas, PodDisruptionBudget, topology spread) | `enforced-in-ci` (2026-08-15) | PDB + `topologySpreadConstraints` on agent-runtime/ai-gateway/mcp-gateway/rag-service/Keycloak; PostgreSQL/Redis already replica/PDB-complete via PGO/Bitnami defaults; `check_workload_hardening.py`'s availability checks (ADR-0101 / WP-12) |
| A measured 99.9% availability objective is defined and alerted on | `gap` (definition + alert rules exist, not yet measuring) | `docs/platform/slo.md` defines the SLO and ships `prometheusrule-slo.yaml` (disabled by default), but two prerequisites are still missing: `agent-bff` doesn't emit the `zuno_bff_requests_total` metric the query needs, and the OTel Collector's `prometheus` exporter is unconfirmed scraped by a live `ServiceMonitor`/`PodMonitor` (ADR-0102 / WP-12) |

## How to update this matrix

Every roadmap WP that closes a `gap` row here must flip it to
`enforced-in-ci`/`enforced-on-cluster` in the same change, citing the exact
file that now enforces it - never mark a row closed without a concrete
mechanism a reader can go verify.
