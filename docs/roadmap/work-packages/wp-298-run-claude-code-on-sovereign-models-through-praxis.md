# WP-298: Run Claude Code on sovereign models through Praxis

- **State:** Operator pending (2026-11-18): the realm client and the entry are live (groups ocp-ai-dev, ocp-ai-ops and consultant); left: step 4 (the `claude-code` experience-client declaration in an agents release) and the workstation coding task of the acceptance
- **ADRs:** [ADR-0619](../../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)
- **Depends on:** [WP-292](wp-292-deploy-praxis-ai-in-the-alternative-gateways-namespace.md)
- **Related:** [ADR-0610](../../adr/0610-generate-blender-objects-as-bpy-scripts-from-a-local-model-through-the-ai-gateway.md)
- **Target:** v0.17
- **Estimated files touched:** ~10: realm, the connectivity-link entry, the praxis NetworkPolicy, evaluations/claude-code

## Goal

From the presenter's workstation, Claude Code works on `qwen3.6-27b-instruct` and `gpt-oss-20b` through Praxis, under the presenter's own Keycloak identity, and nothing leaves the cluster.

## Steps

1. Keycloak client `claude-code` (public, device grant, audience mapper `zuno-admin-api`):
   - in `gitops/charts/keycloak/files/realm-zuno.json`;
   - applied to the live realm, since import is create-only.
2. Workstation host `praxis.<domain>` on `zuno-agent-gateway`, modelled on `gitops/charts/connectivity-link/templates/workstation-entry.yaml`:
   - an HTTPRoute in `zuno-ai-gateways` for `POST /v1/messages`, `POST /v1/messages/count_tokens` and `GET /v1/models`;
   - an AuthPolicy with `allowedClients: [claude-code]`;
   - a per-user RateLimitPolicy;
   - the Praxis NetworkPolicy peer.
3. `evaluations/claude-code/`:
   - an `apiKeyHelper` script: device sign-in, cached refresh token, prints an access token;
   - a `settings.json` example (`ANTHROPIC_BASE_URL`, the model names);
   - a README.
4. Ask the `zuno-demo-agents` session to add the experience-client declaration `claude-code` to the agents release.
5. Live, with the owner's go: the realm, then the entry.

## Acceptance

- The device sign-in works.
- Claude Code finishes a small coding task on `qwen3.6-27b-instruct`.
- The Praxis trace shows the local backend, and no SaaS call is made.
- A token of another client is refused by the AuthPolicy.

## Result (2026-11-17, repo)

Repo work done; nothing is applied to the cluster.

- **Keycloak client `claude-code`** in `gitops/charts/keycloak/files/realm-zuno.json`, copied from `blender`.
  - It is public, with the OAuth device grant only: standard flow, implicit flow, password grant and service account
    are off, and there is no redirect URI.
  - It has the `groups` mapper and the `maas-gateway-audience` mapper (audience `zuno-admin-api`).
  - The live realm: the realm import is create-only, but clients are not. The client-reconcile Job (ADR-0530)
    creates every client of the file that the live realm lacks, at the next sync of the keycloak Application. The
    d1 render puts `client-claude-code.json` in the ConfigMap `zuno-keycloak-clients`. So step 5's realm change is
    that sync, with the owner's go, and no edit by hand.
- **Workstation entry** `gitops/charts/connectivity-link/templates/praxis-workstation-entry.yaml`, modelled on
  `workstation-entry.yaml`. It is off by default (`praxisWorkstationEntry.enabled: false`).
  - The Route is `praxis.<clusterBaseDomain>` on `zuno-agent-gateway`, with a 600 s timeout.
  - The HTTPRoute `praxis-workstation` is in `zuno-ai-gateways`, to `praxis:8080`. It passes `POST /v1/messages`,
    `POST /v1/messages/count_tokens`, `GET /v1/models` and `POST /v1/chat/completions` (the Blender reuse of
    WP-302), as a values list. Everything else is a 404.
  - The AuthPolicy `praxis-workstation-jwt` checks the issuer, the audience `zuno-admin-api` and the azp in
    `allowedClients` (`claude-code`, `blender`). `allowedGroups` is empty by default (any realm user), and a value
    narrows the entry to those groups, as for Blender.
  - The RateLimitPolicy `praxis-workstation` allows 120 requests per user in 5 minutes.
  - The zuno-agent-gateway listener admitted routes from `zuno-ai-run` only. With the entry on, it also admits
    `zuno-ai-gateways`.
  - Off, the chart renders byte for byte the same as before, with the default values and with the d1 values.
  - Not here: the Praxis NetworkPolicy peer for the gateway pod. It belongs to the praxis chart of WP-292, and must
    be on together with the entry.
