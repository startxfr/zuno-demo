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

Recommendation: check option 1 first (one read-only structured call against qwen36, then a one-line values change), keep the inspection on.
