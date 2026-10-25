# Lightspeed: "a tool result failed the safety inspection" (2026-10-25)

Observed on demo333: a question asked in the OpenShift Lightspeed console ("Qu'est-ce qu'un pod ?") ended with "Lightspeed stopped the
operation because a tool result failed the safety inspection" after the tool `search_openshift_documentation`. The question did reach the
model (the Lightspeed MaaS subscription counter moved, see WP-177), so the Zuno MaaS path is fine; the failure is inside Lightspeed.

## Cause (reproduced)

Lightspeed inspects every tool result with a classifier (`ols/src/tools/tool_result_inspection.py`). The classifier is the active chat model
(`zuno-maas` / `gpt-oss-20b`) called with a strict structured output (`json_schema`, `{injectionDetected, category}`) and a **hard-coded
`max_tokens` of 128** (`docs_summarizer.py`, classifier LLM parameters). It makes 3 attempts and then raises `ToolResultInspectionError`.

`gpt-oss-20b` is a reasoning model: its reasoning tokens count against `max_tokens`. With 128 tokens the answer is cut before the JSON is
complete, so every attempt fails and Lightspeed reports the same user-facing message as for a malicious result.

Evidence:
- The exported span `tool_result.inspection` has `inspection.outcome = classifier_error`, not `malicious`: the content was not judged hostile.
- The log shows exactly three `POST .../gpt-oss-20b/v1/chat/completions 200 OK` after the docs search (the 3 attempts).
- Reproduction inside the `lightspeed-app-server` pod with its own configuration and the real classes, one harmless snippet of `oc debug`
  documentation:
  - `max_tokens=128` (what Lightspeed does): `LengthFinishReasonError: Could not parse response content as the length limit was reached`
    (`completion_tokens=128`).
  - `max_tokens=1024`, same request: `parsed=ToolResultInspectionDecision(injection_detected=False, category='none')`,
    content `{"injectionDetected": false, "category": "none"}`, `finish_reason=stop`, 276 completion tokens (most of them reasoning).

So with this model the inspection can never pass on a tool call, and every Lightspeed question that calls a tool fails (documentation search,
the `openshift` and `zuno-mcp` MCP tools). Questions that call no tool are unaffected.

## Where the switch is

`OLSConfig.spec.ols.guardrails.toolResultInspection.enabled` (unset in the CR, so true; it protects against prompt injection in tool results).
The classifier `max_tokens` is not configurable.

## Options (nothing is applied)

1. **Serve Lightspeed with a non-reasoning model** (or one whose reasoning is off by default) through MaaS, e.g. `qwen36-27b-instruct`, which already
   has a Lightspeed subscription. The provider URL is per model (`.../zuno-ai-run/<model>/v1`), so this is a change of
   `gitops/charts/lightspeed-config/values.yaml` (`maasModelRef`) and a re-test; the same structured call must be checked on that model first
   (a reasoning-by-default Qwen would hit the same limit).
2. **Turn reasoning down for that route** on the vLLM / `LLMInferenceService` side (a model-serving change shared with every user of gpt-oss-20b).
3. **Disable the inspection** (`guardrails.toolResultInspection.enabled: false`): immediate, removes the prompt-injection guard on tool results;
   needs an explicit decision and an ADR note.
4. Ask Red Hat to make the classifier `max_tokens` configurable or reasoning-aware (upstream, not Zuno).

Recommendation (first version): check option 1 first. **Superseded by the finding below.**

## Fix found (2026-10-25, same day)

Lightspeed can send the reasoning effort itself: `OLSConfig.spec.llm.providers[].models[].parameters.reasoningConfig` is mapped, for the `rhoai_vllm`
provider, to the request-level `reasoning_effort` (`populate_vllm_reasoning`). Measured on a throwaway vLLM pod (zuno-bench) and in the Lightspeed pod
on the existing `gpt-oss-20b` route:

- vLLM `--default-chat-template-kwargs '{"reasoning_effort":"low"}'` is accepted but has **no effect** on gpt-oss (the default still reasons 700+ tokens, the
  content stays empty); the same value inside `chat_template_kwargs` does not work either. Only the top-level request field `reasoning_effort: "low"` does
  (454 tokens in total for a documentation answer, reasoning about 19 characters).
- Classifier call as Lightspeed makes it (`json_schema`, `max_tokens=128`) with `reasoningConfig: {effort: low}` set on the model, 5 snippets: 5/5 parsed,
  44-56 output tokens, verdicts right (the two injection attempts flagged `instruction_override`, the three benign snippets accepted).
- (A first test of `qwen36-27b-instruct` timed out because the served name is `qwen3.6-27b-instruct`; qwen36 and qwen35-9b also reason by default, so they would
  hit the same 128-token limit.)

**Correction (same day, after the roll-out): this fix does not work as deployed.** The chart value `olsConfig.provider.reasoningEffort: low` (7f1b6213) was applied
(user go) and the app-server restarted, but with `reasoningConfig` present Lightspeed switches to its `ChatVLLMReasoning` class and EVERY query then fails, including a
plain "Say hello in one word." (HTTP 500, `[LLM Backend] An error occurred during LLM invocation`, log: `AttributeError: 'dict' object has no attribute 'choices'` in
`_invoke_llm` / `astream`, although MaaS answered 200). The in-pod classifier test passed because it only exercised the structured-output call, not the streaming chat path.
Reverted in a73123cd (value empty again); Lightspeed answers again. The classifier limit is therefore still open: tool-using questions fail with the safety-inspection message until
another route is chosen (a non-reasoning model for Lightspeed, reasoning off on the vLLM route, disabling the inspection, or a Lightspeed fix). Lesson: validate the real
end-to-end path (a full query), not only the component that failed.