- **Workstation client** `evaluations/claude-code/`, with its test `evaluations/tests/test_claude_code_token.py`
  (in CI).
  - `zuno_claude_token.py` is the apiKeyHelper. `login` runs the device grant once in a terminal. Without an
    argument, it trades the cached refresh token for a fresh access token on stdout; it never starts a sign-in,
    since Claude Code runs it without a terminal.
  - The cache is `~/.cache/zuno/claude-code/token.json` (0700 and 0600, written atomically). A cache readable by
    others is refused, and no token is ever written to stderr.
  - `settings.example.json`: Praxis as `ANTHROPIC_BASE_URL`; `qwen3.6-27b-instruct` for the model and the opus and
    sonnet aliases; `qwen3.5-9b` for haiku and background tasks; no traffic outside the gateway.
  - A README.
- **Open point for WP-292.** Praxis holds the Anthropic key. Pinning the aliases keeps Claude Code's defaults
  local, but a full SaaS model name typed in `/model` would still reach Claude. To meet "no SaaS call", Praxis must
  refuse SaaS models for the `claude-code` client.
- **Checks:** `helm lint` and `helm template` of connectivity-link (default, d1, d1 with the entry on) and of
  keycloak (d1); `check_docs.py`; the token helper test.
- **Live steps remaining**, each with the owner's go:
  1. the keycloak sync (the client);
  2. the praxis chart with its NetworkPolicy peer (WP-292);
  3. `praxisWorkstationEntry.enabled: true` with `keycloakAcmeWildcardTLS: true` and, preferably, `allowedGroups`
     in `gitops/apps/connectivity-link/application-d1.yaml`;
  4. step 4 of this brief (the agents release).

## 2026-11-18: the entry admits the AI operators and the consultants

- **Owner's decision (2026-11-18).** On demo333, `praxisWorkstationEntry.allowedGroups` is `ocp-ai-dev`, `ocp-ai-ops`
  and `consultant`, in `gitops/apps/connectivity-link/application-d1.yaml`. The other groups (sales, ADV, finance,
  board, recruitment, PaaS) stay out. The client check (azp `claude-code` or `blender`) and Praxis's sovereign-only
  rule for `claude-code` are unchanged.
- **Why it came up.** The first workstation test signed in as `ai-ops-01`, whose Keycloak session was still open in
  the browser. The entry answered 403 with no body. Claude Code retried ten times over about 4 minutes without a
  message, then showed "Failed to authenticate. API Error: 403".
- **Live, 2026-11-18.** Applied by the connectivity-link d1 install, 12:09Z to 12:11Z (an Application change, so
  the role re-applies it; no pod rolled). The AuthPolicy `praxis-workstation-jwt` is Accepted and Enforced with the
  three groups. With a `claude-code` device token, `POST /v1/messages` on `qwen3.6-27b-instruct` through
  `praxis.apps.demo333.startx.fr`:

  | Persona | Result |
  |---|---|
  | `ai-dev-01`, `ai-ops-01`, `consultant-01` | 200 |
  | `sale-01` (none of the three groups) | 403 |

- **Seen on the way.** With `max_tokens: 20` the answer has no text block: the model's reasoning uses the whole
  budget, and the translation drops the reasoning. With 400 the answer is `pong`, in 6 s and 108 output tokens.
  Claude Code asks for far more, so it does not meet this.

## 2026-11-18: Claude Code's first real request reached vLLM untranslated

