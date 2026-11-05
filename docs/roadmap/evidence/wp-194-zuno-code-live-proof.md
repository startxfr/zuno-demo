# WP-194: "Zuno Code" in Open WebUI and OpenClaw

- **Date:** 2026-11-04 (deployment) and 2026-11-05 (live run), demo333, consultant-01 (Open WebUI) and consultant-02 (OpenClaw)
- **Running versions:**
  - ai-gateway build 41 (`d94b8554`, `sha256:5f9f27d9…`);
  - charts `b62e3b41`;
  - agents release v0.11.0 (`okf-corp@sha256:c77d8c9f…`, promoted by PR #28).
- **Rollback:** ai-gateway `sha256:59d12c1dd2c2c261f2455538a8463763a53c5706b9c29f022d5dc825a70f4b67`.
- **Brief:** [WP-194](../work-packages/wp-194-zuno-code-model-for-experience-clients.md),
  [ADR-0596](../../adr/0596-let-experience-clients-pick-a-declared-code-model-routed-to-codestral-first.md)

## Deployed state

1. **Routing table.** The ConfigMap `ai-gateway-model-routing` holds 24 preferences. Among them, `open-webui`/`code` and
   `openclaw`/`code` have `prefer: [mistral-codestral]` and no `strict`.
2. **ai-gateway.**
   - The environment has `MODEL_TASK_ALIASES=zuno-code=code:Zuno Code`.
   - `app/model_tasks.py` is in the pod.
   - The gateway started with no error and `/healthz` returns 200.
3. **Clients.**
   - Open WebUI shows the banner `zuno-routing-code`.
   - Both claws (`consultant-02`, `sale-01`) declare `{name: zuno-code, alias: zuno-code}`.
   - The Argo CD Applications `zuno-ai-gateway-d1`, `zuno-open-webui-d1` and `zuno-openclaw-d1` are Synced and Healthy at
     `b62e3b41`.
4. **Checks before the live run (18:10 local).**
   - `qwen36-27b-instruct` and `qwen35-9b` answer a 5-token completion with HTTP 200, in 0.33 s and 0.12 s.
   - All `LLMInferenceService`s are Ready.

## Automated checks

- ai-gateway suite: 366 passed, 358 before WP-194. `tests/test_wp194_model_tasks.py` covers:
  - `zuno-code` from an experience client is served by `mistral-codestral`, and `auto` by `local-maas`;
  - Codestral raising makes `local-maas` answer in the same turn;
  - an unmarked `tool` message keeps the turn local (ADR-0594);
  - a non-experience client sending `zuno-code` keeps its header task;
  - `zuno.task` is on the `model_call` span and not on the counters.
- `platform/okf/tests/test_generate_stack_config.py`: 38 passed. `generate_stack_config.py --check` passes on v0.11.0.

## Live run

2026-11-05, 10:00 to 10:25 local, in a window announced to the other sessions. Same question in each case: "peux tu me
faire du code python pour verifier une adresse email". The user reported the three cases OK. The figures are the
ai-gateway `model_call` spans in Tempo (`zuno-monitoring`, `tempo-tempo`).

| Case | Client, user | Model picked | Time | Provider, model | `zuno.task` | Class. | Tokens in / out | Duration |
|---|---|---|---|---|---|---|---|---|
| T1 | Open WebUI, consultant-01 | Zuno Code, tools off | 10:16:22 | `mistral-codestral`, codestral-latest | `code` | C1 | 595 / 192 | 1.3 s |
| T1, title | Open WebUI, consultant-01 | Zuno Code | 10:16:22 | `mistral-codestral`, codestral-latest | `code` | C1 | 258 / 10 | 0.45 s |
| T2 | Open WebUI, consultant-01 | Zuno | 10:17:00 | `local-maas`, qwen3.6-27b-instruct | `chat` | C1 | 797 / 2,384 | 129.8 s |
| T2, title | Open WebUI, consultant-01 | Zuno | 10:17:00 | `local-maas`, qwen3.6-27b-instruct | `chat` | C1 | 276 / 860 | 48.1 s |
| T3 | OpenClaw, consultant-02 | zuno-code | 10:23:13 | `mistral-codestral`, codestral-latest | `code` | C1 | 17,884 / 186 | 2.2 s |

Compared with the same question on 2026-11-04 at 11:18, before WP-194, when every call went to the local qwen:

| | Before (2026-11-04) | Zuno Code (2026-11-05) |
|---|---|---|
| Open WebUI, consultant-01 | qwen, 1,075 in / 3,641 out, 2 min 48 s | Codestral, 853 in / 202 out, 1.3 s |
| OpenClaw, consultant-02 | qwen, 8 calls with `exec` (C1, then C2), 159,885 in / 4,538 out, 5 min 10 s | Codestral, 1 call, 17,884 in / 186 out, 2.2 s |

Findings:
- `model: zuno-code` from an experience client sets the task to `code` and is served by `mistral-codestral`, and `auto`
  keeps the local-first order. `zuno.task` is on the span.
- Open WebUI's title call uses the picked model, so it goes to Codestral too.
- In T3 OpenClaw answered in one turn without running a tool. The "local after an `exec`" case was run live later the
  same day as T4 (see [T4](#t4-openclaw-zuno-code-with-an-exec-adr-0594)).
- The Codestral answers are shorter, with no reasoning tokens, and arrive 60 to 100 times faster than qwen's on this
  question.

## T4: OpenClaw, zuno-code, with an `exec` (ADR-0594)

2026-11-05, 15:05 to 15:08 local, in a window announced to the other sessions (after the RHOAI 3.6.0-ea.2 reinstall
and UnifAI 0.1.59). OpenClaw, consultant-02, model `zuno-code`, new session. The question: "Écris un script python qui
vérifie une adresse email, puis exécute-le sur ces 3 valeurs : alice@startx.fr, pas-une-adresse, bob@exemple et
montre-moi la sortie." The user reported that the script was run and worked. The figures are the `model_call` spans in
Tempo.

| Time | Trace | Provider, model | `zuno.task` | Class. | Tokens in / out | Duration |
|---|---|---|---|---|---|---|
| 15:05:52 | `bf550c0b4900b465` | `mistral-codestral`, codestral-latest | `code` | C1 | 17,917 / 25 | 0.98 s |
| 15:05:53 | `bf550c0b4900b465` | `local-maas`, qwen3.6-27b-instruct | `code` | C2 | 18,158 / 334 | 24.0 s |
| 15:06:17 | `bf550c0b4900b465` | `local-maas`, qwen3.6-27b-instruct | `code` | C2 | 18,465 / 86 | 9.6 s |
| 15:06:27 | `bf550c0b4900b465` | `local-maas`, qwen3.6-27b-instruct | `code` | C2 | 18,569 / 240 | 18.5 s |
| 15:07:09 | `e3ef1a2c7a95b3ec` | `local-maas`, qwen3.6-27b-instruct | `code` | C2 | 18,834 / 468 | 30.9 s |
| 15:07:41 | `e3ef1a2c7a95b3ec` | `local-maas`, qwen3.6-27b-instruct | `code` | C2 | 19,353 / 67 | 8.6 s |
| 15:07:49 | `e3ef1a2c7a95b3ec` | `local-maas`, qwen3.6-27b-instruct | `code` | C2 | 19,414 / 332 | 23.0 s |

Findings:
- **Codestral on the tool-free start.** The first call of the turn has no tool result yet. It is C1, so `zuno-code`
  sends it to Codestral, which answers with the `exec` tool call (25 output tokens).
- **Local after the tool.** Every later call carries the unmarked `exec` result. It is C2, so it is local-only and
  `local-maas` serves it (ADR-0594, ADR-0596 decision 4). The second trace (15:07) is a follow-up turn of the same
  session, which still carries the tool results, and stays local.
- **Guardrails in observe mode.** On every call, NeMo Guardrails (`observe` mode) detected `email` in the prompt.
  Observe mode does not change the classification, so the first call stayed C1 and went to Codestral. The test values
  are not personal data. With real addresses, the turn would still have reached Mistral at C1; only the guardrails mode
  (or a C2 classification of the prompt) prevents that.
- **A cancelled call before the test.** At 15:05:51, a C1 call with no `zuno.task`, so not `zuno-code` (trace `a2c667d32695ece2`), was
  cancelled after 103 s, before T4 started.

## Not run live

- **Codestral down.** It is not tested live, because the key lives in Vault and this session does not write there. The
  fallback is covered by the unit test above.

## Addendum: Dify, agents release v0.12.0

On 2026-11-05, agents release v0.12.0 declared `dify` as an experience client with tasks `chat` and `code`
([ADR-0599](../../adr/0599-serve-a-no-code-workflow-canvas-with-dify-as-an-experience-client.md),
[WP-204](../work-packages/wp-204-install-dify-on-demo333.md)). The release was promoted by zuno-demo PR #30. Argo CD then
synced the ConfigMap `ai-gateway-model-routing`, which gained `dify`/`code` with `prefer: [mistral-codestral]`. The
ai-gateway reloaded it at 11:34:30Z (`routing reloaded … sha256 5305d3d43718`), with no restart. The image and
`MODEL_TASK_ALIASES` did not change, because Dify was already in `MARKER_FAIL_CLOSED_CLIENTS`.

`model_call` spans from Dify in Tempo (UTC). The last two calls ran after the RHOAI 3.6.0-ea.2 reinstall on demo333.

| Time | Trace | Task | Provider, model | Class. | Duration |
|---|---|---|---|---|---|
| 11:54:54 | `11db781394b02eda` | `chat` | `local-maas`, qwen3.6-27b-instruct | C1 | 0.44 s |
| 11:55:06 | `ab430fb243c8859c` | `code` | `mistral-codestral`, codestral-latest | C1 | 0.36 s |
| 11:55:16 | `5102736d016e965c` | `chat` | `local-maas`, qwen3.6-27b-instruct | C1 | 1.22 s |
| 12:04:40 | `c8da2a0a724d921e` | `code` | `mistral-codestral`, codestral-latest | C1 | 0.84 s |
| 12:52:01 | `2d612a73b22da823` | `chat` | `local-maas`, qwen3.6-27b-instruct | C1 | 1.23 s |
| 12:52:02 | `571b9e6109a23444` | `code` | `mistral-codestral`, codestral-latest | C1 | 0.47 s |

The ADR-0594 rule (a turn with a tool result stays local) applies to Dify as it does to the other clients. This
addendum does not exercise it.
