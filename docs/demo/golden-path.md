# Golden path: the check before a live demonstration

[ADR-0605](../adr/0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md). A moment is proved by a
real answer, never by a green status. The check has two parts: the automated probes, then the screens a person looks
at. Run both at every golden-path run (the dry run, the freeze baseline, the two morning runs) and write the result in
the demo-day runbook.

## 1. Automated probes (about 15 minutes)

From a workstation logged in to the cluster with `oc`:

```bash
make demo golden-path                 # every moment
ONLY=sovereignty,dify make demo golden-path   # some moments only
```

| Moment | What passes |
|---|---|
| `unifai-tekos` | A Tekos answer in the `agent-tekos` team workspace, signed in as `eval-consultant-01`; the session is deleted |
| `sovereignty` | Arkos (floor C3) called with a `C1` header is routed to a local model and recorded at `C3`; a Tekos control call answers |
| `delegation-approval` | Arkos delegates to Tekos, the approval request appears and is rejected (nothing runs); the gateway logs show the delegated call |
| `open-webui` | One answer from the Zuno model through Open WebUI's API, signed in through Keycloak |
| `zuno-code` | One answer from the `zuno-code` model through Open WebUI (Codestral first) |
| `dify`, `kagent` | One answer through the experience's own token proxy, from inside its pod |
| `openclaw` | Every persona assistant answers from inside its pod through the operator's egress proxy (the `openclaw-<persona>` token is injected there) |
| `lightspeed` | The OLSConfig API and console plugin are Ready, and Lightspeed answers one question (temporary port-forward, your OpenShift token; with a certificate login it falls back to `manual`) |
| `tools` | `search_confluence` through the mcp-gateway REST path (consultant-01, Tekos's task, C2) is answered by the `confluence` MCP server with at least one page |
| `guardrails` | The DAN prompt through Dify's token proxy is answered (observe mode) and the ai-gateway logs `guardrails DETECTED` for client `dify` |
| `trace` | The trace of the `unifai-tekos` run is found in Tempo by its run id (temporary port-forward to `tempo-tempo`), with its gateway spans |
| `world-model` | `roadmap` while `zuno_world_model_enabled` is false; once the demo is installed, a real world is created as `GOLDEN_WORLD_PERSONA` (ai-ops-01), video arrives, one edit is screened and applied, the session is released (run in the web pod); then it is required (ADR-0604, WP-235) |

`RESULT: PASS` means every required moment passed. A `FAIL` on the morning of the demonstration switches that moment
to its fallback in the runbook; it does not open a fix.

Personas and limits: the probes sign in as `eval-consultant-01` (`GOLDEN_PERSONA`) so the demonstration personas'
histories and quotas are untouched. The delegation moment spends one Arkos turn; if it fails with a quota refusal
(429), the evaluation persona's budget is spent, not the platform broken.

## 2. Screens (about 2 minutes, then 5 minutes by eye)

```bash
make demo browser        # UnifAI, Open WebUI, kagent, Dify, OpenClaw: Keycloak sign-in, first screen, screenshots
```

Each check signs in as the persona the script uses and fails on a JavaScript page error. OpenClaw's check also
enters the Control UI password and proves its WebSocket connection to the gateway. The screenshots are written to the
directory the run prints. What stays manual, because a person sees it better than a script:

- [ ] **Lightspeed** in the OpenShift console (chat icon): the panel opens (its API is already proven by the probe).
- [ ] **Grafana** (`zuno-monitoring`, *Zuno Platform / Five experiences*, last hour): one series per client
      (`unifai`, `open-webui`, `openclaw-*`, `dify`, `kagent`) after the probes; the guardrails row shows the probe's
      DAN detection for `client="dify"`.
- [ ] **Tempo** (Grafana, Explore): a trace opens in the UI, as it will be shown on stage.
- [ ] **Dify Studio** after its local sign-in (`dify-admin@zuno.local`, Vault `zuno/dify/admin`): the three example
      applications are listed.
