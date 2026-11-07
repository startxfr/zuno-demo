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
| `guardrails` | The DAN prompt through Dify's token proxy is answered (observe mode) and the ai-gateway logs `guardrails DETECTED` for client `dify` |
| `trace` | The trace of the `unifai-tekos` run is found in Tempo by its run id (temporary port-forward to `tempo-tempo`), with its gateway spans |
| `world-model` | `roadmap` until ADR-0604 ships a probe (WP-235) |

`RESULT: PASS` means every required moment passed. A `FAIL` on the morning of the demonstration switches that moment
to its fallback in the runbook; it does not open a fix.

Personas and limits: the probes sign in as `eval-consultant-01` (`GOLDEN_PERSONA`) so the demonstration personas'
histories and quotas are untouched. The delegation moment spends one Arkos turn; if it fails with a quota refusal
(429), the evaluation persona's budget is spent, not the platform broken.

## 2. Screens (about 10 minutes)

Each line: where, what to do, what must be seen. Sign in as the persona the script uses.

- [ ] **UnifAI** (`https://unifai-ui-zuno-unifai.<apps domain>`, consultant-02): the `agent-tekos` team workspace opens
      and Tekos answers a short question.
- [ ] **Open WebUI** (`https://open-webui.<apps domain>`, sale-01): the models `Zuno` and `Zuno Code` are listed; one
      answer; the tool list shows *Zuno tools*.
- [ ] **OpenClaw** (`https://assistant-zuno-claw-sale-01.<apps domain>`): sign-in through Keycloak, then the Control UI;
      "Cherche dans Confluence les pages d'onboarding" gets an answer citing Confluence.
- [ ] **Dify** (`https://dify.<apps domain>`): Studio lists the three example applications; *Zuno Agent* answers "Find
      our onboarding pages in Confluence". If a Workflow run stalls, stop and restart it (D1).
- [ ] **kagent** (`https://kagent.<apps domain>`, ai-ops-01): the agent `zuno-sre` is ready and answers "Which pods of
      zuno-ai-run are not Running?". Click **Skip wizard** on the first screen.
- [ ] **Lightspeed** (OpenShift console, chat icon): one question about the cluster gets an answer.
- [ ] **Grafana** (`zuno-monitoring`, *Zuno Platform / Five experiences*, last hour): one series per client
      (`unifai`, `open-webui`, `openclaw-*`, `dify`, `kagent`) after the probes; the guardrails row shows evaluations.
- [ ] **Tempo** (Grafana, Explore, Tempo): a trace opens in Grafana's UI, as shown on stage (the probe checks the
      search; this checks the screen).
- [ ] **Guardrails dashboard row**: the probe's DAN detection appears with outcome `detected` for `client="dify"`.
