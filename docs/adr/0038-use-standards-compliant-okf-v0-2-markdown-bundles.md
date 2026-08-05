# ADR-0038: Use standards-compliant OKF v0.2 Markdown bundles

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The current `agents/tekos/agent.okf.yaml` uses a Kubernetes-style `apiVersion/kind/metadata/spec` document. The project decision is to use Open Knowledge Format v0.2 as the portable knowledge/agent description basis. OKF v0.2 is document-oriented and supports Markdown files with YAML frontmatter plus extensible producer-defined metadata.

## Decision

Represent every agent as an OKF v0.2 Markdown bundle. Use standard OKF fields for type, title, description, provenance, verification, freshness and sources, and place Zuno-specific runtime metadata under a clearly namespaced `zuno` extension. Tasks, prompts, knowledge references and policies should be individual Markdown documents linked from an agent index.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

Agent definitions become human-readable in GitHub, closer to the upstream OKF model, easier to sign/review and directly ingestible as knowledge. Existing YAML agent definitions require migration.

## Security considerations

Do not place secrets, tokens or sensitive runtime values in OKF bundles. Provenance and classification metadata must be preserved across ingestion.

## Operational considerations

Create a migration tool or validation step that rejects the legacy pseudo-OKF form once all v0 agents have migrated.

## Implementation state

**Implemented (2026-08-05).** Every `agents/<name>/agent.okf.yaml` (a
single Kubernetes-style `apiVersion/kind/metadata/spec` document) is
replaced by `agents/<name>/agent.okf.md`: a YAML frontmatter block (OKF
core fields `okf_version`, `type`, `title`, `description`, `provenance`,
`verification`, `freshness`, `sources`, plus the Zuno extension entirely
namespaced under `zuno`) followed by a Markdown body. Tasks are individual
linked documents under `agents/<name>/tasks/<task>.md`, referenced by name
from the index's `zuno.tasks` list; Tekos additionally has a
`agents/tekos/prompts/answer-technical-question.md` prompt document (used
by ADR-0039). Two new schemas formalize this:
`platform/okf/schema/zuno-okf-v0.2.schema.json` (rewritten for the
frontmatter shape) and `platform/okf/schema/zuno-okf-task-v0.2.schema.json`
(new); a third, `zuno-okf-prompt-v0.2.schema.json`, covers prompt
documents.

Every consumer of the old format was migrated to parse frontmatter instead
(the same small "split on `---`, `yaml.safe_load` the middle part" logic,
independently duplicated per this repo's established convention rather
than shared across independently deployed services/tools):
`components/agent-frontend/internal/okf/okf.go` (the portal),
`components/agent-runtime/app/registry.py` (new, ADR-0039),
`components/mcp-gateway/app/agent_declarations.py` (new, ADR-0036), and
`ansible/roles/agents/tasks/check.yml`'s structural validator (Jinja's
`.split('---')`). All three services now bake `agents/` into their image
at build time from a repository-root Docker build context (`agent-runtime`
and `agent-frontend`'s Dockerfiles already did/were changed to this
pattern; `mcp-gateway`'s already did for `policies/`).

Operational consideration ("reject the legacy pseudo-OKF form once all v0
agents have migrated"): the old `agent.okf.yaml` files are deleted, not
merely superseded - there is no fallback path reading the old format, so a
stray legacy file would simply be invisible to every loader (`LoadAll`/
`AgentRegistry`/`AgentDeclarationStore` all glob for `agent.okf.md`
specifically).

No secrets or sensitive runtime values are placed in these bundles
(Security considerations above) - they carry only descriptive/config
metadata already public in this repository (task descriptions, tool
names, classification hints, UI copy).

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0005
- ADR-0006
- ADR-0106
- ADR-0109

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
