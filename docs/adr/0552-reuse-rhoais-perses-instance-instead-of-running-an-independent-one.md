# ADR-0552: Reuse RHOAI's Perses instance instead of running an independent one

- **Status:** Accepted
- **Target:** v0.5
- **Date:** 2026-09-07
- **Decision owners:** Zuno Demo architecture team
- **Supersedes ADR-0551** in part (decisions 2 "one Perses server instance"
  and 3 "PersesGlobalDatasource" auth strategy). ADR-0551's decisions 1
  (physical namespace split), 4 (UIPlugin console integration), 5 (phased
  rollout) and 6 (namespace mapping) are unaffected and remain in force.

## Context

WP-138 implemented ADR-0551's decision to run a second, independent `Perses`
server instance (`perses.dev/v1alpha2`) in `zuno-monitoring`, alongside
RHOAI's own `data-science-perses` instance in `redhat-ods-monitoring`
(ADR-0522/WP-080). Applying it live broke RHOAI's dashboards for ~14
minutes, immediately rolled back - see ADR-0551's dated correction note for
the full incident record.

Root cause, confirmed against both live cluster behavior and upstream
documentation: `instanceSelector` on `PersesDashboard`/`PersesDatasource`/
`PersesGlobalDatasource` is a standard Kubernetes `LabelSelector`. An empty
or absent selector matches **every** Perses instance on the cluster, by
Kubernetes' own selector semantics - not a Perses-specific bug. Every one of
RHOAI's own Perses resources has no `instanceSelector` set. With exactly one
Perses instance on the cluster this was unobservable; the moment a second
instance existed, RHOAI's resources became ambiguously matched and several
resolved against the new (backend-less) instance instead of their own.
Neither the Perses operator's own documentation, Red Hat's COO/Perses
articles, nor its release notes describe, support, or even discuss running
more than one Perses instance per cluster - one release note explicitly
frames the operator's status logic around "when no Perses instances are
found" (singular), not managing several. There is no documented way to
exempt RHOAI's own resources from matching a second instance without
editing those resources - out of scope, not ours to change.

## Decision

Duplicate the Grafana dashboards onto **RHOAI's existing `data-science-perses`
instance**, not a new one:

1. **No `Perses` server CR.** `gitops/charts/perses/templates/perses.yaml`
   (and its dedicated ServiceAccount/ClusterRoleBinding) are removed
   entirely. Every `PersesDashboard`/`PersesGlobalDatasource` this repo
   defines targets `data-science-perses` via
   `instanceSelector.matchLabels: {platform.opendatahub.io/part-of: monitoring}`
   - `data-science-perses`'s own live label, verified 2026-09-07.
2. **Datasource plugin shape matches RHOAI's own working examples exactly**
   (`plugin.spec.proxy: {kind: HTTPProxy, spec: {url, secret?}}`, never the
   `directUrl` shape this repo's first attempt used) - live-verified against
   RHOAI's four existing `PersesDatasource`s, all `Available: true`:
   - `prometheus` (thanos-querier, cross-namespace, TLS): reuses RHOAI's own
     `prometheus-web-tls-ca` ConfigMap (`redhat-ods-monitoring`) for
     `client.tls.caCert` rather than duplicating it - identical endpoint,
     identical CA. Bearer auth via a **new** ServiceAccount
     (`zuno-perses-prometheus-reader`) and long-lived token Secret, created
     in `redhat-ods-monitoring` (not `zuno-monitoring`) because that is
     where RHOAI's own `proxy.spec.secret` references resolve from (same
     namespace as the running server) - this is the one deliberate,
     additive footprint this ADR puts inside a namespace this repo does not
     own. Nothing existing in `redhat-ods-monitoring` is modified or
     deleted.
   - `mesh-prometheus` / `tempo`: no auth, matching RHOAI's own no-auth
     `data-science-prometheus-datasource` shape - `proxy.spec.url` only, no
     `secret`.
3. Everything else ADR-0551 decided is unchanged: dashboards still live in
   their target application namespace (decision 1's mapping table), the
   `UIPlugin` (decision 4) is unaffected by this change - it now also
   surfaces RHOAI's own pre-existing dashboards in the console, a side
   effect accepted as harmless - and the phased WP-138/WP-139 rollout
   (decision 5) continues unchanged in scope, just against this new
   backend.

## Operational considerations

This trades "fully independent of RHOAI" for "additive inside RHOAI's
namespace, RHOAI's own resources untouched." The distinction that matters:
this ADR creates **new** objects in `redhat-ods-monitoring`
(`zuno-perses-prometheus-reader` ServiceAccount/Secret/ClusterRoleBinding)
and reads one existing one (`prometheus-web-tls-ca`); it never edits,
deletes, or takes a dependency on any RHOAI-managed object's continued
existence beyond the running `data-science-perses` instance and that one
ConfigMap. If ADR-0522's monitoring stack is ever retired or its Perses
instance renamed, every resource this ADR adds fails safely (datasources go
`Unavailable`, dashboards show no data) - it does not block or alter
RHOAI's own reconciliation. Whether `plugin.spec.proxy.spec.secret`
genuinely resolves relative to the Perses server's own namespace (as
inferred from RHOAI's own working example, not from written documentation)
is confirmed at WP-138's live verification step, not assumed permanently -
if wrong, only the new ServiceAccount/Secret's namespace needs to move, no
architecture is at stake.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Consequences, Security considerations, Acceptance criteria and
Review evidence.

## Migration / evolution

If RHOAI ever changes `data-science-perses`'s label
(`platform.opendatahub.io/part-of: monitoring`) or its own datasource/CA
resource names, this ADR's `instanceSelector` and reused ConfigMap reference
would need updating - a live-verification-gated follow-up if it ever
happens, not a decision this ADR makes now.

## Related ADRs

- [ADR-0551](0551-add-namespace-scoped-perses-dashboards-alongside-grafana.md) -
  the record this ADR partially supersedes; its namespace-split mapping
  table, UIPlugin decision, and phased rollout stand unchanged.
- [ADR-0522](0522-enable-openshift-ai-monitoring-stack-side-by-side.md) - owns
  `data-science-perses`, now reused (read-only) rather than left
  untouched-and-separate as originally decided.
