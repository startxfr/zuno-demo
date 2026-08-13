# ADR-0038: Use standards-compliant OKF v0.2 Markdown bundles

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The current `agents/tekos/agent.okf.yaml` uses a Kubernetes-style `apiVersion/kind/metadata/spec` document. The project decision is to use Open Knowledge Format v0.2 as the portable knowledge/agent description basis. OKF v0.2 is document-oriented and supports Markdown files with YAML frontmatter plus extensible producer-defined metadata.

## Decision

Represent every agent as an OKF v0.2 Markdown bundle. Use standard OKF fields for type, title, description, provenance, verification, freshness and sources, and place Zuno-specific runtime metadata under a clearly namespaced `zuno` extension. Tasks, prompts, knowledge references and policies should be individual Markdown documents linked from an agent index.

## Consequences

Agent definitions become human-readable in GitHub, closer to the upstream OKF model, easier to sign/review and directly ingestible as knowledge. Existing YAML agent definitions require migration.

## Security considerations

Do not place secrets, tokens or sensitive runtime values in OKF bundles. Provenance and classification metadata must be preserved across ingestion.

## Operational considerations

Create a migration tool or validation step that rejects the legacy pseudo-OKF form once all v0 agents have migrated.

## Implementation state

**Implemented (2026-08-05).**

- Every `agents/<name>/agent.okf.yaml` is replaced by `agents/<name>/agent.okf.md`: a YAML frontmatter block (OKF core fields `okf_version`, `type`, `title`, `description`, `provenance`, `verification`, `freshness`, `sources`, plus the Zuno extension namespaced under `zuno`) followed by a Markdown body. Tasks are individual linked documents under `agents/<name>/tasks/<task>.md`, referenced from the index's `zuno.tasks` list; Tekos additionally has `agents/tekos/prompts/answer-technical-question.md` (used by ADR-0039). Two new schemas: `platform/okf/schema/zuno-okf-v0.2.schema.json` (rewritten) and `zuno-okf-task-v0.2.schema.json` (new); a third, `zuno-okf-prompt-v0.2.schema.json`, covers prompt documents.
- Every consumer of the old format was migrated to parse frontmatter instead (the same small split-on-`---`/`yaml.safe_load` logic, independently duplicated per this repo's convention rather than shared): `components/agent-frontend/internal/okf/okf.go` (the portal), `components/agent-runtime/app/registry.py` (new, ADR-0039), `components/mcp-gateway/app/agent_declarations.py` (new, ADR-0036), and `ansible/roles/agents/tasks/check.yml`'s structural validator. All three services now bake `agents/` into their image at build time from a repository-root Docker build context.
- The old `agent.okf.yaml` files are deleted, not merely superseded - there is no fallback path reading the old format, so a stray legacy file would be invisible to every loader (`LoadAll`/`AgentRegistry`/`AgentDeclarationStore` all glob for `agent.okf.md` specifically).
- No secrets or sensitive runtime values are placed in these bundles - they carry only descriptive/config metadata already public in this repository.

## Evolution (2026-08-13)

ADR-0333 and ADR-0334 extend the Zuno OKF contract with logical knowledge-domain declarations and task-level `allowed_knowledge`. OKF remains the declarative catalogue of what an agent/task may use; no parallel `AIProfile` or capability-bundle configuration is introduced. Physical vector databases, services and endpoints remain outside OKF and are resolved through platform bindings.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0005](0005-use-okf-v0-2-as-the-declarative-agent-definition-contract.md)
- [ADR-0006](0006-extend-okf-with-zuno-agent-specific-metadata.md)
- ADR-0106
- ADR-0109
