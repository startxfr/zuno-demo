# ADR-0105: Automate source-specific knowledge ingestion

- **Status:** Partially implemented (tech/legacy cadence merged; Salesforce/Aramis clauses superseded by [ADR-0218](0218-drop-aramis-adapter-and-defer-salesforce-ingestion-cadence.md) — see the 2026-08-23 note below; live KFP schedule confirmation still blocked on rag-dspa readiness, see ADR-0330; tech's two sources now independently scheduled — see the 2026-08-30 amendment below — pending WP-100's operator-run confirmation)
- **Target:** v0.6 (retargeted from v0.7 on 2026-08-30 — v0.7 split into a short-term closeout band (v0.6) and a long-term/harder band (v0.7); this item and its already-closed siblings ADR-0206/ADR-0213/ADR-0218 move to v0.6, while ADR-0111/ADR-0115 (externally blocked) and ADR-0352 (large not-started effort) remain in v0.7. Previously retargeted from v0.1 on 2026-08-26 — roadmap reprioritization, grouped into v0.7 as a second, unrelated deferred-items set alongside WP-04's GitHub-Actions release-automation theme already there)
- **Date:** 2026-08-15
- **Decision owners:** Zuno Demo architecture team

## Decision

Promote this decision from a one-line v0.1-roadmap entry
(`0100-v0.1-roadmap.md`) to a full record.

Run scheduled ingestion according to each source's freshness objective
rather than one global monthly cadence. Technical web/Confluence
knowledge must be refreshable at least weekly, operational Salesforce
knowledge is expected to refresh on an hours-scale cadence, and
immutable legacy sources may be loaded on demand. Retain manual refresh
support.

Cadences are configured per domain in `knowledge/<domain>/domain.yaml`
(the freshness objective) and realized as per-source KFP recurring-run
schedules in `gitops/charts/rag-ingestion/values.yaml` (the top-level
`schedule` block for `knowledge.tech`, each `domains.<name>.schedule`
block for the others), rendered as one schedule ConfigMap per scheduled
domain that `ansible/roles/rag_ingestion/tasks/install.yml` turns into
KFP recurring runs. Manual refresh remains
`make d1 install rag-ingestion`, triggering an immediate run.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Consequences, Security/Operational considerations,
Acceptance criteria and Review evidence.

## Superseded (2026-08-23)

[ADR-0218](0218-drop-aramis-adapter-and-defer-salesforce-ingestion-cadence.md)
drops Aramis as an ingestion objective entirely (the service will not be
provisioned) and defers Salesforce's hours-scale batch-ingestion cadence to
an unscheduled backlog, out of v0.1/v0.2. The tech (weekly) and legacy
(on-demand) cadences this ADR decided are **not affected** and remain as
originally decided. See ADR-0218 for the full decision.

## Live verification check (2026-08-17, roadmap WP-22)

With live `oc` access, confirmed the exact remaining blockers rather than
leaving them generic:

- `salesforce-technical-credentials` (`zuno-ai-run`) is a real
  `SecretSyncedError: could not get secret data from provider` -
  `ansible/roles/vault/tasks/install.yml` only seeds Vault's
  `zuno/salesforce/technical` path when real `zuno_salesforce_url`/
  `zuno_salesforce_access_token` values are supplied (the default is the
  literal placeholder `xxxxxx`, deliberately never seeded). This is
  working as designed, not a bug - it is waiting on real Salesforce
  credentials.
- No `ExternalSecret` for Aramis exists in the cluster at all yet -
  credentials were never even attempted.
- The full `components/rag-ingestion/` test suite (38 tests, including
  the 22 source-adapter tests), `helm lint`/`helm template`, and
  `check_knowledge_refs.py` all pass against the current repo state - no
  repo-side gap found this pass.
- Live per-domain runs and KFP recurring-schedule confirmation remain
  additionally blocked on `rag-dspa` not being `Ready` on this cluster
  (see ADR-0330's 2026-08-17 note, WP-07) - independent of the credential
  gap above.

## Amended (2026-08-30)

The Decision text above states cadences are "realized as per-source KFP
recurring-run schedules" - true for sales (`fetch-salesforce`) and
sxa-legacy (`load-sxa-dump`) since WP-22, but `knowledge.tech`'s two
sources (`fetch-redhat`, `fetch-confluence`) shared one domain-level
schedule and one KFP pipeline despite the adapter-level separation WP-22
delivered. This gap is closed by WP-100: `fetch-redhat` and
`fetch-confluence` now have independent KFP recurring-run schedules
(`gitops/charts/rag-ingestion/values.yaml`'s `techSources.redhat` weekly /
`techSources.confluence` every 6 hours), each compiled to its own Pipeline
(`rag-corpus-ingestion-tech-redhat` / `-tech-confluence`), while continuing
to share `knowledge.tech`'s single database (ADR-0202 unaffected — the
`fetch_stages` scoping this required is task-level env, not a ConfigMap
split). See WP-100 for the detect-changes/changeset concurrency-isolation
fix that independent per-source scheduling required
(`components/rag-ingestion/src/rag_ingestion.py`'s `stage_detect_changes`
and `_changeset_key`).

## Related ADRs

- [ADR-0204](0204-generalize-the-rag-platform-to-multiple-isolated-knowledge-domains.md)
  — the multi-domain RAG platform these per-source adapters feed.
- [ADR-0205](0205-prefer-indexed-knowledge-for-read-and-live-tools-for-freshness-and-write.md)
  — the freshness policy that consumes each source's cadence objective.
- [ADR-0330](0330-integrate-the-rag-ingestion-pipeline-as-a-day1-component.md)
  — the Day 1 ingestion pipeline these cadences schedule.
- [ADR-0218](0218-drop-aramis-adapter-and-defer-salesforce-ingestion-cadence.md)
  — supersedes this ADR's Salesforce/Aramis clauses.
