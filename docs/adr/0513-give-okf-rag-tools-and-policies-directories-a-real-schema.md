# ADR-0513: Give OKF rag/, tools/ and policies/ directories a real schema

- **Status:** Implemented - see `platform/okf/schema/zuno-okf-{rag,tool,policy}-v0.2.schema.json`, `platform/supply-chain/validate_okf_bundle.py` and `agents/tekos/{rag,tools,policies}/` (WP-56, 2026-08-19)
- **Target:** OKF v0.1
- **Date:** 2026-08-19
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0502 classifies `agents/<name>/rag/`, `tools/` and `policies/` as
legacy full-skeleton stubs: "Empty stub directories are not Stage 2 - they
are drift", and names only `deployment/` (ADR-0503) and `tests/`
(ADR-0504) as directories that gain real content at promotion. Consistent
with that, nothing in the codebase reads these three directories today -
not Agent Runtime's `AgentRegistry`, not MCP Gateway's declaration check,
not `validate_okf_bundle.py` - and every agent that has them (Tekos,
Arkos, Comage, Advantage, Finage) carries only a three-line placeholder
README in each. The actual authorization contract these directory names
suggest already lives elsewhere and is already complete: RAG retrieval
tuning in `agent.okf.md`'s `zuno.rag.top_k` and each task's
`zuno.allowed_knowledge` (ADR-0202/ADR-0203); tool authorization in each
task's `zuno.allowed_tools` intersected with `policies/tools/tool-policy.yaml`
and `platform/bindings/tools/tool-bindings.yaml` (ADR-0011/ADR-0116);
platform-wide constraints in the root `policies/*/` tree.

That completeness is exactly why these three directories have stayed
empty: there is no missing *authorization* for them to hold. What is
missing is the human-readable, per-agent, per-item documentation layer
ADR-0503 already established a precedent for with the generated
Authorization matrix - "an agent review reads one generated section
instead of joining five files" - but scoped one level finer, to a single
knowledge domain, a single tool or a single extra constraint, rather than
the whole bundle at once.

## Decision

1. **`rag/`, `tools/` and `policies/` become real Stage-2 content**,
   alongside `deployment/` and `tests/`, amending ADR-0502's clause 1
   accordingly. Each holds one Markdown file per item (ADR-0038's existing
   `tasks/<task>.md` granularity), validated against a new schema in
   `platform/okf/schema/`:
   - `agents/<name>/rag/<domain>.md` - `zuno-okf-rag-v0.2.schema.json`.
     Documents retrieval tuning for one knowledge domain this agent's
     tasks already declare in `allowed_knowledge`.
   - `agents/<name>/tools/<capability>.md` - `zuno-okf-tool-v0.2.schema.json`.
     Documents usage of one tool/capability this agent's tasks already
     declare in `allowed_tools`.
   - `agents/<name>/policies/<name>.md` - `zuno-okf-policy-v0.2.schema.json`.
     Documents one additional, agent-specific constraint that narrows -
     never widens - the platform policy floor.

2. **Every field is documentation, never a second source of authority.**
   Each schema requires a `used_by_tasks` (rag/tool) or `applies_to.tasks`
   (policy) cross-reference back to the task frontmatter that already
   declares the domain/tool, and the policy schema requires an explicit
   `narrows_platform_policy: true` acknowledgment. This mirrors ADR-0503's
   own rule for the Authorization matrix almost verbatim: these documents
   must never become an enforcement input, only a legible record of what
   the actual sources (`agent.okf.md`, `tasks/*.md`, root `policies/*/`)
   already say.

3. **`validate_okf_bundle.py` gains a third check** alongside its existing
   schema-validity and policy-validity checks: for every `*.md` under a
   bundle's `rag/`, `tools/`, `policies/`, its `okf_version`/`type` are
   correct and its cross-reference (`domain`+`used_by_tasks`,
   `capability`+`used_by_tasks`, or `applies_to.tasks`) resolves against
   tasks the bundle actually declares. A dangling reference (a domain,
   tool or task that does not exist in this bundle) fails the same
   lint-chain job the existing checks already run in
   (`.github/workflows/lint.yml`).

4. **Population is promotion-time work, per agent, like `tests/` content**
   (ADR-0504 clause 4). This ADR and WP-56 populate Tekos only - the sole
   Stage-2 agent today - as the worked example; Arkos, Comage, Advantage
   and Finage keep their reserved-but-still-stub structure (ADR-0502
   clause 4) until each is promoted, at which point filling `rag/`,
   `tools/`, `policies/` per this schema joins `deployment/`/`tests/` as
   a promotion-checklist step (`platform/templates/agent/PROMOTION.md`).

## Consequences

The four remaining full-skeleton agents' `rag/`, `tools/`, `policies/`
directories stop being unexplained dead weight without becoming a second,
divergent source of truth: the schema exists, but nothing is required to
populate it before promotion. A future maintainer asking "why does Tekos
recommend `web_search` this way" or "what does Tekos actually retrieve
`knowledge.tech` for" reads one small file instead of re-deriving it from
`agent.okf.md` and three task files. `platform/templates/agent/PROMOTION.md`
gains one more per-directory line at its Stage-2 growth step, matching how
it already names `deployment/`/`tests/`.

## Security considerations

Because these documents can never grant, widen or override anything (rule
2 above; every schema also carries a hard `additionalProperties: false`
ceiling), authoring one changes nothing about what a caller can actually
do. `validate_okf_bundle.py`'s new check runs against already-committed,
already-reviewed files - no new secrets, network calls or credentials are
introduced. The `narrows_platform_policy: true` guardrail in
`zuno-okf-policy-v0.2.schema.json` exists specifically so a reviewer
cannot mistake a per-agent policy note for a grant: the field is a
required `const true`, so a widening claim has no schema-legal way to be
expressed here.

## Operational considerations

The new validator check is colocated with the existing
`validate_okf_bundle.py` checks in `.github/workflows/lint.yml`'s
policy-as-code job - no new CI job, no cluster dependency. Runtime is file
parsing only, identical in cost to the checks it extends.

## Acceptance criteria

- `platform/okf/schema/zuno-okf-{rag,tool,policy}-v0.2.schema.json` exist,
  validate as JSON Schema draft 2020-12, and follow the same
  `$id`/`additionalProperties: false`/ADR-citing-description conventions
  as the three existing OKF schemas.
- `agents/tekos/{rag,tools,policies}/` each hold real, schema-conformant
  content instead of the three-line stub README (README kept as a short
  index, matching `agents/tekos/tasks/README.md`'s existing pattern);
  `agents/tekos/README.md`'s directory-tree annotation for these three
  lines is updated to match.
- `python3 platform/supply-chain/validate_okf_bundle.py` passes for all
  eight bundles and fails closed on a deliberately broken cross-reference
  tested by hand.
- `python3 platform/docs/check_docs.py` passes.

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md)
- [ADR-0038](0038-use-standards-compliant-okf-v0-2-markdown-bundles.md)
- [ADR-0116](0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md)
- [ADR-0202](0202-introduce-logical-knowledge-domains.md)
- [ADR-0203](0203-enforce-knowledge-authorization-as-policy-intersection.md)
- [ADR-0502](0502-formalize-the-two-stage-agent-maturity-model.md)
- [ADR-0503](0503-make-each-okf-bundle-state-its-complete-authorization-contract.md)
- [ADR-0504](0504-define-the-agent-tests-directory-structure-and-promotion-gate.md)
