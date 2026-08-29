# ADR-0531: Promote qwen3.5-9b to the fleet-wide default model, extend OVHcloud reasoning access from Arkos to Tekos/Comage

- **Status:** Proposed
- **Target:** v0.4
- **Date:** 2026-08-30
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0419 introduced the `preferred:`/`fallback:` schema and per-call "prompt slot"
classification ceilings in `policies/model-routing/model-routing-policy.yaml`. That mechanism has
been fully implemented for some time (`components/ai-gateway/app/model_routing_policy.py`'s
`_preference_names`, `platform/okf/generate_authorization_matrix.py`'s `strict:`/per-slot
rendering, `arkos_nodes.py::reflect_node` reading `classification_ceiling` from task frontmatter)
even though the ADR's own `Status:` field was never flipped from `Proposed` - corrected alongside
this decision.

Separately, ADR-0526/WP-087 fine-tuned `Qwen/Qwen3.5-9B` into `qwen3.5-9b-wesh` (a French
urban-register style variant) for Comage, deploying both the fine-tune and its unmodified base as
live, separate `LLMInferenceService`s. WP-092 (2026-08-29) confirmed both are live and
node-separated. Both are registered `ai-gateway` providers today
(`platform/ai-gateway/provider-routing.yaml`): `local-wesh(-maas)` (model `qwen3.5-9b-wesh`) and
`local-qwen35(-maas)` (model `qwen3.5-9b`), both `eligible_for: [C1, C2, C3]`. `local-qwen35` was,
until this decision, not referenced by any `preferences:` entry - reachable only as an unlisted
tail behind whatever chain a given (agent, task) already had, never as a genuine default.

