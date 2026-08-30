# ADR-0528: Re-key project binding, quota and telemetry onto the Zuno project id

- **Status:** Implemented (2026-08-30) - WP-090 landed all four Decision clauses: `salesforce_opportunity_id`/`salesforce_verified_at` on the project with verification moved to `POST`/`PUT /v1/projects` under the editing admin's own identity (`project_binding.verify_project_binding` itself unchanged, its three distinguishable causes intact); `_require_customer_project` replacing the per-conversation `_bind_project_if_required`, so a `project_required` task refuses a free project (403) or no project (400) and re-verifies once per project per validity window rather than once per conversation; the `task.project_required` gate removed from all seven `X-Zuno-Project-Id` call sites, the guarantee now resting on ADR-0527's server-resolved id rather than a frontmatter mark; and `zuno.project_id` added as a span attribute - never a metric label - to ai-gateway's `model_call` span (both the non-streaming and the streaming path), agent-runtime's `graph_run`/`api_request` spans and agent-bff's `bff_request` span, carried to the BFF on the SSE `start` event and on `ChatResponse`. A negative test asserts no Salesforce identifier reaches any outgoing header, and `zuno.project_id`'s presence is now itself regression-tested in all three services (2026-08-30 - it had been proven live but unguarded, see below). The `policies/tools/tool-policy.yaml` decision was recorded 2026-08-29: no change to `finance`'s `allowed_groups`.

  **Deliberately not gating `Implemented`:** the live Salesforce three-cause pass (404/403/503 against a real opportunity) remains blocked on the standing WP-22/WP-33 sandbox credential gap ADR-0512 already carried, and that gap has no repo-side fix - `ansible/roles/vault/tasks/install.yml` only seeds `zuno/salesforce/technical` when real (non-placeholder) credentials are supplied, and none exist in this cluster. Rather than leave this ADR indefinitely short of `Implemented` for a precondition this repo cannot satisfy, the credential provisioning and its confirming live pass are carved out to [WP-101](../roadmap/work-packages/wp-101-salesforce-sandbox-credentials.md), targeted at v0.7 alongside the already-deferred `fetch-salesforce` cadence (ADR-0218). All four Decision clauses and every acceptance criterion that this repo can independently verify are met: `project_binding.verify_project_binding`'s cause taxonomy is exercised by fixture tests (mocked Salesforce responses, not a live org), and the fail-closed/fail-open behavior for each of the three causes is unit-tested exactly as it was before this ADR - only the outer live-org confirmation is deferred.
- **Target:** v0.4
- **Date:** 2026-08-27
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0512](0512-introduce-project-bound-tasks-with-salesforce-verified-context.md) clause 3 (where and when the Salesforce binding is verified, and what `conversations.project_id` holds) and the quota/observability keying of its clause 4. Clauses 1 and 2 - the `zuno.project_required` frontmatter mark and prompt-side collection - stand unchanged, as does clause 4's requirement that a verified binding activate the project's quota and scope `knowledge.project` retrieval.

## Context

ADR-0512 made a project-bound task refuse to act until a project was verified,
and chose the Salesforce opportunity as both the verification oracle and the
project's identity: `components/agent-runtime/app/project_binding.py` resolves a
candidate through `salesforce.opportunity.read` under the caller's own identity
at conversation start, and the verified **Salesforce id** is what lands in
`conversations.project_id` and what leaves the runtime as `X-Zuno-Project-Id`
for the ADR-0511 quota ledger.

That conflation has three costs. Work that is not a Salesforce opportunity -
internal engineering, a pre-sales exploration, an evaluation - cannot carry a
project at all, so it draws no project quota and appears nowhere in any project
view. The verification is per-conversation, so its latency and its failure modes
sit on the conversation-start path, once per conversation and per validity
window, for what is a property of the engagement rather than of the chat. And
the guard that keeps the header honest is the task's own `project_required`
mark: `app/clients/model_router.py` sets `X-Zuno-Project-Id` only when the task
is marked, precisely because `state["project_id"]` is otherwise a client
assertion and a caller could shift consumption onto an arbitrary project's
budget. That guard works, but it buys its safety by making the project dimension
invisible for every unmarked task.

