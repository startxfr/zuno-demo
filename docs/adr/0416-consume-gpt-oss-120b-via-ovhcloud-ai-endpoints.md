# ADR-0416: Consume gpt-oss-120b via OVHcloud AI Endpoints

- **Status:** Proposed
- **Target:** v0.4
- **Date:** 2026-08-20
- **Decision owners:** Zuno Demo architecture team

## Context

`gpt-oss-120b` is not servable on this cluster's GPUs -
`gitops/charts/models/values.yaml`'s `modelsS3` comment marks it "transit
storage for the operator's own workstation only," and ADR-0414 explicitly
ruled it out for local tiering (the largest available MIG slice, `2g.48gb`,
is why Qwen3-32B was chosen for tier 1 instead). The only way to offer it at
all is a remote provider.

ADR-0415 already set up an OVHcloud AI Endpoints account for
`stable-diffusion-xl` - a Vault-backed `OVHCLOUD_API_KEY`
(`zuno/providers/ovhcloud`, `ExternalSecret`
`platform/ai-gateway/externalsecret-ovhcloud.yaml`) already mounted into
`ai-gateway`. Checking OVHcloud's live catalog (2026-08-20) confirms
`gpt-oss-120b` is served on the **same** base URL as `stable-diffusion-xl`
(`https://oai.endpoints.kepler.ai.cloud.ovh.net/v1`), through the same
OpenAI-compatible shape (`/chat/completions`, `Authorization: Bearer`),
131k-token context, function-calling and streaming supported. This is
materially simpler than ADR-0415's image work: `provider-routing.yaml` /
`app/routing.py::RoutingTable` / `app/providers.py::chat_model_for` are
already a generic, multi-provider chat abstraction (`local`, `local-gpt-oss`,
`openai`, `gemini`, `anthropic`, `mistral`) - ADR-0415 only needed a sibling
image-specific module because image generation doesn't fit
`BaseChatModel`; a new chat provider does not have that problem, and reuses
the existing `OVHCLOUD_API_KEY` credential as-is, with no new Vault path,
`ExternalSecret`, or chart change.

`policies/data-classification/classification.yaml` (ADR-0021) fixes, for
every SaaS provider without exception, `external_saas: forbidden` at `C3`.
This is not a choice this decision makes - it is inherited automatically by
giving the new provider `eligible_for: [C1, C2]`, the same shape every
existing SaaS entry already uses.

Two of the four candidate agents complicate that inheritance:

