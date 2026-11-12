# WP-249 row 2: Lightspeed OLSConfig rollback, tested on demo333 (2026-11-12)

Live test with the user's go, by session zuno-avancement. The window ran from 10:32 to 10:38 UTC and was announced to
zuno-main and zuno-demo.

## Which version is "the previous one"

The rendered `OLSConfig` at HEAD is identical to the one of a73123cd (2026-10-25). The commits between a73123cd and
f5d66b66 rendered broken configurations:
- `reasoning_effort` sent, which broke every query (7f1b6213, 49ca2989);
- qwen35-9b, whose pod crash-looped (d7f4f4a0).

The previous valid and different version is f5d66b66 (2026-10-24). It uses the same gpt-oss-20b model through MaaS,
with `contextWindowSize: 32768` instead of 131072.

## Steps

| UTC | Step | Result |
|---|---|---|
| 10:32 | baseline, `golden_path_probe.py --only lightspeed` | PASS (219 chars) |
| 10:32 | 44a923fd pushed: `contextWindowSize: 32768`; hard refresh of `zuno-lightspeed-config-d0/d1` | |
| 10:33 | `OLSConfig` and the operator's `olsconfig` ConfigMap at 32768; lightspeed-app-server rolled | about 1 min after the push |
| 10:35 | the Lightspeed moment | **FAIL: HTTP 413 "Prompt is too long", "The input exceeds the model's context window"** |
| 10:35 | 5485706a pushed: `git revert` of 44a923fd | |
| 10:36-10:38 | `OLSConfig` and ConfigMap back at 131072; lightspeed-app-server rolled | |
| 10:38 | the Lightspeed moment | PASS (242 chars) |

## Findings

- **The mechanism works.** `git revert` on the chart reaches the app server in 1 to 3 minutes each way, through ArgoCD
  and the operator, and nobody touches the cluster.
- **The previous version is not a valid target any more.** Lightspeed answered 413 on the 2026-10-24 configuration.
  The app server logs, right after the forward, show what one query costs: a prompt of 1,223 tokens plus 14,585 tokens
  of tool definitions, with `tool_budget_ratio: 0.5`. The tool set grew after 2026-10-24 (the Zuno `/mcp` front-door
  tools, including the four `k8s.*` of WP-220), so a 32,768-token window no longer holds the query.
- **Rule for the runbook.** A Lightspeed rollback goes back to the previous commit of the chart only when nothing that
  feeds the prompt changed since then: the front-door capabilities, the MCP servers, or BYOK RAG. Otherwise the target
  is the last configuration that passed the Lightspeed moment. In every case, the rollback is closed only with the
  Lightspeed moment of the golden path.