Meanwhile the project identity reaches the quota ledger but **never the
telemetry**: no span in `agent-runtime`, `ai-gateway`, `mcp-gateway` or
`agent-bff` carries a project attribute today. ADR-0029's cost and trace
instrumentation can attribute a model call to a user, a group, an agent and a
run, but not to an engagement.

ADR-0527 removes the premise this all rested on. A project is now a real,
server-created object with a server-verified membership, and `project_id` is
minted by the platform rather than asserted by the client.

## Decision

### 1. The Salesforce link is an optional attribute of the project

`projects.salesforce_opportunity_id` (with its `salesforce_verified_at`
companion, ADR-0527) records an optional link to a Salesforce opportunity. A
project that has one is a **customer project**; a project that has none is a
**free project**. Both are first-class: a free project has a title, a context,
grants, conversations, durable memory and a quota bucket exactly like a customer
project.

The Salesforce id is never the project's identity. `project_id` stays a
server-minted UUID, and the opportunity id is returned by the API only to a
project `admin`, never emitted in a header and never set as a span attribute.

### 2. Verification moves to project create and update

`project_binding.verify_project_binding()` is retained unchanged - the same
`salesforce.opportunity.read` call through the MCP Gateway under the caller's
own identity (ADR-0013/ADR-0032), never routed through `tool_call_node` so the
record never reaches the model's context, with the same three distinguishable
causes mapped to 404 (unknown project), 403 (no access) and 503 (Salesforce
unreachable). What changes is **when** it runs: at `POST`/`PUT /v1/projects`,
under the identity of the admin setting the link, and again on the project when
`project_binding.is_binding_still_valid()` finds the stamp older than
`policies/quotas/quota-policy.yaml`'s `project_binding.validity_window`.

The verification therefore lands once per project per window rather than once
per conversation per window - which is what ADR-0512's own Operational
considerations wanted ("latency lands once per conversation, not per turn"),
taken one level further now that a project outlives a conversation. Saving a
project with an unverifiable link fails closed: the link is rejected, the
project is not saved with it, and the three causes remain distinguishable.

### 3. `project_required` means "a customer project"

A task marked `zuno.project_required` now requires the conversation to belong to
a project whose Salesforce link is present and currently valid. A conversation
in a free project, or in no project, is refused before any tool call, retrieval
or model action, exactly as ADR-0512 clause 2 requires - the enforcement point
moves, the fail-closed posture does not. `components/agent-runtime/app/main.py`'s
per-conversation `_bind_project_if_required` is replaced by a check against the
conversation's own project, which re-verifies only when the stamp has aged out.

### 4. Quota and telemetry key on the Zuno project id, for every project

`X-Zuno-Project-Id` carries the Zuno `project_id` and is emitted for **any**
conversation that belongs to a project, customer or free. The guard that made
the old header trustworthy is not removed but replaced by a stronger one: the
id is no longer gated on the task's `project_required` mark because it is no
longer client-assertable at all - ADR-0527 has the runtime resolve it from the
conversation's own `projects` row after verifying the caller holds a grant.
Database-verified membership is strictly stronger than a frontmatter mark, and
it closes the same abuse channel for a wider population.

ADR-0511's precedence is unchanged and now simply applies to more work:
consumption inside a project draws the project's budget first, the user's next,
with the group as the outer ceiling.

A new **`zuno.project_id` span attribute** is set beside the existing
`zuno.run_id` on `ai-gateway`'s model-call span, `agent-runtime`'s graph-run and
API-request spans, and `agent-bff`'s request span. It is a span attribute only,
never a metric label - the same unbounded-cardinality reasoning ADR-0029's
instrumentation already applies to `run_id`. The Salesforce opportunity id is
emitted nowhere.

## Consequences