This is a business decision to make `qwen3.5-9b` - a smaller, cheaper local model than today's
implicit default `qwen3.6-27b-instruct` (the `local`/`local-maas` providers, first in
`provider-routing.yaml`'s file order) - the platform's new default candidate, with Tekos and
Comage each pairing it with Comage's fine-tune, and OVHcloud's `gpt-oss-120b` gaining explicit
preference on Tekos's and Comage's own reasoning-heavy tasks (previously an Arkos-only grant).
**This decision changes no code and no classification tier** - `policies/data-classification/
classification.yaml` still defines only C1/C2/C3, and `ovhcloud-gpt-oss-120b`'s `eligible_for:
[C1, C2]` (never C3) is unchanged: OVHcloud reaches the front of a chain only on turns that
compute at C1/C2, exactly the same eligibility-filtering mechanism ADR-0416 already established
for Arkos's `reflect_node` (list OVH first; a C3 turn has it eligibility-filtered out
automatically, no per-task ceiling override needed for Tekos/Comage since neither has a
`reflect_node`-style fixed-ceiling call - their reasoning-heavy tasks already compute at their
agent's own natural classification).

## Decision

1. **`qwen3.5-9b`(`-maas`) becomes the fleet-wide default candidate.** Every declared `(agent,
   task)` pair across all eight agents now carries an explicit `preferred:` entry in
   `policies/model-routing/model-routing-policy.yaml` - no more implicit
   `provider-routing.yaml` file-order default for any task, including tasks belonging to
   not-yet-deployed agents (Naveo, Soursage) and the inert Cognos placeholder. This is purely
   additive to every existing chain: `qwen3.5-9b(-maas)` is inserted, nothing already reachable
   is removed.
2. **Tekos pairs with `qwen3.5-9b-wesh` as its own fallback; Comage pairs the other way.** Tekos's
   three non-reflexional tasks (`find-relevant-docs`, `check-my-drive-docs`) and Comage's three
   non-reflexional tasks (`check-deal-status`, `update-opportunity-status`,
   `check-my-drive-and-mail`) lead with the agent's own primary model
   (`local-qwen35-maas`/`local-qwen35` for Tekos, `local-wesh-maas`/`local-wesh` for Comage),
   immediately followed by the other member of the pair as fallback - Comage remains the
   fine-tune's target agent (ADR-0526 decision 1), Tekos is not, so the pairing direction differs
   by design, not by oversight.
3. **Reasoning-heavy tasks keep their existing local-gpt-oss-20b lead, and now also gain
   OVHcloud.** Tekos's `answer-technical-question` and Comage's `compare-historical-deals` are
   both reflexional (multi-source synthesis / multi-year analysis, matching the shape ADR-0419's
   own header comment already used to justify gpt-oss-20b's lead over qwen on these two exact
   tasks). This decision does not reorder that existing doctrine: `local-gpt-oss(-maas)` keeps its
   rank. It adds `ovhcloud-gpt-oss-120b` ahead of it - the identical mechanism already proven for
   Arkos's `draft-architecture-testimonial`/`workshop-presentation` (ADR-0416): OVH leads when the
   turn computes at C1/C2, and is eligibility-filtered out at C3, where local-gpt-oss/wesh/qwen3.5
   take over with no extra config. The `qwen3.5-9b`/`qwen3.5-9b-wesh` pair from decision 2 is
   inserted behind gpt-oss-20b on these two tasks specifically, not ahead of it - the reasoning
   doctrine's leader is preserved, only OVH's reach is extended and the new pair's own position is
   appended after the existing local-first chain.
4. **Advantage's and Finage's four gpt-oss-20b-led tasks are demoted, not exempted.**
   `answer-project-question`, `identify-new-business-with-po`, `monthly-sales-report`
   (Advantage) and `identify-business-ready-to-invoice`, `monthly-invoice-report` (Finage) are
   analysis/judgment tasks, but were confirmed NOT to be protected reflexional overrides the way
   Arkos/Tekos/Comage's reflect-slot-bearing tasks are: `qwen3.5-9b(-maas)` becomes their new
   lead, `local-gpt-oss(-maas)` becomes a fallback rather than being removed.
5. **Every previously-entry-less `(agent, task)` pair gets an explicit entry now**:
   `advantage/check-my-drive-and-mail`, `finage/answer-finance-question`,
   `finage/check-my-drive-and-mail`, `cognos/review-historical-commercial-data`,
   `naveo/answer-onboarding-question`, `soursage/coming-soon` - all get the same fleet-default
   shape as decision 1. Naveo and Soursage are pre-live agents (no runtime route yet, per their
   own `NEXT_STEPS.md`); these entries are pure forward-declaration, identical in spirit to the
   pre-existing `cognos/coming-soon` precedent - zero live-routing effect until either agent is
   actually deployed.
6. **OVHcloud's reach stays scoped to Arkos, Tekos and Comage only** - Advantage/Finage/Cognos do
   not gain OVH preference in this decision. Cognos's pre-existing `coming-soon` OVH entry
   (ADR-0416, board-level reasoning) is unrelated prior art, kept unchanged; the newly-added
   `cognos/review-historical-commercial-data` entry deliberately does NOT gain OVH even though it
   also reads `knowledge.sxa-legacy` (the same C3-escalating domain as Comage's
   `compare-historical-deals`) - extending OVH there is new scope beyond what this decision
   authorizes, and Cognos is entirely inert either way.
7. **Arkos is untouched.** All three of Arkos's declared tasks are already fully covered by this
   decision's own carve-outs - `write-code` by "code uses mistral-codestral" (ADR-0417),
   `draft-architecture-testimonial`/`workshop-presentation` by "reflection uses
   ovhcloud-gpt-oss-120b" (ADR-0416, already in place, unaffected by decision 3's extension to
   Tekos/Comage). There is no remaining "default" Arkos task left to migrate to `qwen3.5-9b`.
8. **Every entry touched or created by this decision uses the `preferred:` key** (ADR-0419's
   schema), migrating off the legacy flat `prefer:` key as a byproduct of being touched for other
   reasons. The two `strict: true` entries (`arkos/write-code`, `tekos/write-code`) keep their
   `prefer:` shape and exact content unchanged - `evaluations/tekos/gate_checks.py`'s
   `tekos_write_code_prefers_mistral_codestral` check hard-asserts on `tekos/write-code`, and
   neither entry needed any content change this decision's scope requires.

## Alternatives considered

- **Make `qwen3.5-9b` lead Tekos's/Comage's reflexional tasks too, ahead of gpt-oss-20b** -
  rejected: this would silently regress the platform's existing reasoning-quality doctrine on
  exactly the two tasks that doctrine was written for, for no stated business reason; the
  business ask was specifically about Tekos's/Comage's *default* model, not about overriding an
  established reasoning-heavy preference.
- **Reorder `provider-routing.yaml`'s file order so `local-qwen35` leads globally, instead of
  writing an explicit `preferences:` entry per (agent, task)** - rejected: this repo's own
  convention (every existing agent already migrated away from relying on implicit file order, per
  ADR-0412's original preferences work) is explicit, auditable per-task entries; a file-order
  change would also silently affect any future agent/task added later with no entry of its own,
  which is exactly the implicit-default failure mode this decision is closing everywhere else.
- **Extend OVHcloud access to Advantage/Finage/Cognos too, since their tasks are also
  analysis-shaped** - rejected per explicit scope: the business ask named only Arkos, Tekos and
  Comage for OVH; widening it further is a separate decision if a real need for it materializes.
- **Introduce a new C0 classification tier for "low-risk default" routing** - rejected: no such
  tier exists in `policies/data-classification/classification.yaml`/ADR-0021, and nothing in the
  actual business requirement needs one - the existing C1 (public/low-risk, any provider) already
  serves that role, and OVHcloud's eligibility is governed entirely by its own `eligible_for:
  [C1, C2]`, unrelated to which local model leads.

## Consequences

- Every touched agent's `agent.okf.md` authorization matrix must be regenerated
  (`platform/okf/generate_authorization_matrix.py`) - the "Available models" rollup line and each
  task's reference-model row change for every agent this decision touches, mirroring ADR-0526's
  own equivalent consequence.
- `evaluations/tekos/stress_test.py`'s `layer1_model_routing` category
  (`_expected_reference_model`) recomputes its expectation directly from
  `provider-routing.yaml`/`model-routing-policy.yaml` at test time - no test-code change is
  required, it self-validates against the new chains.
- No GPU/quota/scheduling impact: no new provider, no new `LLMInferenceService`, no placement
  change - this decision only reorders already-live, already-eligible candidates.

## Security considerations

No `eligible_for` value changes on any provider - this is a pure reorder within chains that were
already eligibility-filtered exactly as before. C3 turns for Comage's `compare-historical-deals`
still resolve to a local-only survivor (the `qwen3.5-9b-wesh`/`qwen3.5-9b` pair, or
`local-gpt-oss`), never OVHcloud - `ovhcloud-gpt-oss-120b`'s `eligible_for: [C1, C2]` makes this
structural, unchanged from ADR-0416/ADR-0021.

## Operational considerations

Rollback is a pure GitOps revert of the YAML content change - no infrastructure to unwind, no
`LLMInferenceService` to delete. **`policies/model-routing/model-routing-policy.yaml` is baked
into the `ai-gateway` container image** (unlike `provider-routing.yaml`, which is a ConfigMap) -
this change takes live effect only through an ai-gateway image rebuild and rollout, not a GitOps
sync alone.

## Acceptance criteria

Beyond the Standard clauses:

- `platform/okf/generate_authorization_matrix.py --check --all` passes with the regenerated
  matrices committed.
- `evaluations/tekos/gate_checks.py`'s `tekos_write_code_prefers_mistral_codestral` still passes.
- A live Tekos `answer-technical-question` turn at C1 is answered by `ovhcloud-gpt-oss-120b`; a
  live Comage `compare-historical-deals` turn forced to C3 (via `knowledge.sxa-legacy` context)
  is answered by a local-only provider, never OVH.
- A live Tekos `find-relevant-docs`/`check-my-drive-docs` turn is answered by `qwen3.5-9b`, and
  falls back to `qwen3.5-9b-wesh` when the base is made unavailable; the reverse holds for
  Comage's `check-deal-status`/`update-opportunity-status`/`check-my-drive-and-mail`.

## References

- Work package: [WP-096](../roadmap/work-packages/wp-096-qwen35-9b-fleet-default-and-ovh-reasoning-rollout.md).

See [Standard clauses](README.md#standard-clauses) for Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md) - the C1/C2/C3
  eligibility rule this decision's reordering never bypasses
- [ADR-0034](0034-compute-effective-classification-from-the-complete-context.md) - C3 escalation
  that keeps Comage's `compare-historical-deals` local-only regardless of preference order
- [ADR-0412](0412-serve-gpt-oss-20b-on-the-unmanaged-full-gpu-node.md) - introduced the
  `preferences:` mechanism this decision's entries build on (superseded by ADR-0414 on the
  serving-placement question, not on the preference mechanism itself)
- [ADR-0416](0416-consume-gpt-oss-120b-via-ovhcloud-ai-endpoints.md) - the OVHcloud
  eligibility-filtering mechanism this decision extends to Tekos/Comage
- [ADR-0419](0419-split-model-preference-into-preferred-fallback-with-prompt-slot-overrides.md) -
  the `preferred:`/`fallback:` schema this decision's entries use (already implemented; its own
  `Status:` corrected alongside this decision)
- [ADR-0521](0521-route-local-model-traffic-through-maas.md) - the `-maas` sibling-before-direct-twin
  convention every entry in this decision follows
- [ADR-0526](0526-fine-tune-and-serve-a-french-urban-register-model-variant.md) - origin of
  `qwen3.5-9b`/`qwen3.5-9b-wesh` as live, separately-eligible providers
