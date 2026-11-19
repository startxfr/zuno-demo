# Threat Model

What the platform defends, against whom, and which decision closes each threat. This page is the threat model that
[ADR-0602](../adr/0602-harden-the-platform-trust-boundaries-before-a-customer-runs-it.md) (clause 13) asks for. It is a map from threats to
decisions and work packages, drawn from the review of 2026-11-06 (code and charts read, nothing replayed on a cluster); it is not a
penetration test. The security views are in [security architecture](../architecture/security-architecture.md); the demo and hardened profiles
are described in [operations](../platform/operations.md#security-profiles-demo-and-hardened-adr-0602-wp-223).

## The standing threats

| Threat | Main defence | Decision |
|---|---|---|
| Prompt injection, through a user message or through a retrieved document or tool result | Guardrails in the ai-gateway (NeMo backend, observe mode on every level; blocking is a mode, not today's default) | [ADR-0567](../adr/0567-move-trustyai-guardrails-into-the-ai-gateway.md) |
| Unauthorized tool invocation | The effective permission is the intersection of the agent's declared tools, the caller's groups and the tool policy; the mcp-gateway shows and allows only that set | [ADR-0011](../adr/0011-define-tool-authorization-as-policy-intersection.md) |
| Cross-agent and cross-user data leakage | Groups drive agent visibility and object-level authorisation; the RAG filter is fail-closed on the caller's groups | [ADR-0583](../adr/0583-require-group-visibility-and-object-level-authorisation-before-per-agent-entries.md), [ADR-0568](../adr/0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md) |
| SaaS context leakage | Data classification (C1 to C3) can only be raised; C3 stays on local models; signed markers on tool results | [ADR-0565](../adr/0565-derive-data-classification-from-okf-and-only-allow-raising-it.md), [ADR-0594](../adr/0594-give-the-three-experiences-the-same-mcp-tools-behind-signed-classification-markers.md) |
| Excessive agent delegation | Delegation only to targets an agent declares, depth and cycle limits, human approval of writes | [ADR-0401](../adr/0401-introduce-agent-delegation-limited-to-targets-an-agent-declares.md), [ADR-0406](../adr/0406-limit-agent-delegation-by-depth-cycle-and-budget.md) |
| A compromised or misbehaving agent | Lifecycle states, roles and incident revocation of one agent | [ADR-0584](../adr/0584-define-agent-lifecycle-states-roles-and-incident-revocation.md), [revocation runbook](../platform/agent-revocation-runbook.md) |
| Tampered images or agent releases | Keyless signatures verified by digest and identity; admission refuses an unsigned image | [supply chain architecture](../architecture/supply-chain-architecture.md) |

## The trust-boundary findings of 2026-11-06 (C1 to C10)

Each finding has its attacker, its asset and the clause that closes it. The state of a work package is read from the
[tracker](../roadmap/implementation-roadmap.md) on 2026-11-19; ADR-0602 itself is `Accepted`, and the hardened profile that bundles the
settings (WP-227) is not started.

| # | Asset | Attacker and attack | Closed by | Work package state |
|---|---|---|---|---|
| C1 | Every secret in Vault | Anyone who can `get secret` in `zuno-vault` or read an etcd backup: the unseal key and root token sat together in a cluster Secret | Clause 1: AWS KMS auto-unseal, root token used once, Kubernetes-auth roles ([Vault migration](../platform/vault-kms-raft-migration.md)) | WP-223 Done |
| C2 | Keycloak admin, database roots, OIDC secrets | Whoever may create an `ExternalSecret` anywhere: one `ClusterSecretStore` read all of `zuno/data/*` | Clause 2: one `SecretStore` per namespace, each with its own Vault role | WP-223 Done |
| C5 | Every account and database | One leaked or guessed shared password; no brute-force protection | Clause 3: security profiles (`demo`, `hardened`), brute-force detection in the realm | WP-223 Done |
| C3 | Service-to-service traffic | A plaintext caller: the mesh issued identities and enforced none | Clause 4: `PeerAuthentication` STRICT on the namespaces that hold the platform's secrets ([service mesh scenario](../demo/scenarios/foundation/service-mesh-kiali.md)) | WP-224 Operator pending |
| C4 | The cluster | A merge to `main` or a tampered chart in transit, with Argo CD at cluster-admin | Clause 5: the single `*/*` AppProject split in three (`zuno-platform`, `zuno-apps`, `zuno-bootstrap`), `check_app_projects.py`, GitHub settings on `main` | WP-224 Operator pending |
| C6 | The gateways | A token minted for another client (`aap`, `openshift`) replayed against the ai-gateway or mcp-gateway | Clause 6: audience and issuer checked | WP-222 Done, WP-224 Operator pending |
| C7 | The prompts the model reads | Indirect injection planted in a Confluence page or a crawled web page, read as a tool result and never inspected; a detector outage lets a request through | Clause 8: tool results and RAG text scanned before the model, fail-closed for classes C2 and above in block mode, streamed replies buffered or cut | WP-225 Done |
| C8 | The token budget | An API key on the `/v1/messages` and `/v1/responses` paths consumes without a ceiling | Clause 9: those paths are metered, not blocked | WP-225 Done |
| C9 | Each user's own scope | Confused deputy: shared-credential servers (Confluence, Salesforce, git forge) act beyond the caller's scope, a logging server can replay the bearer | Clause 10: shared-credential servers check the caller's groups against a space, repository or object | WP-225 Done |
| C10 | The C3 content | C3 labelled C1 by the caller reaches a SaaS model | Clause 11: ADR-0565 and the signed markers | ADR-0565 Implemented |

The medium findings M1 to M44 (egress rules, database TLS in the mesh, certificate verification, admin routes, supply-chain hygiene) are
listed in [ADR-0603](../adr/0603-close-the-medium-severity-security-gaps-found-in-the-2026-11-06-review.md), delivered by WP-222 to WP-226.
The three live items still waiting for the owner's window are in [ADR-0613](../adr/0613-close-the-three-remaining-live-hardening-items-of-adr-0603-in-mid-december.md).

## What this page does not say

It does not claim the platform is hardened: the demo profile keeps the permissive behaviour on purpose, and clause 12 (the hardened profile)
has not been rehearsed. When a row above says Done it means the repository work landed and the cited proofs ran, as the work package records
them; read the work package for what was and was not proven live.
