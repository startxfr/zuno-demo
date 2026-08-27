# ADR-0417: Consume Codestral via the Mistral API

- **Status:** Implemented (smoke-tested live 2026-08-27 - a real completion returned from
  `api.mistral.ai` (`model_name: codestral-latest`) using the dedicated
  `MISTRAL_CODESTRAL_API_KEY` credential, confirming the model id this ADR could not verify)
- **Target:** v0.4
- **Date:** 2026-08-20
- **Decision owners:** Zuno Demo architecture team

## Context

Codestral is Mistral's code-specialized model - not servable on this
cluster's GPUs, and not a fit for the existing `mistral` provider entry
(`mistral-large-latest`, general-purpose, `eligible_for: [C1]` only). The
`mistral` chat branch in `components/ai-gateway/app/providers.py::
chat_model_for` already proves the native Mistral API path needs no new
transport code (`langchain_mistralai.ChatMistralAI`, no `base_url`
override) - the same reuse argument ADR-0416 made for
`ovhcloud-gpt-oss-120b` against `ChatOpenAI`.

`policies/data-classification/classification.yaml` (ADR-0021) fixes,
for every SaaS provider without exception, `external_saas: forbidden` at
`C3` - inherited automatically by giving the new provider
`eligible_for: [C1, C2]`, the same shape every existing SaaS entry uses.
Unlike ADR-0416's `ovhcloud-gpt-oss-120b`, this decision is scoped to a
specific *kind* of request (coding), not a task's every turn, for two
agents specifically:

- **Arkos** (seeds `C3`, same structural conflict ADR-0416 resolved for
  its `reflect_node`): needs Codestral preferred for coding requests
  specifically, with no automatic silent fallback to a different model if
  Codestral is unavailable (including running low on credits) - the
  requirement is to surface that failure, not paper over it.
- **Tekos** (seeds `C1`, no classification conflict): needs Codestral
  preferred for coding requests specifically, WITH an automatic fallback
  to the local model if Codestral is unavailable for any reason.

Two things needed for this have no precedent in the repo:

1. **Per-message task selection.** The model router picks a provider by
   `(agent, task)` (`policies/model-routing/model-routing-policy.yaml`'s
   `preferences:`), but task selection itself is always static and
   resolved once at graph-build time from `agent.okf.md`'s
   `primary_task` (`app/graph/build.py::GraphFactory.graph_for`). Even
   agents with several declared tasks (Finage: four; Tekos: three before
   this ADR) only ever execute their one `primary_task` at runtime - the
   others are inert OKF-catalog/documentation entries, never dynamically
   selected by message content. Building genuine runtime task-switching
   (a `task_id` on `ChatRequest`, `GraphFactory` changes) would be a much
   bigger, out-of-pattern lift than this decision needs.
2. **Provider-credit-exhaustion detection.** Nothing in this repo tracks
   a SaaS provider's own remaining balance or reacts to a 402/429 from
   one - `components/ai-gateway/README.md` documents this outright as
   unimplemented future work. The only existing fallback mechanism is
   generic: `app/main.py::_invoke_with_fallback` retries the next
   candidate on ANY exception, with no error-type inspection. Building
   live credit detection plus new interactive "pick another model" chat
   UX is explicitly out of scope for this iteration (declarative wiring
   only, matching this repo's existing pattern for `cost_ceiling_usd_per_1k`
   in `model-routing-policy.yaml`'s `objectives:` block - present in
   config, consumed only by an offline report, never enforced live).

## Decision

1. **Provider, dedicated credential.** Register `mistral-codestral` in
   `platform/ai-gateway/provider-routing.yaml` (`kind: saas`, `model:
   codestral-latest`, `eligible_for: [C1, C2]`), and add one
   `ChatMistralAI` branch to `providers.py::chat_model_for`, mirroring
   the existing `mistral` branch. Unlike ADR-0416's OVHcloud reuse, this
   credential is DEDICATED - a new `MISTRAL_CODESTRAL_API_KEY` /
   `zuno/providers/mistral-codestral` / `llm-provider-mistral-codestral`
   chain, fully parallel to (never reusing) the existing `mistral`
   provider's. See Alternatives considered for why.
