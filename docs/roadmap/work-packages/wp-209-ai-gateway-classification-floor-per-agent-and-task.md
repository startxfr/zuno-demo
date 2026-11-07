# WP-209: ai-gateway classification floor per agent and task

- **State:** Done (2026-11-07) - live on demo333: ai-gateway image `d849b322` (build ai-gateway-47 from 11c12da9),
  floors on, probe as expected. The header-less default stays `C1` by user decision, so ADR-0565 stays
  `Partially implemented` until that is decided (see "Live verification (2026-11-07)")
- **ADRs:** [ADR-0565](../../adr/0565-derive-data-classification-from-okf-and-only-allow-raising-it.md)
- **Depends on:** none
- **Blocks:** WP-225 (builds on `app/classification_floor.py`)
- **Related:** [ADR-0594](../../adr/0594-give-the-three-experiences-the-same-mcp-tools-behind-signed-classification-markers.md) (signed markers already raise a turn), [WP-187](wp-187-carry-the-source-classification-through-unifai-rag-results.md), [WP-191](wp-191-same-mcp-tools-in-the-three-experiences.md)
- **Target:** v0.15
- **Estimated files touched:** ~8: `platform/okf/generate_stack_config.py`, a new `gitops/charts/ai-gateway/files/classification-floors.generated.yaml` and its ConfigMap template, `components/ai-gateway/app/main.py` and a new floor module, their tests, the CI drift check

> Why: ADR-0565 clause 5 asks the ai-gateway to enforce a per-(agent, task) classification floor itself, so a caller cannot lower the level by sending a lower header. It is the one clause of ADR-0565 that has no code. The operator validation and bundle overrides (WP-150) and the per-chunk classification (WP-187) are done, and ADR-0594 raises the turn from signed markers, which covers clause 3 in practice.

## Goal

`effective = max(header, floor(agent, task))` in the ai-gateway, with the floors generated from the admitted bundles, and an absent classification header treated as `C3` instead of `C1` once no current caller depends on the old default.

## Steps

1. **Inventory the callers that send no `X-Zuno-Data-Classification`.** Candidates named by the ADR: the mcp-gateway built-in tools and the acceptance gate. Add the three experiences (Open WebUI, OpenClaw, Dify) and kagent. The header defaulted to `C1` (`components/ai-gateway/app/main.py`, three handlers). **Done, see the table below.**
2. **Generate the floor slice.** Same pattern as `guardrails-modes.generated.yaml` and `model-routing.generated.yaml`: `platform/okf/generate_stack_config.py` writes it from the agents release, a ConfigMap mounts it, and a CI drift check fails when the file differs from the bundles. **Done.**
3. **Enforce it in the gateway.** Compute the effective level from the header and the floor of the calling agent and task, as `local_only_for` is already ORed into the caller's local-only flag. Log a raised level. **Done, not live.**
4. **Change the default.** Treat an absent header as `C3` only after step 1 shows which callers must send a header; fix those callers first. A cluster with callers that cannot send one keeps `C1` until they do. **Built behind a chart value, kept at `C1` (user decision 2026-11-07).** The callers to fix before the flip are listed below.
5. **Record the partial supersession.** ADR-0565 clause 3 (the session carries a monotone level) is covered in practice by ADR-0594's signed markers; say so in the ADR when this WP closes. **Done (note of 2026-11-07 in the ADR).**

## Caller inventory (step 1, 2026-11-07)

Every caller of the ai-gateway found in this repository, the UnifAI fork (read only) and demo333 (`oc get unifaillm`,
read only). "Header" is what the caller sends on its model calls; the `/mcp` connections of the experience clients send
`C2` and are not ai-gateway calls.

