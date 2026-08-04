# ADR-0038: Use standards-compliant OKF v0.2 Markdown bundles

- **Status:** To be implemented
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

This ADR records an agreed architectural change identified during the 2026-08-05 repository review. **No implementation is claimed by this ADR.** The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.

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