2. **A generic `strict:` preference flag**, not Codestral-specific.
   `policies/model-routing/model-routing-policy.yaml`'s `preferences:`
   entries gain an optional `strict: true` field
   (`model_routing_policy.py::strict_for`), consumed by
   `routing.py::RoutingTable._apply_preference`: when set, the candidate
   list is narrowed to ONLY the still-eligible `prefer:` names - no
   unlisted survivor is appended - with a new fail-closed `RoutingError`
   if that list ends up empty. This is a structural change to which
   providers are even candidates, not live error/credit detection; it is
   what lets Arkos's and Tekos's coding paths genuinely differ in
   behavior without building the credit-detection machinery Context #2
   rules out.
3. **A non-primary `write-code` OKF task, declared for both agents**
   (`agents/arkos/tasks/write-code.md`, `agents/tekos/tasks/
   write-code.md`), the same "declared but not independently live-routed"
   status Finage's/Tekos's other non-primary tasks already have. This
   resolves Context #1 without new task-switching infrastructure: it
   supplies a real `(agent, task)` key for the preference table, while
   the actual routing happens through the EXISTING mechanism of a graph
   node choosing what `task_name` string to pass to
   `ModelRouter.invoke_with_fallback` per call - the same lever
   ADR-0416's `reflect_node` already pulled for a fixed classification
   override, pulled here for a fixed task-name override instead.
4. **Arkos: an early-exit `code_node`.** A new node reached via a
   `plan -> {code, retrieve}` conditional edge
   (`route_after_plan`, a keyword/regex heuristic in the same style as
   the existing `_TOOL_TRIGGER_PATTERN`), inserted in the
   `plan_draft_write` shape. Never runs `retrieve_node`, so its payload
   is only the user's own message - the same narrow-scope argument that
   makes evaluating it at a **fixed `C2` ceiling** safe, mirroring
   `reflect_node`'s ADR-0416 precedent exactly. Routed
   `strict: true`, `prefer: [mistral-codestral]` - if the call fails for
   any reason, the turn fails explicitly (a `ModelRouterError` surfaces
   as a visible failure reply) rather than silently substituting a model
   the user never asked for. That absence of automatic substitution IS
   this decision's buildable form of "ask the user to move to another
   model," given Context #2 rules out a real interactive prompt.
5. **Tekos: a `code_node` on the shared `retrieve_reason_respond`
   shape**, added via a data-driven selector
   (`_make_route_after_retrieval`) that only ever routes to it for an
   agent whose bundle declares a sibling `write-code` task - a true
   no-op for Comage/Advantage/Finage/Naveo, which share this exact shape
   but don't declare one. No classification override needed (Tekos seeds
   `C1`, and Codestral is `eligible_for: [C1, C2]`). Routed non-strict,
   `prefer: [mistral-codestral, local-gpt-oss, local]` - the EXISTING
   generic fallback-on-any-exception in `_invoke_with_fallback`
   (unchanged) already drops to local when Codestral errors for any
   reason, including running low on credits, giving "use local also for
   coding" from configuration alone.

## Alternatives considered

- **Reuse the existing `MISTRAL_API_KEY`/`zuno/providers/mistral`
  credential**, the same one-key-per-account reasoning ADR-0416 used for
  OVHcloud - rejected here specifically: Mistral issues API keys per
  project/account, and a dedicated Codestral key/project keeps "Codestral
  is out of credits" a distinguishable event from "mistral-large-latest
  is out of credits," which matters for a decision whose whole second
  half is about differentiated behavior on provider failure. ADR-0416's
  reuse argument doesn't transfer: OVHcloud's two models (SDXL,
  gpt-oss-120b) shared one account by necessity (one key per Public
  Cloud project); nothing forces that constraint here.