The owner's dry run on the workstation, as ai-dev-01, went through sign-in and `/status`. The `/status` screen showed
the Praxis base URL, `apiKeyHelper` and `qwen3.6-27b-instruct`. Then the first prompt failed with `API Error: 400
25 validation errors`, `body.tools[0].function: Field required`: vLLM had received Claude Code's tools in the
Anthropic shape. The Praxis log shows the request on the `maas` step, which answered 400.

**Cause.** `anthropic_messages_to_chat_completions` rewrites the request body only once an upstream is selected
(`on_selected_upstream_request_body`). In our chart it sat in the main chain, but the upstreams are selected inside the
router steps (`maas`, then `direct`), so it never rewrote a body. Plain prompts still passed, because vLLM reads a
text-only Messages body as a Chat Completions one. The tests of 2026-11-17 and 11-18 used only such prompts, so they
did not catch it. The spike of WP-292 had no router, and there the translation worked.

**Reproduced and fixed locally:**
- **Setup:** the deployed image (`e319e228…`), the live configuration with only the cluster-specific filters
  replaced, and a real Claude Code 2.1.325 request (21 tools, `stream: true`, `thinking: adaptive`) captured against
  a local stub.
- **Before:** the body reached the stub unchanged.
- **After:** the filter sits in each step, just before the step's `load_balancer` (`praxis.messagesToChat`). The
  request arrives in Chat Completions form, with `tools[].function`, `max_completion_tokens`, `reasoning_effort` and
  `stream_options`. This holds on the `maas` step and on the `direct` step after a MaaS 503.
- **Streamed answers:** text and tool calls are translated back to Anthropic events (`text_delta`, `tool_use`,
  `input_json_delta`, `stop_reason: tool_use`).
- **OpenAI requests** on `/v1/chat/completions` are untouched on both steps.

`praxis-ai --validate` accepts the rendered configuration, as it accepts the live one. For this check, the
credential file watcher was removed, because the workstation's inotify limit was reached.

**Not yet proven:** the live sign-in and the coding task after the roll.

**Second error after the fix (22:53):** `API Error: 400 System message must be at the beginning`.
- **Cause:** Claude Code 2.1.325 sends its environment block as a second `system` message, placed after the first
  user turn, and the Qwen chat template refuses a system message anywhere but first.
- **Fix:** the client setting `CLAUDE_CODE_MODEL_CAPABILITIES=-mid_conv_system`, added to `settings.example.json`
  and to the README table. Claude Code then puts the block in the user turn as a `<system-reminder>`.
- **Checked locally:** through the same Praxis rig, the request reaches the model as `system`, then `user`, with the
  21 tools in `function` form.

**Third error (23:05):** vLLM answered `maximum context length is 32768 tokens. However, you requested 32000 output
tokens`.
- **Cause:** Claude Code does not know the model, so it asks 32000 output tokens. Its base prompt with all 21 tools
  is about 20k tokens (73 KB).
- **Fix:** the settings now set `CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192` and `CLAUDE_CODE_MAX_CONTEXT_TOKENS=32768`, the
  model's window. They also deny every tool but `Bash`, `Read`, `Edit` and `Write`.
- **Checked:** a request captured with these settings carries four tools, `max_tokens` 8192 and 15 KB, about 4k
  tokens.

**After these fixes (23:17–23:19):**
- **What works:** `pong`, a short conversation, and the coding task up to the two `Write` calls. `fib.py` and
  `test_fib.py` were written through Praxis to `qwen3.6-27b-instruct`.
- **What failed:** the `Bash` call that runs the test.
  - Claude Code was in its "Auto" permission mode, which first asks the model whether the command is safe. That
    request got 400 from vLLM, so Claude Code refused the command.
  - It then sent the refusal as a `tool_result` with `is_error: true`. Praxis refuses to translate such a result, by
    design (its test `tool_result_error_is_rejected`), and answered 400 `tool_result requires string tool_use_id and
    text content`.
- **Settings now:**
  - `permissions.defaultMode: default`, and `claudeCode.initialPermissionMode: default` in the extension, so
    Claude Code asks the presenter before it runs a command.
  - Limit: any failed tool still ends the turn. Fixing that needs a change in Praxis's translator and a rebuild of
    the image, after the 2026-11-24 demo.