- **Arkos** seeds `C3` (`agent.okf.md`'s `model.preferred_classification`) -
  its notes say sovereign-marked DAT workflows are local-model-only by
  nature. `app/graph/arkos_nodes.py::retrieve_node` initializes
  `effective_classification` from that `C3` seed and only ever escalates it
  (ADR-0034) - so `draft_node`'s own model call is `C3` on every real turn,
  with no exception, making a `[C1, C2]`-only provider structurally
  unreachable there without a scoped override.
- **Cognos** also seeds `C3`, but is a genuine placeholder today
  (`status: placeholder`, zero declared tools/knowledge,
  `tasks/coming-soon.md`) with no runtime route at all - so, unlike Arkos,
  there is no live code path yet where the classification-ceiling question
  is forced.

**Comage** (`C2`) and **Finage** (`C2`, but see Decision 4 below) have no
such conflict: a `[C1, C2]`-eligible provider is reachable on their existing
chain the same way `openai`/`anthropic` already are.

## Decision

1. **Provider.** Register `ovhcloud-gpt-oss-120b` in
   `platform/ai-gateway/provider-routing.yaml` (`kind: saas`, `model:
   gpt-oss-120b`, same endpoint/`api_key_env` as `ovhcloud-sdxl`,
   `eligible_for: [C1, C2]`), and add one `ChatOpenAI(base_url=...)` branch
   to `components/ai-gateway/app/providers.py::chat_model_for`, matching the
   shape of the existing `local`/`openai` branches. No other file in
   `ai-gateway`, `agent-runtime` or `mcp-gateway` needs to change - chat
   completions is already fully provider-agnostic end to end.
2. **Comage.** OKF-registration only. No `prefer:` entry, no new task file:
   the provider becomes visible as an additional `C1`/`C2` fallback
   candidate automatically, identically to how `openai`/`anthropic` already
   are for every other `C2` agent (Advantage, Tekos at `C1`, etc. see the
   same addition fleet-wide). A future pre-sales response/strategy task is
   noted under Future work, not built here.
3. **Cognos.** A forward-declared `prefer: [ovhcloud-gpt-oss-120b,
   local-gpt-oss, local]` entry in `policies/model-routing/
   model-routing-policy.yaml`, inert like the rest of Cognos's config until
   it is actually built. No override needed: a turn computing at `C1`/`C2`
   (ordinary board Q&A) gets it first; a turn escalating to `C3` (genuine
   Direction-level financial/strategic material) excludes it automatically
   via the same fail-closed eligibility rule as every other agent, falling
   back to `local-gpt-oss`/`local`.
4. **Arkos.** A new `reflect` graph node (`app/graph/arkos_nodes.py::
   reflect_node`), inserted between `draft` and `write` in the
   `plan_draft_write` shape - a self-review/refinement pass over
   `draft_node`'s own output text only, never the raw `retrieved_docs`/
   Confluence context `draft_node` was grounded in. That narrow scope is
   what makes it safe to evaluate at a **fixed `C2` ceiling**, mirroring
   ADR-0415's `generate_image` scoped exception exactly: both calls' payload
   is a short, already-derived string rather than raw source material, so
   evaluating it below the turn's own escalated classification does not let
   that turn's actual `C3` source content leave the cluster. `reflect_node`
   still honors `local_only_required` (ADR-0035) unconditionally - the `C2`
   ceiling overrides classification *escalation* only, never that separate
   source-level restriction. The same `(agent, task)` `prefer:` entry as
   Cognos's applies; it is inert for `draft_node`'s own call (permanently
   `C3`) and only takes effect for `reflect_node`'s explicit override.
5. **Finage: hardened to genuine local-only, not merely excluded.**
   Investigation before this decision found Finage was not actually
   local-only despite its finance-only scope - it is seeded `C2` with
   `openai`/`anthropic` already live in its fallback chains, same as every
   other `C2` agent. Excluding only the new provider would have left that
   inconsistency in place. A new declarative `zuno.model.local_only: true`
   field (`AgentDefinition.local_only`, `registry.py`) is threaded through
   every model-router call site that already reads the per-turn
   `local_only_required` state flag - `reason_node` (`nodes.py`, Finage's
   `retrieve_reason_respond` shape), history compaction
   (`history.py::compact`) and memory extraction (`memory.py::
   extract_memory`) - forcing local **unconditionally, at every
   classification including `C1`**, where neither the existing `C2`/`C3`
   compaction/extraction rule nor any per-tool `local_only_required` would
   otherwise fire. `generate_authorization_matrix.py` was updated to honor
   this flag too, so Finage's generated model-routing table now correctly
   shows only local candidates instead of the now-unreachable
   `openai`/`anthropic`/`ovhcloud-gpt-oss-120b`.

## Alternatives considered

- **Model Arkos/Cognos's addition on ADR-0415's `image_providers.py`
  pattern** (a single-provider-name-branch dispatch, MCP tool binding) -
  rejected: that path is structurally image-specific (base64 payload
  shape, `openai.Images.generate`, a dedicated MCP handler); a chat model
  needs none of it, since `providers.py`'s chat factory was already
  generic before ADR-0415.
- **A dedicated Vault path/credential per OVH model**
  (`zuno/providers/ovhcloud-gptoss` vs. reusing `zuno/providers/ovhcloud`) -
  rejected per the stated requirement to reuse the same OVH account/API
  call; OVHcloud issues one key per Public Cloud project, not per model, so
  a second path would only add an unused indirection.
- **Fix Finage by excluding `ovhcloud-gpt-oss-120b` alone, leaving
  `openai`/`anthropic` in place** - rejected: leaves the "Finage never uses
  an external model" requirement only partially true, and the gap was
  already there independent of this decision. Closing it now is a small,
  narrowly-scoped addition (one flag, four call sites already built for
  exactly this kind of forcing).
- **Downgrade Arkos to `C2` entirely to reach `gpt-oss-120b` without a
  scoped override** - rejected, same reasoning as ADR-0415's identical
  alternative for Arkos/Cognos: broader than needed, weakens the
  local-only guarantee for all Arkos traffic instead of the one narrow,
  audited call.
- **Give `reflect_node` its own `(agent, task#reflect)` preference key**
  instead of sharing Arkos's existing `(arkos, draft-architecture-
  testimonial)` entry - rejected for this v0: the shared key already
  produces the correct effective behavior (`draft_node` structurally never
  sees the new provider; `reflect_node` does), because eligibility, not
  preference, is what does the real gating. A distinct key would only
  matter once a second call type on the same task needs a *different*
  preference order than the task's primary call - not the case here.

## Accepted risks (and their remediations)

- **The scoped `C2` ceiling for Arkos's `reflect_node` narrows ADR-0021/
  ADR-0035's "`C3` never leaves the cluster" guarantee, same residual
  exposure ADR-0415 already accepted for `generate_image`.** The draft text
  reflected on could still indirectly carry traces of `C3` source material
  even though raw context/citations are never in its payload by
  construction. Remediation: none beyond the structural narrowing to
  `document_draft` text only - accepted as a deliberate, scoped trade-off,
  consistent with the precedent this mirrors. If this proves insufficient,
  a follow-up ADR should add content screening before the call, not a wider
  classification change.
- **Registering `ovhcloud-gpt-oss-120b` fleet-wide (Decision 1) makes it an
  available fallback for every `C1`/`C2` agent, not only the four discussed
  here** (Advantage, Tekos, Naveo, Soursage all gain it automatically,
  identically to how `openai` already appears for them). Remediation: none
  needed - this is the same fail-open-within-eligibility behavior every
  existing SaaS provider has always had in this system; scoping usage
  narrower would require a bespoke per-agent eligibility mechanism this
  repo does not have and this decision does not introduce.
- **Not independently verified that OVHcloud's `gpt-oss-120b` deployment
  matches the exact `/chat/completions` request/response shape this
  decision assumes beyond the catalog page checked.** Remediation: the
  provider factory reuses `ChatOpenAI`, the same battle-tested client every
  other SaaS provider here already uses against a real OpenAI-compatible
  server: a live smoke test against the real account is the natural
  first verification step before this ships, no bespoke integration code to
  separately trust.

## Future work

- **Comage pre-sales response/strategy task.** Not built here - Decision 2
  registers the provider only. A future task (e.g.
  `draft-presales-response`) would declare its own `allowed_tools`/
  `allowed_knowledge` and, if warranted, its own `prefer:` entry, following
  the same pattern every other Comage task already does.

## Related ADRs

- [ADR-0009](0009-separate-agent-runtime-from-ai-inference-gateway.md)
- [ADR-0020](0020-support-both-local-and-external-llm-providers.md)
- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md)
- [ADR-0024](0024-use-vault-for-application-secrets.md)
- [ADR-0034](0034-compute-effective-classification-from-the-complete-context.md)
- [ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md)
- [ADR-0342](0342-support-multiple-agent-graph-shapes-in-agent-runtime.md)
- [ADR-0414](0414-consolidate-zuno-ai-run-into-three-tiered-mig-predictors.md)
- [ADR-0415](0415-consume-stable-diffusion-xl-via-ovhcloud-ai-endpoints.md)
- [ADR-0503](0503-make-each-okf-bundle-state-its-complete-authorization-contract.md)

See [Standard clauses](README.md#standard-clauses) for Consequences, Security/Operational
considerations, Migration/evolution, Acceptance criteria and Review evidence.
