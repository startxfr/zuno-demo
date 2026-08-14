# WP-20: Logical knowledge domains and the knowledge policy

- **State:** Done (2026-08-15 — Part A merged: `knowledge/` domain descriptors (tech/sales/sxa-legacy/adv) + `knowledge/metadata-schema.yaml` + `platform/docs/check_knowledge_refs.py`, wired blocking in `.github/workflows/lint.yml`. Part B merged: `policies/knowledge/knowledge-policy.yaml` + README; `zuno.allowed_knowledge` added to the task OKF schema and declared on Tekos's `answer-technical-question`/`find-relevant-docs` tasks (`knowledge.tech`); `components/agent-runtime/app/knowledge.py` (`KnowledgePolicyStore` + `evaluate_knowledge()`) enforces the fail-closed ADR-0203 intersection in `retrieve_node` before every rag-service call; rag-service gained an additive `domains`/`technology` filter in `app/search.py`/`app/ogx_provider.py`/`app/schemas.py` as defense in depth (parity maintained between both providers). Both ADR-0202 and ADR-0203 now Implemented.)
- **ADRs:** ADR-0202, ADR-0203 (To be implemented -> Implemented)
- **Depends on:** WP-00 (done)
- **Blocks:** WP-21, WP-22, WP-23, WP-24, WP-25, WP-28, and all Phase 3 agent slices
- **Estimated files touched:** Part A ~7, Part B ~8 (two separate PRs)

> Execute this brief as a standalone task from the repository root. It is the
> spine of the v0.2 knowledge stack: Part A (ADR-0202) defines the domains,
> Part B (ADR-0203) enforces authorization over them. Land Part A first.

## Goal

Introduce the four logical knowledge-domain identifiers as a declarative,
validated repo contract (`knowledge/` descriptors + chunk-metadata schema),
then enforce knowledge access as a fail-closed policy intersection with a
new `zuno.allowed_knowledge` OKF task field and a GitOps-managed knowledge
policy file.

## ADR references

Primary:
- [docs/adr/0202-introduce-logical-knowledge-domains.md](../../adr/0202-introduce-logical-knowledge-domains.md)
- [docs/adr/0203-enforce-knowledge-authorization-as-policy-intersection.md](../../adr/0203-enforce-knowledge-authorization-as-policy-intersection.md)

ADR-0202 acceptance criteria: agent/task defs reference `knowledge.tech`, `knowledge.sales`, `knowledge.sxa-legacy`, `knowledge.adv` without physical endpoint/DB identifiers; one canonical `technology` filters web + Confluence chunks; validation rejects unknown domain refs; no new profile store duplicates Keycloak roles or OKF capabilities.

ADR-0203 acceptance criteria: `allowed_knowledge` is declared independently of `allowed_tools`; `knowledge.sales` doesn't grant `knowledge.sxa-legacy` without both agent ceiling and platform/user policy allowing it; entitlement without the required role is denied, and the reverse stays denied via the existing BFF/agent boundary; ACL-restricted chunks stay invisible when groups don't intersect `acl_groups`.

Key constraints: descriptors carry no physical DB names/endpoints/secrets; the intersection is agent declaration ∩ task `allowed_knowledge` ∩ user business-role rights ∩ document ACL/classification ∩ platform knowledge policy, fail closed on any missing factor; the agent declaration is a ceiling a task may narrow but never widen.

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- Read: `policies/tools/tool-policy.yaml` (the structural template — the
  knowledge policy must be "analogous" to it, including its five-factor
  commentary style), `agents/tekos/agent.okf.md` + `agents/tekos/tasks/*.md`
  (where `allowed_knowledge` will live), `components/rag-service/app/search.py`
  (the existing `acl_groups` `?|` intersection filter and where domain
  filtering hooks in), `components/agent-runtime/app/` (where task
  declarations are parsed/enforced), ADR-0202's metadata field lists.

## Part A — repo changes (ADR-0202)

1. **Create `knowledge/`** at repo root with one descriptor per domain:
   `knowledge/tech/domain.yaml`, `knowledge/sales/domain.yaml`,
   `knowledge/sxa-legacy/domain.yaml`, `knowledge/adv/domain.yaml`, plus
   `knowledge/README.md`. Each descriptor declares: domain ID, taxonomy,
   source classes, freshness objective, classification defaults, policy
   references. NO physical endpoints/DB names/secrets.
2. **Metadata schema:** `knowledge/metadata-schema.yaml` defining the common
   chunk metadata (`domain`, `source`, `source_type`, `language`,
   `classification`, `acl_groups`, `provenance`, `source_modified_at`,
   `indexed_at`, `stale_after`) and the per-domain extensions from the ADR
   (tech: `technology` canonical key, `product`, `version`, optional
   `skill_scope`; sales: `deal_type`, customer/opportunity/business-unit/
   status/year; sxa-legacy: schema/table/column/relationship/record-type/
   date/customer/project; adv: `project_type`, project/customer/status/
   owner/business-unit/date).
3. **Validator:** `platform/docs/check_knowledge_refs.py` (mirroring
   `check_docs.py`'s structure and output format) that (a) validates
   descriptor files against the schema, (b) scans `agents/**` and
   `policies/**` for `knowledge.` references and fails on any not defined in
   `knowledge/`; wire it into `.github/workflows/lint.yml` as blocking.
4. **Canonical `technology` vocabulary:** record in `knowledge/tech/domain.yaml`
   the canonical values already used by ADR-0330's ingestion
   (satellite, openshift, openshift-ai, keycloak) so web + Confluence chunks
   share one vocabulary.

## Part B — repo changes (ADR-0203)

5. **Knowledge policy:** create `policies/knowledge/knowledge-policy.yaml`
   analogous to `policies/tools/tool-policy.yaml` (same commented five-factor
   intersection explanation, adapted): map each logical domain to allowed
   business roles, classification constraints, optional source restrictions.
   Add `policies/knowledge/README.md`.
6. **OKF contract:** add `zuno.allowed_knowledge` to the task front-matter
   contract; declare it for Tekos (`knowledge.tech` on its existing tasks)
   and the agent-level ceiling in `agents/tekos/agent.okf.md`, following how
   `allowed_tools`-equivalent declarations are structured there today.
7. **Enforcement:** implement the fail-closed intersection where retrieval
   is invoked (Agent Runtime request to rag-service, and rag-service's own
   filter as defense in depth): missing task declaration, unknown domain,
   missing user groups, missing policy entry, or untrusted ACL metadata all
   deny. Reuse the existing `acl_groups` filter in
   `components/rag-service/app/search.py`; add the domain + role + policy
   factors around it.
8. **Tests:** one per ADR-0203 acceptance bullet, as unit tests in
   `components/agent-runtime/tests/` and/or `components/rag-service/tests/`
   (the entitlement-without-role and role-without-entitlement cases can be
   asserted at the policy-evaluation function level).

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set.
- Physical DB provisioning/bindings (WP-21 / ADR-0204 owns them).
- `policies/tools/tool-policy.yaml` semantics (touch only if adding parallel
  commentary links).
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `python3 platform/docs/check_knowledge_refs.py` (exit 0; then prove it
  fails on a deliberately unknown `knowledge.bogus` reference in a scratch
  file, and remove the scratch file)
- `python3 -m pytest components/rag-service/tests/ components/agent-runtime/tests/ -q`
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`
- `! grep -rn "postgresql\|svc.cluster.local" knowledge/` (no physical identifiers)

## Operator / human follow-up

None — both ADRs are repo-provable. (Cross-domain behavior on live data gets
exercised again by the Phase 3 agent slices.)

## Status updates (then re-run check_docs.py)

- After Part A merge: ADR-0202 →
  `Implemented - see \`knowledge/\`, \`platform/docs/check_knowledge_refs.py\`.`;
  index row `Implemented`; tracker updated.
- After Part B merge: ADR-0203 →
  `Implemented - see \`policies/knowledge/\`, \`components/rag-service/app/search.py\`.`;
  index row `Implemented`; tracker → `Done`; this file's State; MEMORY.md
  dated bullet.

## Out of scope / deferred

- `knowledge.project` (fifth domain) — WP-28 / ADR-0209.
- Physical bindings + per-domain databases — WP-21 / ADR-0204.
- Freshness enforcement (`stale_after` behavior) — WP-24 / ADR-0205.
