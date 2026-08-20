# ADR-0419: Split model preference into preferred/fallback, with prompt-slot overrides

- **Status:** Proposed
- **Target:** v0.4
- **Date:** 2026-08-20
- **Decision owners:** Zuno Demo architecture team

## Context

`policies/model-routing/model-routing-policy.yaml` expresses each `(agent, task)`'s
model routing as one flat `prefer:` list, consumed by
`components/ai-gateway/app/routing.py::RoutingTable._apply_preference`: providers
named in `prefer:` move to the front, in that order; any other classification-eligible
provider not named at all trails at the very end, in `provider-routing.yaml`'s
declared order. Position within the list is the only signal - there is no way to
say "these are my genuinely preferred choices" versus "these are acceptable, but
only once the real choices are gone" other than list order itself.

Two requirements motivate a schema change rather than another content-only edit:

1. **Tekos should try OVHcloud (`ovhcloud-gpt-oss-120b`) before
   openai/gemini/anthropic, with mistral third**, for its three general-purpose
   tasks (`answer-technical-question`, `find-relevant-docs`,
   `check-my-drive-docs`) - `write-code` (ADR-0417) keeps its own
   `mistral-codestral`-first rule untouched, since it already has a correct,
   task-type-specific preference.
2. **A specific call within a task should be able to declare its own model
   preference**, distinct from the task's default. This already exists as
   hand-written Python: `arkos_nodes.py::reflect_node` (ADR-0416) shares its
   task's `(agent, task)` = `(arkos, draft-architecture-testimonial)` routing key
   but evaluates its own call at a hardcoded `classification="C2"`, deliberately
   different from `draft_node`'s own (which uses the turn's real
   `effective_classification`, always `C3` for Arkos in practice). This decision
   formalizes that pattern as declarative OKF config instead of Python literals,
   so it shows up in a `git diff` to an agent bundle, not buried in a node
   function.

Two things converge on the same code this decision touches, both confirmed by
reading the current committed state before designing anything:

- **ADR-0417** (a concurrent, already-landed piece of work: commits `6087c95`
  through `cc3985c`) added `mistral-codestral` as a provider and a `strict:`
  preference flag: when set, `_apply_preference` narrows the candidate list to
  *only* the still-eligible `prefer:` names - no unlisted survivor appended,
  fail-closed (`RoutingError`) if none survive. `(arkos, write-code)` uses it
  (`prefer: [mistral-codestral]`, `strict: true`); `(tekos, write-code)` does
  not. This decision's schema sits alongside `strict:` unchanged - it is
  orthogonal (which candidates are named and in what tiers) rather than
  overlapping (whether unnamed candidates survive at all).
- **`platform/okf/generate_authorization_matrix.py` has a real, pre-existing
  accuracy gap.** `_load_model_routing()` never reads `strict:` at all, and
  `_effective_model_chain()` has no concept of a call-specific classification
  ceiling. Concretely, `agents/arkos/agent.okf.md`'s generated `write-code` row
  today shows `local`/`local-gpt-oss` as reachable fallbacks - at runtime,
  `strict: true` means only `mistral-codestral` is ever tried, no fallback at
  all. The committed doc is actively wrong about what the agent can do. The
  same class of gap already exists for `reflect_node`'s hardcoded `C2` (its row
  shows Arkos's ambient `C3` ceiling, not the `C2` the call actually runs at).
  Both are fixed here as a consequence of the new schema - a prompt slot
  declares its own ceiling and `strict:`-ness, and the generator reads and
  renders them - not as separate, disconnected bug fixes.

Two parts of a broader request this decision is scoped from turned out to
already be satisfied by prior work, confirmed during research, so they are
explicitly *not* new work here:

- "Image-generation tasks should prefer stable-diffusion" - already true by
  construction: `stable-diffusion-xl` is the only entry in
  `platform/ai-gateway/image-provider-routing.yaml`.
- "Long-reflection (DAT-like) tasks should prefer gpt-oss-120b" - already done
  for Arkos (`reflect_node`, ADR-0416) and forward-declared for Cognos.

## Decision

1. **`preferred:`/`fallback:` replace `prefer:` in `model-routing-policy.yaml`,
   backward-compatible.** A `preferences:` entry may keep using the existing
   single `prefer:` key (every untouched entry does, and keeps behaving
   identically - equivalent to `preferred: <that list>, fallback: []`), or use
   the new pair:
   ```yaml
   - agent: tekos
     task: answer-technical-question
     preferred: [local-gpt-oss, local, ovhcloud-gpt-oss-120b]
     fallback: [openai, gemini, anthropic, mistral]
   ```
   The loader concatenates `preferred + fallback` into one list before handing
   it to the unchanged `_apply_preference`/`_effective_model_chain` - this is a
   schema/expressiveness change, not a new routing algorithm. `strict:`
   continues to apply to the concatenated list exactly as it does today.
   `mistral-codestral` is deliberately left unlisted for Tekos's three general
   tasks: it stays reachable, trailing after `fallback` in
   `provider-routing.yaml`'s declared order - not preferred, never excluded.