- **Build real credit-balance/402-429 detection plus an interactive
  "pick another model" chat prompt** - rejected for this iteration, an
  explicit scope decision: this repo has no budget/quota enforcement
  mechanism for ANY provider today (see Context #2), and building one
  novel piece for Codestral alone would be inconsistent with the
  documented "future work" status that gap already has everywhere else.
  The `strict:` flag achieves the required behavioral difference between
  Arkos and Tekos through routing structure instead.
- **Runtime task-switching infrastructure** (a `task_id` field on
  `ChatRequest`, `GraphFactory` changes to build/cache more than one
  graph per agent) - rejected: no other agent in this repo does this
  (even Finage's four declared tasks only ever execute one), and the
  existing per-call `task_name` label mechanism already gets the same
  effective routing granularity with a fraction of the surface area.
- **A single shared `write-code` implementation reused via the exact
  same factory both agents call** - rejected: Arkos's version is a
  fixed-C2-ceiling early exit from `plan_node` (mirroring `reflect_node`'s
  shape, since Arkos seeds C3); Tekos's is an unceilinged branch off
  `retrieve_node` (mirroring `reason_node`'s shape, since Tekos seeds
  C1). The two graphs' structural differences (Context of ADR-0342)
  meant a shared node would need agent-specific branches inside it
  anyway; only the coding-request KEYWORD HEURISTIC
  (`_code_request_trigger_reason`, `app/graph/nodes.py`) is actually
  shared - the same "same question, different point in two different
  graphs" reasoning that keeps `_live_read_trigger_reason` agent-generic
  too.

## Accepted risks (and their remediations)

- **Arkos's `strict: true` coding path has no automatic fallback by
  design** - a single Codestral outage or credit exhaustion is a visible,
  turn-ending failure, not a degraded-but-working response. Remediation:
  none needed - this is the intended behavior (Context's "ask the user to
  move to another model" requirement), not an oversight; if this proves
  too disruptive in practice, a follow-up ADR should add a real
  interactive model-choice UX rather than silently loosening `strict`.
- **The regex-based coding-request detector
  (`_code_request_trigger_reason`) will have false negatives/positives**,
  the same accepted-and-tunable status `_TOOL_TRIGGER_PATTERN` already
  has. Remediation: tune the pattern from real usage; verified against
  every existing test fixture message in this repo before shipping (no
  collisions found).
- **Registering `mistral-codestral` fleet-wide (Decision 1) makes it an
  available `C1`/`C2` fallback candidate for every agent on this shape**,
  not only Arkos/Tekos - the same fail-open-within-eligibility behavior
  every existing SaaS provider already has (ADR-0416 accepted the
  identical risk for `ovhcloud-gpt-oss-120b`). Remediation: none needed;
  only Arkos and Tekos additionally get a `write-code` task/node that
  actively prefers it - every other agent would only ever reach it as an
  unlisted, low-priority fallback survivor, same as `openai`/`anthropic`
  today.
- **Not independently verified that `codestral-latest` is the correct,
  current model identifier on the operator's real Mistral account** - the
  page the operator originally pointed at
  (`https://free-model.com/models/mistral-ai/codestral/`) returned
  HTTP 403 during this work and could not be checked. Remediation: the
  provider factory reuses `ChatMistralAI`, the same client the existing
  `mistral` entry already uses against the real Mistral API; verify the
  model name against the operator's own Mistral console/docs before the
  real key is seeded, as the first live smoke test step.

## Future work

- **A real interactive "pick another model" UX for Arkos's strict
  coding path** - not built here (see Accepted risks); would need a new
  signal surfaced from the AI Gateway's `RoutingError` through
  agent-runtime to the chat frontend, not just a text error reply.
- **Live provider-credit/quota detection** - the general gap this
  decision deliberately routes around (Context #2), same "not
  implemented" status every other provider in this repo already has.

## Related ADRs

- [ADR-0009](0009-separate-agent-runtime-from-ai-inference-gateway.md)
- [ADR-0020](0020-support-both-local-and-external-llm-providers.md)
- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md)
- [ADR-0024](0024-use-vault-for-application-secrets.md)
- [ADR-0034](0034-compute-effective-classification-from-the-complete-context.md)
- [ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md)
- [ADR-0342](0342-support-multiple-agent-graph-shapes-in-agent-runtime.md)
- [ADR-0416](0416-consume-gpt-oss-120b-via-ovhcloud-ai-endpoints.md)
- [ADR-0503](0503-make-each-okf-bundle-state-its-complete-authorization-contract.md)

See [Standard clauses](README.md#standard-clauses) for Consequences, Security/Operational
considerations, Migration/evolution, Acceptance criteria and Review evidence.

## Dated progress notes

- 2026-08-27: closed out to `Implemented` after the live smoke test. The accepted risks flagged
  that the model name was never independently verified against Mistral's own console; this
  resolves that. Executed from inside the `ai-gateway` pod through the same
  `langchain_mistralai.ChatMistralAI` path `providers.py` uses, with the dedicated
  `MISTRAL_CODESTRAL_API_KEY`: a real completion came back,
  `response_metadata.model_name: codestral-latest`. The id is correct as written and the
  dedicated credential chain resolves end to end.
