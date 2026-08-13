# ADR 00xx Implementation Backlog

Status scan of ADR-0001 – ADR-0056 (2026-08-13): 50 implemented, 3 superseded
(ADR-0018, ADR-0023, ADR-0050 — replaced by ADR-0322/ADR-0329), 3 open.
The open decisions below are ordered by target version and readiness.

## 1. ADR-0051 — Immutable and verifiable supply chain artifacts (v0, partially implemented)

The only v0-target ADR still open. All remaining gaps reduce to one blocker:
no real end-to-end build → publish → sign cycle has run against GitHub Actions + Quay (gap 7).

1. Run `.github/workflows/build-publish.yml` with real Quay/GitHub credentials to produce one signed release (gap 7).
2. Pin the 8 `tag: latest` fields across 7 charts to the resulting immutable tags (gap 2).
3. Make `platform/supply-chain/check_no_latest_tags.py` blocking in `lint.yml` (gap 3).
4. Point Argo CD `targetRevision: main` at the reviewed release tag (gap 4).
5. Add signature verification to the promotion/deployment path (gap 6).

## 2. ADR-0049 — Zuno as policy router in front of OpenShift AI MaaS (v1, to be implemented)

Evolve `components/ai-gateway` to delegate model access, subscriptions and quotas to
OpenShift AI MaaS while Zuno keeps the business-aware policy layer (C1/C2/C3,
sovereignty, task requirements, cost). First step per the ADR: prototype the MaaS
adapter behind the existing OpenAI-compatible model client and compare feature
coverage before removing current gateway capabilities.

## 3. ADR-0026 — AIAgent Kubernetes CRD and operator (v1, proposed)

Deliberately deferred: a plain Deployment plus GitOps manifests is sufficient while
Tekos is the only agent. Implement once a second agent lands and reconciliation
logic earns its cost. Still Proposed, lowest urgency.

## Note

ADR-0043 is implemented, but its residual work (confluence, google-workspace,
lucidchart and web-search MCP servers) is tracked under ADR-0326.

See the [ADR index](../adr/README.md) for authoritative per-ADR status.
