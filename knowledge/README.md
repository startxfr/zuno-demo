# Knowledge domains (ADR-0202)

`knowledge/` is the declarative, GitOps-managed contract for Zuno's logical
knowledge domains. It defines **what** knowledge an agent/task can ask for,
never **how** or **where** that knowledge is physically stored.

## Layout

- `knowledge/<domain>/domain.yaml` — one descriptor per logical domain
  (`tech`, `sales`, `sxa-legacy`, `adv`). Declares domain ID, taxonomy,
  source classes, freshness objective, classification defaults and policy
  references.
- `knowledge/metadata-schema.yaml` — the common chunk-metadata contract every
  domain's indexed content carries, plus each domain's own extensions.

## Rules (from ADR-0202)

- A domain descriptor **must never** contain a physical database name,
  service endpoint, secret or credential. Physical backend bindings are
  `platform/bindings/knowledge/bindings.yaml` (ADR-0204, WP-21) — a domain
  descriptor stays valid even if the domain is re-bound to a different
  backend.
- The logical domain ID (`knowledge.tech`, `knowledge.sales`,
  `knowledge.sxa-legacy`, `knowledge.adv`) is the only thing an OKF task or
  the knowledge policy (`policies/knowledge/knowledge-policy.yaml`,
  ADR-0203) ever references.
- A logical domain does not grant access by itself — authorization is
  `policies/knowledge/knowledge-policy.yaml`'s job (ADR-0203); document-level
  ACL/classification metadata remains mandatory regardless of domain.
- `knowledge.tech`'s `technology` field is the one canonical cross-source
  vocabulary official web documentation and internal Confluence both use, so
  a query can filter one `technology` value across both without knowing
  which source produced a given chunk.

## Validation

`platform/docs/check_knowledge_refs.py` (run from the repository root)
validates every descriptor against `metadata-schema.yaml`'s shape and scans
`agents/**` + `policies/**` for `knowledge.*` references, failing on any
reference to a domain not declared here. It is wired as a blocking CI check
(`.github/workflows/lint.yml`), mirroring `platform/docs/check_docs.py`.

## Deferred

- `knowledge.project` (a fifth, per-project domain) — WP-28 / ADR-0209.
- Physical bindings and per-domain databases — WP-21 / ADR-0204.
- `stale_after` enforcement (freshness-driven ranking/live-read routing) —
  WP-24 / ADR-0205.