Every kind of work becomes attributable. Cost, latency and traces can be joined
by engagement across agents for the first time, and a project's quota stops
being reachable only by Salesforce-backed Finage tasks. The Salesforce
integration narrows to what it is genuinely good at - proving that an
engagement exists and that this user may see it - and stops being the platform's
project registry. The conversation-start path loses an outbound MCP call.
ADR-0512's known live gap (`salesforce.opportunity.read` is granted to
`sales`/`board` but not to Finage's `finance` group) becomes narrower in blast
radius: it now blocks only the setting of a customer link, not the ability to
work in a project at all.

## Security considerations

Verification under the caller's own identity remains the point, and moves with
the check: a user who cannot read the opportunity in Salesforce cannot attach it
to a project, so a customer project can never be conjured by name-guessing. The
binding is still stored as an id plus a verification timestamp, never record
content, and the project row gains no Salesforce business data.

Emitting `X-Zuno-Project-Id` for more conversations is safe only because
ADR-0527 made the id server-resolved; that dependency is load-bearing and must
not be relaxed. If the resolution were ever weakened back to a client-supplied
field, this decision would reopen the quota-shifting channel ADR-0512's mark was
protecting against.

Re-verification on a validity window still bounds how long revoked Salesforce
access lingers, now on the project rather than on each conversation - a wider
blast radius per stale stamp, but a single place to invalidate. Attaching the
project id to spans exports an engagement identifier into the trace backend;
it is an opaque UUID, and no Salesforce identifier or business content
accompanies it.

## Operational considerations

Salesforce latency and failures leave the chat path entirely: they surface at
project save, where a human is waiting on a form and the three causes are
directly reportable, and on the periodic re-verification. Verification failures
remain observable per cause so a Salesforce outage stays distinguishable from an
authorization denial. `project_binding.validity_window` keeps its name and its
home beside the quota classes, with its scope restated as per-project.

`zuno.project_id` on spans, joined with the existing `zuno.run_id`, gives
per-engagement cost and latency views without a schema change to the metrics
pipeline; dashboards that need per-project aggregates must build them from
traces, not from counters, for the cardinality reason above.

## Acceptance criteria

- A project admin sets a Salesforce opportunity on a project; it is verified
  under their identity and the project reports as a customer project. An
  unverifiable id is refused with a cause-distinguished error and the project is
  not saved with it.
- A project with no Salesforce link is fully usable - conversations, memory,
  grants - and draws its own project quota.
- A `project_required` Finage task refuses to act in a free project or in no
  project, and proceeds in a customer project whose stamp is valid; a stale
  stamp triggers exactly one re-verification.
- Starting a conversation in a customer project makes no Salesforce call when
  the project's stamp is fresh.
- A model call made inside any project carries `X-Zuno-Project-Id` with the Zuno
  `project_id` and draws down the project budget first; the Salesforce id
  appears in no header and in no span.
- `zuno.project_id` is present on the ai-gateway model-call span, the
  agent-runtime graph-run span and the agent-bff request span for the same turn,
  joinable on `zuno.run_id`.
- Automated tests cover the header's contents (including a negative assertion
  that no Salesforce identifier is present), the removal of the
  `project_required` gate, and the customer-project requirement's fail-closed
  refusals.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0013](0013-propagate-end-user-identity-through-agent-calls.md)
- [ADR-0029](0029-instrument-model-usage-costs-and-distributed-traces.md)
- [ADR-0032](0032-propagate-trusted-identity-end-to-end.md)
- [ADR-0036](0036-enforce-the-complete-mcp-authorization-intersection-in-the-gateway.md)
- [ADR-0206](0206-separate-current-salesforce-knowledge-from-legacy-sxa.md)
- [ADR-0209](0209-introduce-project-scoped-agent-memory.md)
- [ADR-0212](0212-introduce-persistent-navigable-chat-conversations.md)
- [ADR-0503](0503-make-each-okf-bundle-state-its-complete-authorization-contract.md)
- [ADR-0511](0511-define-okf-quota-policy-enforced-via-kuadrant.md)
- [ADR-0512](0512-introduce-project-bound-tasks-with-salesforce-verified-context.md) (clause 3 superseded by this ADR)
- [ADR-0515](0515-per-conversation-tabs-one-browser-tab-per-agent.md)
- [ADR-0527](0527-introduce-the-project-as-the-sharing-and-context-boundary.md)
