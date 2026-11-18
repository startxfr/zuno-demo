# Claude Code on sovereign models through Praxis (ADR-0619)

Claude Code on a presenter's workstation, working on the cluster's own models through the Praxis alternative AI
gateway, under the presenter's own Keycloak identity
([ADR-0619](../../docs/adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)
clause 8, [WP-298](../../docs/roadmap/work-packages/wp-298-run-claude-code-on-sovereign-models-through-praxis.md)). It
is the second workstation experience. The Blender add-on of [ADR-0610](../blender/README.md) is the first, and this
client copies its pattern.

| File | What it is |
|---|---|
| `zuno_claude_token.py` | Claude Code's `apiKeyHelper`: `login` signs in once (device grant), then each run prints a fresh access token. |
| `settings.example.json` | The Claude Code settings: the helper, Praxis as the base URL, local models only, no traffic outside the gateway. |

The test is `evaluations/tests/test_claude_code_token.py` (no network).

## The chain

```text
claude (workstation)
  -> https://praxis.<domain>/v1/messages            Authorization: Bearer <the presenter's access token>
  -> zuno-agent-gateway (gitops/charts/connectivity-link, templates/praxis-workstation-entry.yaml)
       AuthPolicy: Keycloak issuer, audience zuno-admin-api, azp claude-code or blender, optional groups
       RateLimitPolicy: requests per user
  -> praxis:8080 in zuno-ai-gateways, which verifies the token again and calls the local model
```

Keycloak client `claude-code`: public, OAuth device grant only. It has no secret, no redirect, no password grant and
no browser flow. Its two mappers are the same as `blender`'s: `groups`, and the audience `zuno-admin-api`
(`gitops/charts/keycloak/files/realm-zuno.json`).

The entry opens four requests only: `POST /v1/messages`, `POST /v1/messages/count_tokens`, `GET /v1/models` and
`POST /v1/chat/completions` (the last for the Blender add-on's reuse, WP-302). Everything else gets a 404 at the
gateway, including Claude Code's startup probe `HEAD /api/hello`, which it does not need.

## Set up a workstation

1. Python 3.8 or newer, and Claude Code.
2. Install the helper:

   ```bash
   install -m 0755 evaluations/claude-code/zuno_claude_token.py ~/.local/bin/zuno_claude_token.py
   ```

3. Copy the settings and set the cluster's domain in `ZUNO_CLUSTER_DOMAIN` and `ANTHROPIC_BASE_URL`:

   ```bash
   install -d -m 0700 ~/.config/zuno/claude-code
   install -m 0600 evaluations/claude-code/settings.example.json ~/.config/zuno/claude-code/settings.json
   ```

4. Sign in once, in a terminal, as a member of the admitted group:

   ```bash
   ZUNO_CLUSTER_DOMAIN=apps.demo333.startx.fr ~/.local/bin/zuno_claude_token.py login
   ```

   Open the page it shows, type the code and sign in with the company account. If the browser already holds another
   Keycloak session, sign out of it first.
5. Start Claude Code in a project directory:

   ```bash
   env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN claude --settings ~/.config/zuno/claude-code/settings.json
   ```

   `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` take precedence over `apiKeyHelper`, so they must not be set.

To end the session: `~/.local/bin/zuno_claude_token.py logout`. It ends the Keycloak session and deletes the cached
refresh token.

## What the helper does

- **`login`.** It runs the device grant of `claude-code` against `https://keycloak.<domain>/realms/zuno`. It shows the
  user code and the verification page on the terminal and polls until the person has signed in. Then it caches the
  refresh token.
- **No argument.** This is what Claude Code runs. It trades the cached refresh token for a new access token and
  prints that token on stdout.
  - Keycloak rotates the refresh token, so the helper caches the new one.
  - It never starts a sign-in: Claude Code runs it without a terminal. With no cached sign-in, or one Keycloak
    refuses, it writes "run `login`" on stderr and exits 1.
- **Re-runs.** Claude Code runs it again every `CLAUDE_CODE_API_KEY_HELPER_TTL_MS` (10 minutes in the example;
  Keycloak's access token lives 15) and after a 401 or 403.
- **The cache.** It is `~/.cache/zuno/claude-code/token.json`: directory 0700, file 0600, written atomically. It
  holds the refresh token, its issuer, client and end time, and nothing else. A cache that other users can read is
  refused, never used.
- **Secrets.** No token or device code is ever written to stderr, a log or an error message. Errors carry HTTP
  statuses and Keycloak error names only. The refresh session ends with Keycloak's SSO maximum (10 hours); then run
  `login` again.

## Why each setting

| Setting | Why |
|---|---|
| `apiKeyHelper` | Claude Code sends the helper's output in the `Authorization` (Bearer) and `x-api-key` headers. The AuthPolicy reads the Bearer one. |
| `ANTHROPIC_BASE_URL` | Praxis's workstation host. Claude Code calls `POST /v1/messages?beta=true` there (a path match ignores the query string). |
| `ANTHROPIC_MODEL` | `qwen3.6-27b-instruct`, the main local model. |
| `ANTHROPIC_DEFAULT_OPUS_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL` | Also `qwen3.6-27b-instruct`, so the `/model` aliases stay on local models. |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL`, `ANTHROPIC_SMALL_FAST_MODEL` | `qwen3.5-9b` for background tasks. The second is the deprecated name, kept for older Claude Code versions. |
| `CLAUDE_CODE_API_KEY_HELPER_TTL_MS` | 600000 (10 min), under the 15-minute access token. |
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` | No auto-update, telemetry, error reporting, feedback or release notes: no call outside the gateway. |
| `skipWebFetchPreflight` | The WebFetch tool's domain check calls `api.anthropic.com` otherwise. |
| `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` | Strips pre-release `anthropic-beta` headers and fields that a translating gateway may refuse. |

Model discovery (`GET /v1/models`) is off by default in Claude Code; `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1`
turns it on, and the entry passes it.

## Limits

- Pinning every alias to a local model keeps the default choices local. It does not stop a person from typing a
  SaaS model's full name in `/model`. Praxis holds the Anthropic key (ADR-0619 clause 3), so only Praxis can refuse
  SaaS models for the `claude-code` client. That rule belongs to Praxis's configuration (WP-292), not to this client.
- Claude Code's prompts are written for Claude models. A local model follows them less well; the WP-298 acceptance
  is a small coding task.

## Tests

```bash
python3 evaluations/tests/test_claude_code_token.py   # the cache, the refresh, the device polling, stderr
```