| Caller | Endpoint | `X-Zuno-Data-Classification` | `X-Zuno-Agent` / `X-Zuno-Task` | With a `C3` default |
|---|---|---|---|---|
| UnifAI agent bundles (operator-emitted `UnifaiLLM`, one per task; ADR-0563) | chat | yes: the bundle level, raised by `classificationOverrides` and delegation targets (live: arkos C3, comage C2, tekos C1, `tekos-answer-technical-question` C2) | yes: bundle name / task | unchanged |
| **UnifAI shared `zuno-gateway` LLM** (`gitops/charts/unifai/templates/_helpers.tpl` `unifai.gatewayLLMConfig`): catalog templates `zuno-chat` and `zuno-tools-agent`, the team examples `<team>-assistant`, `-orchestrator`, `-rag`, `-tools`, the personal `<user>-assistant` and `<user>-rag`, any workflow a user builds on it, the WP-175 test blueprints (`platform/testing/seed_persona_blueprints.py`) | chat | **no** (only `X-Zuno-Run-Id`) | **no** | **every call becomes local-only**: SaaS models disappear from all hand-built and example UnifAI workflows |
| Open WebUI (`gitops/charts/open-webui/values.yaml`, `OPENAI_API_CONFIGS`) | chat, models | yes: `C1` | `open-webui` / `chat` (Zuno Code via `model_tasks`) | unchanged |
| OpenClaw (`gitops/charts/openclaw/templates/claw.yaml`, `zuno-ai` credential) | chat, models | yes: `C1` (`gateways.dataClassification`) | `openclaw` / none (task from the model, ADR-0596) | unchanged |
| Dify via zuno-token-proxy (`ansible/roles/dify/defaults/main.yml` `dify_ai_headers`) | chat | yes: `C1` | `dify` / `chat` | unchanged |
| kagent via zuno-token-proxy (`ansible/roles/kagent/defaults/main.yml` `kagent_ai_headers`) | chat | yes: `C1` | `kagent` / `diagnose` | unchanged |
| a2a-gateway (`components/a2a-gateway/app/clients.py`) | chat | yes: max of the target agent's level and the caller's | yes: target agent / task | unchanged |
| mcp-gateway built-in tools: only `image.generation.create` calls the ai-gateway (`app/handlers/image_gen.py`); `diagram_gen` and the others do not | images | yes: `C2` (ADR-0415) | no (the images endpoint takes none) | unchanged |
| Acceptance gate and day-2 stresstest: `evaluations/*/security_checks.py` `ai_gateway_local_only_forces_local_provider` | chat | yes: `C2` + `X-Zuno-Local-Only: true` | no | unchanged |
| Acceptance gate scenarios (`evaluations/tekos/run_scenarios.py`) | via UnifAI | as the UnifAI bundles | as the UnifAI bundles | unchanged |
| `platform/testing/token_quota_429.py` (day-2 `token_quota`) | chat | **no** | no | routed local-only; the 429 is decided before dispatch, so the check still holds, the burst is slower |
| `platform/testing/quota_counters_probe.py` | chat | **no** | no | routed local-only; the probe targets a local model's counters, unchanged |
| Open WebUI and Dify prechecks (`ansible/roles/open_webui/tasks/precheck.yml`, `ansible/roles/dify/files/probe.py`) | models, no token | no | no | unchanged (they expect 401) |

Not ai-gateway callers: OpenShift Lightspeed, the RHOAI portal playground and Claude Code (`/v1/messages`) go to MaaS
directly. The mcp-gateway's own REST endpoint `/v1/tools/{name}/invoke` also defaults its header to `C1`; that is a
second, separate default (ADR-0565 Context) and out of this WP.

### Callers that must send a header before `defaultWhenAbsent: C3`

1. **The UnifAI shared `zuno-gateway` LLM** (blocking). It is the one caller whose traffic changes. Fix in this repo:
   add `X-Zuno-Data-Classification` to `default_headers` in `unifai.gatewayLLMConfig`. Options, for the user:
   - **A (preferred): `C1` explicitly**, today's behaviour made visible; the turn is still raised by the signed markers
     (ADR-0594), so a Confluence or knowledge-base result keeps the rest of the run at C2.
   - B: `C2`, if team and personal uploads (`<team>-rag`, `<user>-rag`) are to be treated as internal by default.
   - C: no header, and accept that the flip makes every hand-built workflow local-only.
   It needs no UnifAI release: the chart renders the `UnifaiLLM` and the catalog templates; the WP-175 blueprints
   (`seed_persona_blueprints.py`) carry their own copy of `default_headers`.
