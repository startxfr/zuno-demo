# ADR-0111: Strengthen SecNumCloud-oriented security controls

- **Status:** Partially implemented - control matrix and first increment merged (`docs/security/secnumcloud-controls.md`, `platform/security/check_workload_hardening.py`'s new NetworkPolicy-coverage audit and hardcoded-secret check); the audit found and closed a real gap (`zuno-ai-run` was silently receiving an all-ports same-namespace NetworkPolicy, contradicting ADR-0037/0052's stated design - confirmed not yet live on the cluster, `policy.enabled` is currently false there) (2026-08-14, roadmap WP-11)

## Implementation note (2026-08-15)

WP-12 (HA/PDB), WP-13 (backup) and WP-26 (binding auth-mode) have since
merged their repo halves; the matrix's three corresponding rows are updated
to `enforced-in-ci` in the same change, each citing its concrete mechanism
(see `docs/security/secnumcloud-controls.md`'s Identity/Data/Availability
sections). Every remaining `gap` row in the matrix is now genuinely
live-cluster-only: restricted SCC verification, live NetworkPolicy
enforcement proof, the PostgreSQL/Vault restore drill (WP-13), and the SLO
measurement/alerting prerequisites (missing `agent-bff` metric + unconfirmed
`ServiceMonitor` scrape, WP-12). No further repo-side work closes any row in
this matrix — the remainder is the live-cluster verification pass itself.

## Correction (2026-08-18)

The 2026-08-15 note above was wrong about the Availability SLO row: both
of its "live-cluster-only" prerequisites turned out to be genuine
repo-side gaps. `agent-bff` had zero metrics instrumentation - not
unverified, simply absent - and no `ServiceMonitor` for the OTel
Collector's `prometheus` exporter existed anywhere in the repo. Both are
now closed: `components/agent-bff/internal/telemetry/` emits
`zuno_bff_requests_total`, and
`gitops/charts/observability/templates/servicemonitor-otel-collector.yaml`
is confirmed live-scraping (`up{job="zuno-otel-collector-collector"} ==
1"`, verified against the actual `monitoring.coreos.com/v1` Prometheus
instance that evaluates the SLO alert rules, not the differently-scoped
`monitoring.rhobs/v1` CRD group this cluster also has installed). See
`docs/platform/slo.md`'s own 2026-08-18 note for the full detail,
including the ArgoCD `selfHeal` vs. `oc rollout restart` conflict hit
while rolling this out (fixed by deleting pods directly instead) -
`zuno_bff_requests_total` is now confirmed real and queryable on
`prometheus-k8s` across all six agent BFFs. The Availability row stays
`gap` pending only the real 30-day measurement window - genuinely
time-only from here. Every other remaining `gap` row (restricted SCC, NetworkPolicy
enforcement, the WP-13 restore drill, supply-chain signing) was
re-checked this pass and does stay live-cluster/other-WP-only as the
2026-08-15 note described.

## Wave 1 closure pass (2026-08-18)

WP-12 and WP-13 discharged for real: the restore drill ran live
(PostgreSQL scratch-cluster restore verified identical to the primary
in 203s; Vault snapshot restore verified in 39s - both rows flip to
`enforced-on-cluster`), and the availability row closed on a short
measured window by explicit operator decision (100.000% over the
trailing 24h, both burn-rate alerts `health: ok`) plus a live failover
drill across seven services. Three rows remain genuine `gap`s, all
owned by WP-04/WP-05 and blocked on the same external dependency (a
GitHub billing lock on `startxfr/zuno-demo` that fails every Actions
job before it starts - not a repo-side gap):

- Immutable chart image tags (no `latest`) - `platform/supply-chain/check_no_latest_tags.py`
- First-party image signature verification - `platform/supply-chain/verify_signatures.py`
- OKF bundle signature - `platform/supply-chain/sign_okf_bundle.py`

Per WP-11's closure rule, ADR-0111 stays **Partially implemented** -
these three rows are the entire remaining v0.1 gap set; the ADR reaches
`Implemented` the moment WP-04/WP-05 close them.

## Status update (2026-08-25/26)

Of the three rows this ADR was waiting on above, two have since closed
via other WPs, not WP-04/WP-05: first-party image signature verification
and OKF bundle signature both flipped to `enforced-in-cluster` on
2026-08-22 (WP-070 and WP-069/ADR-0420 respectively - see
`docs/security/secnumcloud-controls.md`'s Supply chain section). The
**sole remaining `gap`** is immutable chart image tags, still blocked on
WP-04's external GitHub billing lock.

Also ran the live-cluster verification pass this ADR's "genuinely
live-cluster-only" rows were always waiting on, re-confirming the
2026-08-18 Wave 1 results still hold and closing the one row that had
never actually been proven live:

- **WP-12/WP-13 re-verified live** (failover drill and restore drill
  re-run, same procedure as 2026-08-18): results consistent with no
  regression - see `docs/platform/slo.md`'s 2026-08-25/26 note and
  `docs/platform/backup-recovery.md`'s 2026-08-25 notes for the full
  numbers.
- **WP-26 (binding auth-mode) proven live for the first time**: an
  authenticated live call (`consultant-01`, real Keycloak token) to
  `list_drive_files` (`delegated-user`, no delegated credential
  available) got a live `403 delegated_credential_missing` from the
  running mcp-gateway - the first real proof of this control beyond
  `test_auth_mode_enforcement.py`. The `provider-delegated` branch
  (`workday.profile.*`) could not be exercised the same way: no agent
  declares any Workday tool in an `agent.okf.md` yet, so a live call is
  denied earlier, at the agent-declaration check, before `invoke_tool`
  ever reaches the auth_mode dispatch. Not a bug - correct fail-closed
  behavior from an earlier layer - but it means that specific branch
  stays proven only by inspection/CI until some agent actually adopts a
  `provider-delegated` tool.

ADR-0111 stays **Partially implemented**, now down to exactly the one
WP-04-owned gap.
- **Target:** v0.1
- **Date:** 2026-08-14
- **Decision owners:** Zuno Demo architecture team

## Decision

Promote this decision from a one-line v0.1-roadmap entry
(`0100-v0.1-roadmap.md`) to a full record.

Maintain a SecNumCloud-oriented control matrix at
`docs/security/secnumcloud-controls.md` mapping control families
(deployment, supply chain, identity, network, data) to their concrete
repo/cluster mechanisms and one of: `enforced-in-ci`,
`enforced-on-cluster`, `gap`. Each roadmap increment closes named
`gap` rows; CI-enforceable controls are added to
`platform/security/check_workload_hardening.py` (or a sibling checker)
so regressions block. The matrix is derived documentation - the
authoritative sources remain the policy/checker files it cites.

First increment (this WP): NetworkPolicy default-deny coverage for all
first-party namespaces; PodDisruptionBudget presence is WP-12's
concern; secrets-mount hardening checks (no hardcoded literal secret
values where `secretKeyRef` is required); image-provenance rows point
at ADR-0115.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Consequences, Security/Operational considerations,
Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0037](0037-protect-mcp-servers-with-network-and-workload-identity-boundaries.md)
- [ADR-0041](0041-remove-nominative-demo-identities-and-static-passwords-from-git.md)
- [ADR-0052](0052-harden-all-workloads-for-openshift-restricted-security-and-secnumcloud-objectives.md)
- [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md)
