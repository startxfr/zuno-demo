# ADR v1-Stream Implementation Backlog

Status scan of ADR-0001 – ADR-0056 (2026-08-13): 50 implemented, 3 superseded
(ADR-0018, ADR-0023, ADR-0050 — replaced by ADR-0322/ADR-0329), 3 open.

**Reorganized 2026-08-13:** the open decisions were renumbered into the v1
stream (ADR-0026 → ADR-0113, ADR-0049 → ADR-0114, ADR-0051 → ADR-0115), and
two v2 decisions were promoted as concretely implementable (ADR-0207 →
ADR-0116, ADR-0210 → ADR-0117). Items below are ordered by readiness.

## 1. ADR-0115 — Immutable and verifiable supply chain artifacts (partially implemented)

Formerly ADR-0051 (v0), retargeted v1. All remaining gaps reduce to one blocker:
no real end-to-end build → publish → sign cycle has run against GitHub Actions + Quay (gap 7).

1. Run `.github/workflows/build-publish.yml` with real Quay/GitHub credentials to produce one signed release (gap 7).
2. Pin the 8 `tag: latest` fields across 7 charts to the resulting immutable tags (gap 2).
3. Make `platform/supply-chain/check_no_latest_tags.py` blocking in `lint.yml` (gap 3).
4. Point Argo CD `targetRevision: main` at the reviewed release tag (gap 4).
5. Add signature verification to the promotion/deployment path (gap 6).

## 2. ADR-0116 — Decouple logical tool capabilities from backend bindings (to be implemented)

Formerly ADR-0207, promoted from v2. Replace `mcp-gateway/app/downstream.py`'s
hard-coded tool-name routing with a platform binding registry resolving stable
`<domain>.<resource>.<verb>` capability IDs; a contained gateway refactor and the
prerequisite for ADR-0117.

## 3. ADR-0117 — Implement Confluence as the first real external MCP integration (to be implemented)

Formerly ADR-0210, promoted from v2. Build a real MCP server in
`components/mcp-servers/confluence/` mirroring the existing sales-db server; the
`zuno/confluence/technical` Vault credential is already wired. First real consumer
of ADR-0116's binding layer.

## 4. ADR-0114 — Zuno as policy router in front of OpenShift AI MaaS (to be implemented)

Formerly ADR-0049. Evolve `components/ai-gateway` to delegate model access,
subscriptions and quotas to OpenShift AI MaaS while Zuno keeps the business-aware
policy layer (C1/C2/C3, sovereignty, task requirements, cost). First step per the
ADR: prototype the MaaS adapter behind the existing OpenAI-compatible model client
and compare feature coverage before removing current gateway capabilities.

## 5. ADR-0113 — AIAgent Kubernetes CRD and operator (proposed)

Formerly ADR-0026. Deliberately deferred: a plain Deployment plus GitOps manifests
is sufficient while Tekos is the only agent. Implement once a second agent lands
and reconciliation logic earns its cost. Still Proposed, lowest urgency.

## Note

ADR-0043 is implemented, but its residual work (google-workspace, lucidchart and
web-search MCP servers) is tracked under ADR-0326; the Confluence server is now
ADR-0117 above.

See the [ADR index](../adr/README.md) for authoritative per-ADR status.
