# WP-194: "Zuno Code" in Open WebUI and OpenClaw: Codestral first, local models as fallback

- **State:** Done (2026-11-05, [evidence](../evidence/wp-194-zuno-code-live-proof.md))
- **ADRs:** [ADR-0596](../../adr/0596-let-experience-clients-pick-a-declared-code-model-routed-to-codestral-first.md), [ADR-0594](../../adr/0594-give-the-three-experiences-the-same-mcp-tools-behind-signed-classification-markers.md), [ADR-0592](../../adr/0592-declare-experience-clients-in-the-agents-release-apart-from-agents.md)
- **Depends on:** [WP-193](wp-193-open-webui-user-experience.md), [WP-189](wp-189-experience-clients-in-the-agents-release.md)
- **Target:** v0.13
- **Estimated files touched:** ~12 (agents repo: two task files, client checks; zuno-demo: generator and its tests,
  ai-gateway `main.py`/`telemetry.py` and tests, `gitops/charts/ai-gateway`, `gitops/charts/open-webui/values.yaml`,
  `gitops/charts/openclaw/templates/claw.yaml`, demo script, docs)

> Why: on 2026-11-04 a code question asked in Open WebUI and OpenClaw (sale-01, consultant-01, consultant-02) was always
> answered by the local qwen3.6-27b-instruct. The experience clients have no task that prefers Codestral, and their
> menu shows `auto` alone. User decision of 2026-11-04: option A, a declared "Zuno Code" model with Codestral first and
> the local models as fallback.

## Goal

A user picks "Zuno Code" in Open WebUI or OpenClaw and asks a code question without tools. Codestral answers. If
Codestral fails, qwen answers in the same turn. A turn with a tool result stays local, as ADR-0594 requires.

## Steps

1. **Agents release** (zuno-demo-agents, PR to `devel`):
   - `experience-clients/open-webui/tasks/code.md` and `experience-clients/openclaw/tasks/code.md`: `type: task`,
     `zuno.models.preferred: [code]`, `allowed_tools: []`.
   - Add `code` to `zuno.tasks` in both `client.okf.md` files.
   - Client checks (`validate_client`, and `admit_okf_bundle.py` in the signer image): accept a task with no tools and
     with `zuno.models`. Tests.
   - The user cuts the release; the promotion PR moves `platform/okf/agents.lock`.
2. **Generator** (`platform/okf/generate_stack_config.py`): `model_routing` also reads the experience clients' tasks,
   with the same steps 1 to 4. MaaS subscriptions and guardrail modes stay agents-only.
   - Tests: `open-webui`/`code` and `openclaw`/`code` get `prefer: [mistral-codestral, ...]`, no `strict`, the corp
     order after it; `chat` gets no entry.
   - `--check` passes; `model-routing.generated.yaml` is regenerated from the promoted release.
3. **ai-gateway**:
   - `GET /v1/models` for an experience client returns `auto` ("Zuno") and `zuno-code` ("Zuno Code").
   - `POST /v1/chat/completions` for an experience client with `model` in `MODEL_TASK_ALIASES` (default
     `zuno-code=code`) uses that task in place of `X-Zuno-Task`. The table is a chart value.
   - `model_call` spans carry `zuno.task`.
   - Tests:
     - a `zuno-code` call at C1 lists `mistral-codestral` first;
     - the same call with an unmarked `tool` message is local-only;
     - a `zuno-code` call from a non-experience client keeps its header task;
     - an unknown `model` behaves as `auto`;
     - Codestral raising makes `local-maas` answer.
   - Build and roll after the user's go.
4. **Clients:**
   - OpenClaw (`claw.yaml`): add `{name: zuno-code, alias: zuno-code}` to the `zuno` provider's models.
   - Open WebUI (`values.yaml`): no `model_ids` change, since the list comes from the ai-gateway. The banner adds one
     sentence: "Zuno Code may send your conversation to Mistral; tool turns stay on local models."
   - Each chart is changed by its owner session, which pushes with its user's go.
5. **Prove it live** on demo333, as consultant-01 (Open WebUI) and consultant-02 (OpenClaw), with "write Python code
   that checks the format of an email address":
   - in Open WebUI, "Zuno Code" without tools is served by `mistral-codestral`, and "Zuno" by `local-maas`;
   - in OpenClaw, the first call is served by `mistral-codestral`; after an `exec` the calls are C2 and local;
   - with the Codestral key replaced by an invalid one in a scratch test (or the breaker forced open), the turn is
     answered by `local-maas` and the span records the failed candidate;
   - the tokens show under the persona's budget.

   For each case, record the provider, the tokens and the duration from the `model_call` spans.
6. **Close:**
   - evidence `docs/roadmap/evidence/wp-194-*.md`;
   - `docs/demo/three-experiences.md` updated;
   - ADR-0596 set to Implemented, with the notes on ADR-0588 and ADR-0592.

## Acceptance

On demo333, all of the following hold:
- Open WebUI and OpenClaw list Zuno and Zuno Code;
- a tool-free C1 code turn on Zuno Code is served by `mistral-codestral`;
- the same turn falls back to `local-maas` when Codestral fails;
- a turn with a tool result is local;
- `generate_stack_config.py --check`, the agents repository checks and the ai-gateway suite pass with no new failure.

## Coordination

- The agents repository change goes through a PR to `devel`. The user cuts the release and merges the promotion PR.
- `gitops/charts/open-webui` and `gitops/charts/openclaw` belong to their owner sessions. They get the diff and push
  with their user's go.
- Every build, roll and sync is announced first and needs the user's go in the session that runs it.
