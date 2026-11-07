# WP-225: AI and agent surface: guardrails, metering, delegated scope (delivers ADR-0602, ADR-0603)

- **State:** Not started
- **ADRs:** ADR-0602, ADR-0603, ADR-0565
- **Depends on:** WP-222, WP-209 (classification floor; do not duplicate its work)
- **Blocks:** WP-227
- **Estimated files touched:** ~20

> Execute this brief as a standalone task from the repository root.

## Goal

Make the guardrails enforce (C7), meter the Anthropic-format paths (C8), and stop shared service identities acting beyond
the caller's scope (C9, M12 to M15).

## ADR references

ADR-0602 clauses 8 to 11; ADR-0603 clause 3. Classification (C10) belongs to ADR-0565 and WP-209.

## Preconditions

- Re-read `components/ai-gateway/app/guardrails.py` and `main.py` (`_observed_stream`), `guardrails-policy.yaml` in
  zuno-demo-agents, `components/mcp-gateway/app/downstream.py`, `components/mcp-servers/*`.
- Read `docs/roadmap/work-packages/wp-220-*.md` and the quota notes first: `/v1/messages` stays open.

## Repo changes

1. Guardrails: `block` fails closed for C2 and above; tool and RAG text scanned; streams buffered or cut on detection;
   model-based classifier added to the regular expressions.
2. Metering: per-key token ceiling on `/v1/messages` and `/v1/responses`, in the ai-gateway or by a Limitador data-extraction
   rule.
3. Scope: space, repository and recipient allowlists in the Confluence, git-forge and email servers, from signed context;
   Salesforce owner scoping; namespace matcher injected into the Kubernetes metrics query.
4. mcp-gateway: token exchange or a signed per-call assertion instead of forwarding the bearer; the same entitlement check on
   the REST path as on `/mcp`; authenticated callers for Dify and the token proxy; signed delegation chain headers in a2a-gateway.
5. Metrics: drop the per-user label; bound JSON-RPC batch size; rate-limit the AAP audit launch.

## Verification

Negative tests for each: an injected tool result is flagged and blocked; a detector outage blocks a C2 request; a request
past the key ceiling on `/v1/messages` is refused; a space outside the caller's group is refused.
