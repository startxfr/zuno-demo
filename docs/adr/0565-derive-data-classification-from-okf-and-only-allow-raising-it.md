# ADR-0565: Derive data classification from OKF and only allow raising it

- **Status:** Accepted
- **Target:** v0.11
- **Date:** 2026-10-17
- **Decision owners:** Zuno Demo architecture team
- **Extends:** [ADR-0034](0034-compute-effective-classification-from-the-complete-context.md) (compute effective classification from the complete context)
- **Related:** [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md), [ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md), [ADR-0527](0527-introduce-the-project-as-the-sharing-and-context-boundary.md), [ADR-0550](0550-demonstrate-sovereign-ai-through-classification-specialization-and-resilience.md), [ADR-0560](0560-keep-the-ai-gateway-as-the-policy-router-in-front-of-unifai.md), [ADR-0563](0563-forward-caller-identity-and-zuno-context-headers-from-unifai.md), [ADR-0564](0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md), [ADR-0568](0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md), [ADR-0571](0571-evaluate-the-rhoai-mcp-gateway-before-extending-mcp-gateway.md)

## Context

The C1/C2/C3 level of a model call decides which providers may serve it
(ADR-0021, `policies/data-classification/classification.yaml`: C1 any
provider, C2 approved SaaS only, C3 never leaves the cluster). Today the level
is produced in `components/agent-runtime` from three inputs:

- **The agent's OKF default.** Every bundle declares
  `zuno.model.preferred_classification` in `agents/<name>/agent.okf.md`
  (`tekos` and `naveo` C1; `comage`, `soursage`, `advantage`, `finage` C2;
  `cognos` and `arkos` C3). A task's prompt slot may declare its own
  `classification_ceiling` (`agents/arkos/tasks/workshop-presentation.md`'s
  `reflect` slot at C2; parsed by `app/registry.py` `PromptSlot`).
- **Monotone escalation during the turn.** `app/graph/classification.py`
  `_escalate` is a highest-rank-wins comparison. `retrieve_node` seeds the turn
  at the agent default raised by the project's classification (ADR-0527
  clause 5, `app/graph/nodes.py`), and tool results such as Confluence (C2)
  raise it further (ADR-0034). Conversation history keeps the highest level it
  reached (`app/main.py`, `history_classification`).
- **Source-level local-only.** A tool whose policy says
  `external_model_policy.allow_context: false` sets `X-Zuno-Local-Only`
  (ADR-0035), and the ai-gateway ORs in a per-(agent, task) `local_only_for`
  declaration (`components/ai-gateway/app/main.py`, ADR-0550).

The ai-gateway then trusts the header: `X-Zuno-Data-Classification` defaults
to `C1` when absent (`Header(default="C1")` in `app/main.py`), as does
`components/mcp-gateway/app/main.py` on one of its two endpoints.

Under UnifAI (ADR-0561) none of the agent-runtime code remains. The OKF bundle
still exists (ADR-0564 keeps it the source of truth), but the level must now be
carried by a UnifAI session and rendered into a header by a templated LLM
resource (ADR-0563), and a UnifAI user can author LLM resources. A level that
anyone can lower by editing a header template is no classification at all.

## Decision

**The classification of a UnifAI execution starts at the level its OKF bundle
declares, is carried by the session, can only rise during the session, and is
enforced again at the ai-gateway as a floor.**

1. **OKF is the only source of defaults.** The unifai-operator, when it
   expands a bundle (ADR-0564), records for each emitted agent the agent's
   `preferred_classification` and, per task and prompt slot, any declared
   `classification_ceiling`. Per-(agent, task) `local_only_for` stays where it
   is, in `policies/model-routing/model-routing-policy.yaml`, enforced by the
   gateway. No UnifAI UI field and no `UnifaiAgent` spec field written by
   hand can set them.