2. `platform/testing/token_quota_429.py` and `platform/testing/quota_counters_probe.py` (not blocking): send `C1`
   so they keep measuring the same path.

No caller in the agents repository needs a change: the bundles carry no header; the operator writes it.

## What was built (2026-11-07)

1. **Generator.** `platform/okf/generate_stack_config.py` writes a fifth file,
   `gitops/charts/ai-gateway/files/classification-floors.generated.yaml`: for every agent of the release (served or not)
   `floor` = `zuno.model.preferred_classification`, and the same level under each task. OKF has no task-level level
   today: a prompt slot's `classification_ceiling` was an agent-runtime ceiling and the unifai-operator does not read it
   (its task level is the bundle level, raised by overrides), so the floor equals what the operator already sends.
   An unknown or missing level is refused (`AdmissionError`). Experience clients get no floor: their `classification`
   (C2) is the level of their MCP calls, and their model calls stay C1 until a marker raises them (ADR-0594); a C2 floor
   would make every Open WebUI turn local. Release v0.14.2: arkos, cognos C3; advantage, comage, finage, soursage C2;
   naveo, tekos C1.
2. **Drift check.** The file is part of `outputs()`, so `generate_stack_config.py --check` (CI step "Generated stack
   configuration matches the locked release") fails on a stale copy, and `okf-promote.yml` commits it with the others.
   `test_the_drift_check_fails_on_a_stale_floor_file` proves it.
3. **Chart.** `templates/configmap-classification-floors.yaml` (wave 55), the mount `/app/config-classification` and
   `CLASSIFICATION_FLOORS_PATH`, behind `classification.floorsGenerated` (default `false`; the default render only gains
   `CLASSIFICATION_DEFAULT_WHEN_ABSENT="C1"`). `classification.defaultWhenAbsent` (default `C1`) becomes
   `CLASSIFICATION_DEFAULT_WHEN_ABSENT`; the template fails on anything but C1, C2, C3. The llm role passes
   `zuno_ai_gateway_classification_floors_generated` and `zuno_ai_gateway_classification_default_when_absent`.
4. **Gateway.** `app/classification_floor.py` (no FastAPI import, for WP-225): `declared_level(header)` (header or the
   default), `ClassificationFloors.effective(declared, agent, task)` returning a `FloorDecision` (declared, floor,
   effective, raised), reloaded by the routing watcher. A known agent with an unknown task gets the agent floor; an
   unknown agent gets none; an unknown header is returned unchanged so routing still answers 422.
   `/v1/chat/completions` computes the effective level first, logs
   `classification raised by floor: C1 -> C3 agent=... task=... client=...`, and uses it for `local_only_for`, the
   markers, the candidates, the guardrails mode, the semantic-cache key, the `model_call` span (`zuno.classification`)
   and the routing decision. `/v1/models` and `/v1/images/generations` take the default only (the images endpoint has
   no agent header and keeps ADR-0415's scoped C2).
5. **Tests.** `components/ai-gateway/tests/test_wp209_classification_floor.py` (16, added to the CI list), including a
   `C1` header from `cognos` routed to the local provider with the span and routing decision at `C3`, a C2 floor that
   triggers a C2-only `local_only_for`, and a header-less call at C1 (default) and C3. 5 generator tests.

## Verification (2026-11-07)

- **ai-gateway suite** (pytest, throwaway venv): 392 passed, 1 failed. The failure,
  `tests/test_reply_cap.py::test_the_cap_shrinks_to_the_room_left_in_the_model_window` (`assert 6517 == 7767`), fails
  the same way on the base commit 2befc90a (376 passed, 1 failed); the 16 new tests are the difference. The CI list of
  `lint.yml` passes script by script.
- **Generator.** `test_generate_stack_config.py` 46 tests OK. Before regenerating, `--check` printed
  `RESULT: FAIL - gitops/charts/ai-gateway/files/classification-floors.generated.yaml is stale`; after, PASS for the
  five files. The four existing files are byte-identical.
- **Chart.** `helm template` renders the default with no floor ConfigMap or mount; with
  `classification.floorsGenerated=true,classification.defaultWhenAbsent=C3` it renders the ConfigMap, the mount and both
  env vars; `defaultWhenAbsent=C4` fails the render. `helm lint` passes.
- **Docs.** `check_docs.py` PASS.

## Operator steps and live probe

With the user's go, on demo333 (`--context` explicit on every `oc` command, ADR-0559):

1. Push, then `make d1 build ai-gateway` and check that the running image carries this commit.
2. Set `zuno_ai_gateway_classification_floors_generated: true` in `ansible/clusters/demo333.yml` (leave
   `zuno_ai_gateway_classification_default_when_absent` unset, C1), then `make d2 install llm`.
3. The gateway logs `loaded classification floors from /app/config-classification/classification-floors.yaml (8 agent(s))`.
4. Probe: a `C1` header claiming `cognos` must be routed local and recorded at `C3`; a control call claiming `tekos`
   stays at `C1`; a header-less call stays at `C1`.

```bash
CTX=startx/api-demo333-startx-fr:6443/kube:admin
S=$(oc --context "$CTX" -n zuno-ai-run get secret acceptance-gate-credentials -o json)
TOKEN=$(curl -s https://keycloak.apps.demo333.startx.fr/realms/zuno/protocol/openid-connect/token \
  -d grant_type=password -d client_id=zuno-evaluations -d username=consultant-01 \
  --data-urlencode client_secret="$(jq -r '.data["eval-client-secret"]|@base64d' <<<"$S")" \
  --data-urlencode password="$(jq -r '.data["demo-persona-password"]|@base64d' <<<"$S")" | jq -r .access_token)
unset S
for case in "C1 cognos coming-soon" "C1 tekos answer-technical-question" "- - -"; do
  printf '%s' "$TOKEN" | oc --context "$CTX" -n zuno-ai-run exec -i deploy/ai-gateway -c ai-gateway -- \
    python3 -c '
import sys, uuid, httpx
level, agent, task = sys.argv[1:4]
token = sys.stdin.read().strip()
rid = "wp209-" + uuid.uuid4().hex[:8]
h = {"Authorization": "Bearer " + token, "X-Zuno-Request-Id": rid}
if level != "-": h["X-Zuno-Data-Classification"] = level
if agent != "-": h.update({"X-Zuno-Agent": agent, "X-Zuno-Task": task})
base = "http://127.0.0.1:8080/v1"
r = httpx.post(base + "/chat/completions", headers=h, timeout=180,
               json={"model": "auto", "messages": [{"role": "user", "content": "Say OK."}], "max_tokens": 16})
d = httpx.get(base + "/routing-decisions/" + rid, headers={"Authorization": "Bearer " + token}, timeout=10)
print(sys.argv[1:4], r.status_code, d.json() if d.status_code == 200 else d.status_code)
' $case
done
unset TOKEN
oc --context "$CTX" -n zuno-ai-run logs deploy/ai-gateway -c ai-gateway --since=10m | grep "classification raised by floor"
```

If WP-222's audience flag is live by then and the `zuno-evaluations` token is refused (401), take the token of a client
that carries the `zuno-admin-api` audience instead; the probe is otherwise unchanged.

Expected: `['C1', 'cognos', 'coming-soon'] 200 {... 'kind': 'local', 'classification': 'C3' ...}`, the tekos and
header-less cases at `C1`, and exactly one log line
`classification raised by floor: C1 -> C3 agent=cognos task=coming-soon client=zuno-evaluations`.

## Acceptance

- A request with a header lower than the agent's floor is routed and counted at the floor, with a unit test and a live probe through the gateway. **Unit test done; live probe pending (above).**
- Without a header, the request is treated as `C3` and no listed caller breaks (`make d3 test` and the three experiences' checks stay green). **Deferred by user decision: the default stays `C1`; the flip waits for the UnifAI shared LLM to send a header (option A, B or C above).**
- The drift check fails on a stale floor file. **Done (unit test and a real `--check` run).**

### Known gap (review, 2026-11-07)

The (agent, task) key comes from `X-Zuno-Agent` / `X-Zuno-Task`, which the caller sets. ADR-0565 accepts this only
because a caller that omits them falls to the C3 default. With the default at `C1`, a caller that sends `C1` and
omits the agent, names an unknown agent, or claims a C1-floor agent (`tekos`) is not raised. The floor therefore
protects against a mis-rendered level on a correctly identified agent, not against a hand-written UnifAI LLM resource.
Even after the flip to C3, claiming the lowest-floor agent still lowers the call. Closing it needs a verifiable agent
identity (an operator-signed header in the style of the ADR-0594 markers, or the `agent_chain` of WP-225 lot C).
Agent and task now match case-insensitively, so `Cognos` no longer escapes the `cognos` floor.

User decision (2026-11-07): a **per-client floor** (`classification.clientFloors`, Ansible
`zuno_ai_gateway_classification_client_floors`, e.g. `{unifai: C2}`) applies when a call names no known agent, so a
UnifAI token can no longer drop below it by omitting or inventing `X-Zuno-Agent`. It ships empty (today's behaviour)
and is switched on per cluster with the live probe. A caller that claims a known low-floor agent is closed by WP-225
lot C (verifiable agent identity).

WP-225 lot C (2026-11-07, Operator pending) provides that identity: the a2a-gateway signs `X-Zuno-Agent-Chain` (the agent
it runs, its task and the checked delegators, bound to the bearer, 60 s). With `agentChain.verify` and the public key set
on the ai-gateway, the floor keys on the verified agent, and a disagreeing `X-Zuno-Agent` is ignored and logged. This closes
the gap when the chain is verified, that is for the turns the a2a-gateway runs. Since the lot C review, a call without a
valid chain gets the higher of the named agent's floor and the per-client floor (no longer the agent's instead of the
client's), so claiming a low-floor agent cannot drop a UnifAI call below `classification.clientFloors` either; and
`agentChain.requireFor` can ignore the agent header of a listed client that sends no valid chain. UnifAI's direct
calls, whose headers are static, stay covered by the client floor until UnifAI signs its own calls (the follow-up in
the WP-225 brief).

## Live verification (2026-11-07)

With the user's go, on demo333: `make d1 build ai-gateway` (build `ai-gateway-47`, commit `11c12da9`, digest
`d849b322...`, the first image on the WP-226 hashed lock), `zuno_ai_gateway_classification_floors_generated: true` in
`ansible/clusters/demo333.yml` (default `C1` and the per-client floor left unset), `make d2 install llm`.

- ConfigMap `ai-gateway-classification-floors`: 8 agents (arkos, cognos `C3`; advantage, comage, finage, soursage `C2`;
  naveo, tekos `C1`); the pod mounts it at `/app/config-classification`, `CLASSIFICATION_DEFAULT_WHEN_ABSENT=C1`.
- Probe (the brief's script, `zuno-evaluations` token of consultant-01, accepted):
  `['C1','cognos','coming-soon'] 200 kind=local provider=local-qwen35-maas classification=C3`,
  `['C1','tekos','answer-technical-question'] 200 classification=C1`, header-less `200 classification=C1`, and exactly
  one log line `classification raised by floor: C1 -> C3 agent=cognos task=coming-soon client=zuno-evaluations`.
- After the roll: `/readyz` 200, no error in the pod log, acceptance gate PASS 17/18 (scenario 11, the RAG citation,
  failed with no tool call, as on 0.1.62 the same morning), 14/14, 5/5.
- Finding: the startup line `loaded classification floors from ... (8 agent(s))` is never logged. `ClassificationFloors`
  is built at import time, before logging is configured, so its INFO line is dropped; the floors are loaded (the probe
  proves it). Cosmetic: log it again after logging setup, or check the ConfigMap instead of the line.
