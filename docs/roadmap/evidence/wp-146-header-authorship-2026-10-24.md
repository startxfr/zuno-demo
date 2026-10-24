# WP-146 step 6: who decides the Zuno context headers (probes, 2026-10-24)

Question: any UnifAI user can create an LLM or MCP resource with arbitrary `X-Zuno-*` header templates
(ADR-0563 clause 4). What do the two gateways do with such headers? Probes on demo333 with the persona
`eval-consultant-01` signing in through the client `zuno-evaluations` (its own JWT, no platform identity), on
the ai-gateway before and after the fix of commit 2f981d17, and on the MCP gateway.

## MCP gateway: the headers can only restrict

Calls to `/v1/tools/<tool>/invoke` with the persona's JWT and a forged declaration:

| Declaration sent | Result |
|---|---|
| `X-Zuno-Agent: tekos` plus the task tekos declares, tool `confluence.page.search` | 200 |
| an agent name that does not exist | 403 `unknown calling agent` |
| `X-Zuno-Agent: comage` (an agent that does not declare the tool) | 403 `does not declare tool ... (agent_declaration)` |
| no `X-Zuno-Agent` / `X-Zuno-Task` | 403 `missing ... declaration` |
| a persona with the agent group but no business role, tool `aap.platform.audit` declared by tekos | 403 `caller groups ... do not intersect ... allowed_groups` |

A forged agent header narrows what a call may do; the rights stay the intersection with the caller's groups
(ADR-0036). `agent_chain.py` already documents that `X-Zuno-Agent` is not authenticated; nothing is granted by it.

## ai-gateway: platform context headers needed a trusted caller

Before the fix, `X-Zuno-Quota-Class` and `X-Zuno-Project-Id` were taken as sent from any authenticated caller: a
persona chose its own quota class (`intensive`, `stresstest` were routed) and a made-up project id was accepted,
because the path that stripped them (the BFF) no longer exists with UnifAI. These two headers key quota
(ADR-0511, ADR-0528), so a template could not be left to set them (ADR-0563 clause 5).

Fix (ai-gateway, commit 2f981d17, image `ai-gateway-23`): the two headers are honoured only when the token's `azp`
is in `TRUSTED_PLATFORM_CLIENTS` (chart value `trustedPlatformClients`, Ansible
`zuno_ai_gateway_trusted_platform_clients`), empty by default and empty on demo333. For any other caller the gateway
runs the standard class with no project and logs `ignoring platform context headers from untrusted client`.

Live check after the roll (pod `ai-gateway-5d544499cf-9ntp8`): the same persona with `X-Zuno-Quota-Class` set to
`stresstest`, `intensive` and an unknown class, and with a made-up `X-Zuno-Project-Id`, got 200 on `local-maas`
each time (no class 429) and the log carries the ignore line for the client `zuno-evaluations` for every call.
Side effects: the stresstest and `quota_429` scripts in `platform/testing` cannot select a class until their client
is declared trusted; the project dimension is dropped for untrusted callers, and a project id resolved server-side
from a verified grant (ADR-0528) is not implemented.

## Not covered

`X-Zuno-Data-Classification` sent by the caller is accepted as the caller's own claim; the floor against lowering it
is ADR-0565, enforced where the classification is derived (operator), not tested here.