2. **The operator validates.** A bundle is rejected - no objects emitted,
   status condition set - when a level is not one of the levels in
   `classification.yaml`, or when a task or slot declares a level below its
   agent's default without an explicit `zuno.classification_override_reason`.
   Lowering per task stays possible (arkos's `reflect` slot relies on it) but
   only as a reviewed, signed bundle declaration, never at runtime.
3. **The session carries a monotone level.** A UnifAI session gets a
   `classification` attribute initialised to the agent's (or task's) default,
   raised to the project's level when the session belongs to one, and a
   boolean `local_only`. Both expose a single raise operation; an attempt to
   set a lower level or to clear `local_only` is refused and logged. Sources
   that may raise them: the user (an explicit UI action), a RAG source whose
   declared classification is higher (ADR-0568 gives each `UnifaiRAGSource` a
   classification), and a tool result carrying classification or
   external-context metadata.
4. **The header is rendered from the session, never typed.** Operator-emitted
   LLM resources use `X-Zuno-Data-Classification: {classification}` and
   `X-Zuno-Local-Only: {local_only}` (ADR-0563). The template engine has no
   other way to produce those two headers.
5. **The ai-gateway enforces the floor independently.** The gateway receives a
   generated slice of per-(agent, task) floors - the same generated-config
   pattern as `app/quota_budgets.yaml` - and computes
   `effective = max(header, floor(agent, task))`, exactly as it already ORs
   `local_only_for` into the caller's local-only flag. A request with no
   classification header is treated as `C3`, not `C1`, once WP-150 has
   confirmed which current callers omit it (unverified: `mcp-gateway`'s
   built-in tools and the acceptance gate are the candidates to check).
6. **Automatic raising from tool results needs metadata that does not reach
   MAS yet.** `mcp-gateway`'s REST response echoes `external_model_policy`
   (ADR-0035), but an MCP-protocol path (ADR-0571) must carry it in the tool
   result's metadata, and MAS must read it - designed in WP-150 with WP-152.
   Until it exists, an agent whose tools introduce higher-class content
   declares that higher level statically in its bundle (and, for local-only
   sources, a `local_only_for` entry in `model-routing-policy.yaml`).
   This is conservative by construction: it over-classifies, it never
   under-classifies.

## Planned supersession

None. ADR-0034's rule - effective classification from the complete context,
never downgraded - is restated here, not replaced; its implementation-state
paragraph naming `agent-runtime` receives a dated note at cutover (WP-156).
ADR-0035 and ADR-0527 clause 5 likewise stand.

## Consequences

The level a model call is routed at no longer depends on code inside the agent
platform alone: the bundle states it, the operator checks it, the session can
only raise it and the gateway refuses to go below it. That is stronger than
today, where the gateway floor exists only for `local_only_for`.

Clause 6's interim makes some agents more restrictive than they are today.
`tekos` currently answers public documentation at C1 and escalates only when
Confluence enters context; until dynamic raising from tool results works, a
`tekos` with Confluence access is declared C2 with Confluence local-only, so
those turns lose SaaS candidates. The pilot (ADR-0573) measures whether that
is acceptable or whether clause 6 must land first.

Semantic-cache keys already bind classification and local-only
(`app/semantic_cache.py`), so a raised session can never hit a lower-level
cache entry.

## Security considerations

The threat addressed is platform-mediated leakage: content of a given
sensitivity reaching a provider not eligible for it because an agent, a
template or a defaulted header said so. It does not address a user who
deliberately pastes content they can already read into an agent declared at a
lower level; that is unchanged from today.

Defaulting an absent header to C3 fails closed: a misconfigured resource gets
local-only routing instead of SaaS routing. The floor in clause 5 depends on
`X-Zuno-Agent` and `X-Zuno-Task`, which are themselves headers; a caller that
omits them falls to the global default (C3 under clause 5), and a caller that
claims another agent's identity gets at most that agent's floor, which is why
clause 5 keeps the floor list in the gateway and not in UnifAI.

## Operational considerations

The generated floor slice joins the authorization-matrix drift check
(ADR-0503): a bundle change that moves a floor must regenerate it. Tests
(WP-150): a session cannot be lowered through the API; an operator-emitted
resource for `cognos` sends `C3`; a hand-written request to the gateway
claiming `X-Zuno-Agent: cognos` with `C1` is routed at C3; a request with no
classification header is routed local-only. Live checks run on demo333
(powered off at the time of writing; the user must be asked to power it on),
with `--context` passed explicitly to every `oc` command (ADR-0559).