2. **Tekos's three general tasks get the new order above** (local models first,
   per the existing local-first doctrine; then OVHcloud; then
   openai/gemini/anthropic, relative order unchanged from today; then mistral).
   `write-code` is untouched.
3. **Prompt slots.** A task's frontmatter gains an optional `prompts:` map,
   naming any call within that task that needs its own prompt text and/or its
   own classification ceiling:
   ```yaml
   # agents/arkos/tasks/draft-architecture-testimonial.md
   zuno:
     ...
     prompts:
       reflect:
         classification_ceiling: C2
   ```
   Prompt text for a named slot loads from
   `agents/<agent>/prompts/<task-name>--<slot>.md`, alongside the existing
   `<task-name>.md` convention for the task's primary/implicit prompt.
   `registry.py::TaskDefinition` gains a `prompts: Dict[str, PromptSlot]` field.
   `reflect_node` is refactored to read this slot's `classification_ceiling`
   instead of the hardcoded `"C2"`, and its prompt text instead of the inline
   system prompt string it has today - identical runtime behavior, now
   declarative.

   **Scoped down from this ADR's original draft during implementation**: a
   slot does *not* get its own `preferred:`/`fallback:` model-preference
   override. Model preference is resolved server-side by `ai-gateway` purely
   from the `(X-Zuno-Agent, X-Zuno-Task)` headers `ModelRouter.
   invoke_with_fallback` sends (`components/agent-runtime/app/clients/
   model_router.py`) - there is no existing mechanism for the caller to pass
   an explicit preference list that bypasses that server-side lookup, and
   `reflect_node` sharing its task's `task_name` (by design - see point 3's
   "Alternatives considered" entry on why it isn't a distinct task) means it
   is subject to the *same* `(arkos, draft-architecture-testimonial)` entry
   `draft_node` is. This turns out not to matter for `reflect_node` itself:
   preference is applied *after* classification-eligibility filtering, so
   the same ordered list (`[ovhcloud-gpt-oss-120b, local-gpt-oss, local]`)
   naturally produces a different effective chain at `reflect_node`'s `C2`
   ceiling (OVH eligible, leads) than at `draft_node`'s ambient `C3` (OVH
   excluded) - classification divergence alone is sufficient here. A real
   per-slot preference override, if a future case needs one, requires either
   a client-supplied override reaching `ai-gateway` (a request-contract
   change, not scoped here) or a distinct `task_name` per slot (this ADR's
   own rejected alternative, revisited only if the shared-classification
   trick above turns out insufficient for that future case). See Future
   work.
