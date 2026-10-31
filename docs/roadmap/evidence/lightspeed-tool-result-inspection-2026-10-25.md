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

## Second round (2026-10-25 evening): server-side default effort on gpt-oss-20b, and the comparison with qwen3.5-9b

### What was changed on the gpt-oss-20b pod (mounted patch of vLLM code)

- **Why:** vLLM reads the Harmony reasoning effort only from the request field `reasoning_effort`; `--default-chat-template-kwargs` does not reach the Harmony path, and
  Lightspeed's `reasoningConfig` breaks its main chat (see above). The classifier of Lightspeed (128 tokens, no request field) therefore always ran at the default
  effort and ran out of tokens.
- **What:** a copy of the image's `vllm/entrypoints/openai/parser/harmony_utils.py` (vLLM 0.24.0+rhaiv.9, original sha256 `fa52ad6ac8b35371...`) with one added block in
  `get_system_message`: when the request carries no effort, use the env `ZUNO_DEFAULT_REASONING_EFFORT`. A request that sends `reasoning_effort` keeps it.
  Tested in a CPU-only pod: unset -> `Low`, `high` -> `High`.
- **Where:** models chart (`gitops/charts/models`): value `gptOssModel.defaultReasoningEffort: low`, file `files/gptoss-harmony_utils.py`, ConfigMap
  `gpt-oss-20b-harmony-patch` (`templates/configmap-gptoss-harmony-patch.yaml`), env and a `subPath` volumeMount in `templates/llminferenceservice-gptoss.yaml`.
  Commit `98becb8b` on devel, rolled by 08 on 2026-10-25 (the old ReplicaSet scaled to 0 because of the `zuno-ai-run-gpu-cap` quota).
- **Approved by:** the user, in the session that wrote it, after the chart change was rendered and the CPU test shown (2026-10-25).
- **Effect on others:** every request to gpt-oss-20b that sends no `reasoning_effort` (ai-gateway, the agents, the stresstests) now reasons at `low` instead of vLLM's
  default. Requests that send an effort are unchanged.
- **Rollback:** set `gptOssModel.defaultReasoningEffort` to empty (the env, mount, volume and ConfigMap disappear on the next sync; a pod restart follows).
- **Maintenance risk:** the file is tied to this vLLM build. When the vLLM image digest changes, re-derive the patch from the new file (the diff is 6 lines) or drop
  it; a mismatching copy could break the server at start. Nothing checks this automatically yet.

### Comparison through the Lightspeed code path (in the Lightspeed pod, OLSConfig unchanged; gpt-oss = default low, qwen3.5-9b = thinking off, 32768)

| Question | gpt-oss-20b | qwen3.5-9b |
|---|---|---|
| What is a pod (docs tool) | pass | pass (no tool) |
| Pods in openshift-lightspeed (OpenShift MCP) | pass | pass |
| Cluster-wide proxy | **fail** | pass |
| Cluster minor update | pass | pass |
| NetworkPolicy ingress rule | **fail** | pass |
| Install the GitOps operator | **fail** | pass |
| What is a namespace | pass | pass |
| OIDC identity provider | pass | pass |
| Secure route | pass | pass |
| Persistent storage | pass | pass |
| **Total** | **7 / 10** | **10 / 10** |
| Classifier outcome | the 3 failures are `injectionDetected: false` with category `unknown` (Lightspeed requires `none`; temperature 0, so the 3 retries are identical) | always `none` (1 to 3 calls per question) |
| Tokens per question (MaaS counter, classifier included) | 6k to 23k | 8k to 55k |
| Time per question (includes about 15 s of script start) | 50 to 65 s | 70 to 120 s |
| Confluence (zuno-mcp, Keycloak persona token) | works: first call with the wrong argument name (`search_query`), the tool error passes the classifier, it retries with `query` and answers | **fails**: keeps the wrong argument name, the tool error text is classified `injectionDetected: false` with a non-`none` category, Lightspeed aborts |

Limits met while testing: the Lightspeed subscription is 200,000 tokens per hour per model, which allows only about 6 to 10 docs questions per hour (classifier included).

## qwen3.6-27b with thinking off, and the decision (2026-11-01)

Read-only test run by zuno-demo-68 through the Lightspeed code path (thinking disabled per request with `chat_template_kwargs.enable_thinking=false`, admin token, no live change), the ten questions of the comparison above:

| Result | Detail |
|---|---|
| Questions answered | 4 of the 5 that completed (pods, cluster proxy, minor update, NetworkPolicy ingress) in 67 to 170 s each |
| Classifier | exercised once: failed on a 7,719-character `pods_list_in_namespace` result with `LengthFinishReasonError` at the hard-coded 128 completion tokens; the documentation tool results were not inspected in the passing runs |
| Not measured | questions 6 to 10: 429 on the Lightspeed 200,000 tokens/hour window |
| Context | with `contextWindowSize` 32768 the tool definitions (13,432 tokens) plus the request (1,230) exceed the prompt budget (14,336): the model's real window cannot carry today's MCP tool set; the test only ran with a 40,000 override |

Decision of the user: keep `gpt-oss-20b` with the server-side default reasoning effort `low` and keep the inspection enabled. No OLSConfig, model or budget change. Consequences accepted: about 30% of documentation questions fail on the classifier's `none`/`unknown` category mismatch (7 of 10 pass), Confluence keeps working. Next step if this becomes a priority: the 128-token cap and the `none`/`unknown` strictness are defects of the Lightspeed service, to be reported upstream; qwen3.6-27b is not a fix (slow, still hits the cap, window too small for the tools).
