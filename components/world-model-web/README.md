# world-model-web

ADR-0604, WP-234. The browser side of the world-model demo: a FastAPI service (identity, the GPU lease, prompt screening and
enhancement, the video relay) and the React + PatternFly UI it serves. It owns no model: `world-model-runtime` does, and this
service is its only client.

## API

| Route | What it does |
|---|---|
| `GET /api/me`, `/api/presets`, `/api/status` | Who you are; the curated scenes; runtime readiness, busy or not, engine/encoder in use |
| `POST /api/worlds` | `{preset_id \| prompt, seed?}`: screens the prompt, takes the GPU lease, builds the world (409 busy, 429 hourly limit, 503 runtime not ready, 422 prompt refused) |
| `GET/DELETE /api/sessions/{id}` | Your session; release it (owner, or ops for someone else's) |
| `POST /api/sessions/{id}/prompts` | A mid-session prompt: screened, enhanced, numbered, sent as a world edit (202) |
| `POST /api/sessions/{id}/reset` | Rebuild the world from its first image |
| `POST /api/sessions/{id}/client-stats` | `{fps?, latency_ms?}` measured in the browser (bounded) |
| `WS /api/sessions/{id}/stream` | Controls up (validated); state events and binary H.264 video down |
| `/healthz`, `/readyz`, `/metrics`, `/` | Probes, Prometheus, the built UI |

## Rules enforced here

- **Identity** comes from the validated Keycloak token only (signature through the realm JWKS, issuer, audience `zuno-admin-api`,
  expiry), taken from `Authorization: Bearer` or the oauth2-proxy's `X-Forwarded-Access-Token`. Access needs a group of
  `ALLOWED_GROUPS` (`zuno-world-model-users`, `ocp-ai-ops`, `ocp-paas-ops`). A header never grants identity or groups.
  `WORLD_MODEL_AUTH=dev` exists for a local run only; the chart never sets it and the default is `oidc`.
- **One world per GPU.** The lease is taken before the slow image generation, so a second visitor is told "busy" at once. A
  session belongs to its creator; ops groups may release any. Limits: idle (`SESSION_IDLE_SECONDS`), detached (the tab closed,
  `SESSION_DETACHED_SECONDS`), total length, and `WORLDS_PER_HOUR` per user.
- **Prompts** (ADR-0604 D8): length, control characters and a deny list always; then, when `AI_GATEWAY_URL` is set, one C1
  local-only chat call with the user's own token that screens and rewrites. If the gateway fails, the filtered prompt is used and
  the UI says enhancement is off. The model's reply is data and goes through the local checks again. A prompt only enters through
  `POST .../prompts`: an `edit` message sent over the WebSocket is dropped.
- **Stream**: Origin checked, controls validated and bounded, one viewer per session, no payload ever in a metric label.

## Run and test without a GPU

```bash
cd components/world-model-web
pip install -r requirements.txt pytest
python -m pytest -q tests                      # 28 tests: real JWTs, a fake runtime over a real socket, mutation-checked

cd ui && npm ci && npm run typecheck && npm test && npm run build     # Node 20; the CI runs it in the pinned Node image
```

`platform/world-model/tests/e2e/run.sh` runs the whole thing in a real Chrome (runtime on the mock engine, x264): the video must
decode and animate, keys must change the picture and yield an input-to-display latency, prompt edits must apply, a refused
prompt must be explained, reset and end session must work, and the browser must log no error.

## Configuration

`WORLD_MODEL_RUNTIME_URL`, `WORLD_MODEL_INTERNAL_TOKEN`, `KEYCLOAK_ISSUER`, `KEYCLOAK_JWKS_URL`, `JWT_AUDIENCE`, `ALLOWED_GROUPS`,
`OPS_GROUPS`, `ALLOWED_ORIGINS`, `AI_GATEWAY_URL`, `PROMPT_MODEL`, `PROMPT_ENHANCE_TIMEOUT`, `MAX_PROMPT_CHARS`, `DENY_TERMS_FILE`,
`SESSION_IDLE_SECONDS`, `SESSION_DETACHED_SECONDS`, `SESSION_MAX_SECONDS`, `WORLDS_PER_HOUR`, `PRESETS_FILE`
(`/app/config/presets.yaml`, WP-236), `UI_DIR`. The issuer must be the public https realm URL: a token minted through the in-cluster
http Service carries `iss: http://...` and would be refused.

## Image

`Dockerfile`: a Node 20 stage builds the UI from `ui/package-lock.json`, then the Python service from the hash-checked
`requirements.txt`, files made world-readable for an arbitrary non-root UID. Single replica (the lease is in memory).