4. **Generator fixes**, both in `generate_authorization_matrix.py`:
   - Read and honor `strict:` in `_effective_model_chain` (mirrors
     `routing.py`'s real algorithm) - fixes Arkos's `write-code` row.
   - Render one row per declared prompt slot - a task with no `prompts:` renders
     exactly as it does today; `draft-architecture-testimonial` gains a second
     row for `reflect`, correctly showing its own `C2` ceiling.
   - A new agent-level **"Available models"** line: the generated union of
     every model reachable by any of the agent's tasks/slots, at any
     classification. Pure documentation - no new hand-authored,
     authorization-relevant field. Classification eligibility remains the only
     real gate; this line answers "what could this agent reach" without adding
     a second thing to keep in sync with it.
5. **Rollout: Tekos + Arkos now, prove the schema; the other six agents'
   existing `prefer:` entries migrate to `preferred:`/`fallback:` in a separate,
   later, independently-reviewed decision.** Nothing about this decision
   requires touching Advantage, Comage, Cognos, Finage, Naveo or Soursage's
   actual preference content - their entries keep working unchanged on the old
   `prefer:` key throughout. The "Available models" rollup (point 4's third
   bullet) is the one piece that *does* apply fleet-wide immediately, since it
   is purely additive documentation generation with no per-agent authoring
   required and no behavioral effect.

## Alternatives considered

- **Express "preferred vs fallback" as two positions within one still-flat
  `prefer:` list** (e.g. a separator marker) - rejected: two real YAML keys are
  self-documenting in a diff and in the generated table; a marker inside a flat
  list is exactly the kind of implicit convention this decision exists to
  replace.
- **Make the new schema mandatory, migrating every existing entry in this same
  decision** - rejected per explicit direction: prove the schema against its
  two concrete, currently-motivating cases (Tekos's reorder, Arkos's
  `reflect_node`) before touching the other six agents' already-correct,
  unrelated entries. A flag-day migration of content that isn't changing adds
  review surface without proportionate value right now.
- **Model prompt-slot overrides as a new, parallel `model-routing-policy.yaml`
  key space** (e.g. `(agent, task, slot)` triples in the same flat
  `preferences:` list) instead of task frontmatter - rejected: the slot's
  model preference is tightly coupled to the slot's own prompt text and
  existence (you cannot sensibly declare a `reflect` preference for a task with
  no `reflect` prompt), so co-locating them in the task bundle keeps the
  declaration and its consumer in one file, consistent with how
  `allowed_tools`/`allowed_knowledge` already live in task frontmatter rather
  than a separate policy file.
- **Give `reflect_node`'s slot its own distinct `task_name` routing key**
  (mirroring how `write-code` got its own key in ADR-0417) instead of a
  same-task prompt slot - rejected: `write-code` is a genuinely separate task
  (different tools, different knowledge domains, independently addressable);
  `reflect` is not a task in its own right, it is one step of
  `draft-architecture-testimonial`'s single task - a new prompt-slot concept
  models that relationship accurately, a second task would not.
- **Fix the generator's `strict:`/ceiling-override blindness as a standalone,
  disconnected bug-fix ADR** - rejected: both gaps are direct, mechanical
  consequences of introducing declarative prompt slots (the generator needs a
  place to read a call's own ceiling/strict-ness from, which prompt slots
  provide) - splitting them into a separate decision would document the fix
  before the thing that makes it possible to implement correctly.

## Accepted risks (and their remediations)

- **`mistral-codestral` and `ovhcloud-gpt-oss-120b` were already fleet-wide
  fallback candidates for every C1/C2 agent** (ADR-0416/ADR-0417's own accepted
  risk) - this decision does not change that exposure, only Tekos's explicit
  ordering among providers already reachable. No new remediation needed beyond
  what those ADRs already accepted.
- **Two schema shapes (`prefer:` and `preferred:`/`fallback:`) coexist in the
  same file during the Tekos/Arkos-only rollout.** A reader must know both to
  fully understand the file. Remediation: the ADR and a header comment in
  `model-routing-policy.yaml` state explicitly that both are valid and why;
  the later fleet-wide migration (point 5) removes the older shape entirely
  once proven, so this is a bounded, temporary state, not a permanent fork.
- **The `<task-name>--<slot>.md` prompt-file naming convention is new and
  unenforced by any schema validator today.** A typo'd slot name would silently
  produce a `None` prompt (matching today's existing silent-`None`-on-missing-
  file behavior for the primary prompt) rather than a load error. Remediation:
  none beyond the existing convention's own precedent - `_load_task` already
  behaves this way for the primary prompt; a stricter fail-loud check is a
  reasonable but separate future hardening (see ADR-0038/ADR-0039's schema
  validation surface), not required to land this decision safely, since
  `reflect_node`'s own code still supplies a literal fallback if the slot is
  absent, matching its current hardcoded-string safety net.

## Future work

- Migrate Advantage/Comage/Cognos/Finage/Naveo/Soursage's existing `prefer:`
  entries to `preferred:`/`fallback:` for schema consistency (content-preserving,
  no behavior change) - separate decision, separate review gate.
- Evaluate whether any other agent has a same-task, distinct-call-type pattern
  that would benefit from a prompt slot, the way Arkos's `reflect` does today.
  None identified during this decision's research.
- A stricter OKF validator that fails loudly on a `prompts:` entry naming a
  slot with no corresponding `<task-name>--<slot>.md` file, rather than
  silently resolving to `None` (see Accepted risks above).
- A genuine per-slot model-preference override, if a future slot's need
  cannot be satisfied by the classification-divergence trick `reflect_node`
  relies on today (point 3 above). Requires deciding how a caller-supplied
  preference reaches `ai-gateway` without a server-side `(agent, task)`
  lookup - a request-contract change to `ModelRouter.invoke_with_fallback`
  and the `/v1/chat/completions` schema, not attempted in this decision.

## Related ADRs

- [ADR-0009](0009-separate-agent-runtime-from-ai-inference-gateway.md)
- [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md)
- [ADR-0020](0020-support-both-local-and-external-llm-providers.md)
- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md)
- [ADR-0038](0038-use-standards-compliant-okf-v0-2-markdown-bundles.md)
- [ADR-0039](0039-make-agent-runtime-execute-the-okf-agent-contract.md)
- [ADR-0342](0342-support-multiple-agent-graph-shapes-in-agent-runtime.md)
- [ADR-0415](0415-consume-stable-diffusion-xl-via-ovhcloud-ai-endpoints.md)
- [ADR-0416](0416-consume-gpt-oss-120b-via-ovhcloud-ai-endpoints.md)
- [ADR-0417](0417-consume-codestral-via-mistral-api.md)
- [ADR-0503](0503-make-each-okf-bundle-state-its-complete-authorization-contract.md)

See [Standard clauses](README.md#standard-clauses) for Consequences, Security/Operational
considerations, Migration/evolution, Acceptance criteria and Review evidence.
