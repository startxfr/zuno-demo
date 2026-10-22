# WP-153: Move TrustyAI guardrails into the ai-gateway

- **State:** Repo work in review
- **ADRs:** [ADR-0567](../../adr/0567-move-trustyai-guardrails-into-the-ai-gateway.md)
- **Depends on:** none
- **Related:** [ADR-0534](../../adr/0534-integrate-trustyai-for-ai-evaluation-and-guardrails.md), [ADR-0540](../../adr/0540-express-guardrail-policy-as-nemo-rails-configuration.md), [ADR-0021](../../adr/0021-route-models-according-to-c1-c2-c3-classification.md), [ADR-0560](../../adr/0560-keep-the-ai-gateway-as-the-policy-router-in-front-of-unifai.md), [WP-156](wp-156-retire-zuno-agent-and-rag-code.md)
- **Target:** v0.11
- **Estimated files touched:** ~8 in `zuno-demo` — a new `components/ai-gateway/app/guardrails.py`, `main.py`, `telemetry.py`, a test file, `gitops/charts/ai-gateway/{values.yaml,templates/deployment.yaml,templates/networkpolicy.yaml}` and the trustyai-config NetworkPolicy if one restricts callers.

> Once agents run in UnifAI, agent-runtime's observe-only guardrails hook
> disappears with it. The one place every model call still crosses is the
> ai-gateway, so the hook moves there and gains a block mode.

## Goal

Every `/v1/chat/completions` exchange through the ai-gateway is evaluated by
the TrustyAI detectors; in `observe` mode detections are logged and counted
without touching the response, in `block` mode a detection on the prompt or
the reply returns a clear refusal; the mode is chosen per data
classification.

## Steps

All work in `/home/cl/ClaudeCode/zuno-demo`. No live cluster is needed until
step 7.

1. **Read.** `components/agent-runtime/app/clients/guardrails_client.py`
   (fire-and-forget, what is sent and deliberately not sent),
   its call sites in `components/agent-runtime/app/main.py`,
   `components/agent-runtime/tests/test_guardrails.py`, the
   `guardrails:` block of `gitops/charts/agent-runtime/values.yaml`, and the
   detector side in `gitops/charts/trustyai-config/templates/{guardrailsorchestrator.yaml,nemoguardrails.yaml,configmap-nemo-rails.yaml}`.
   Then `components/ai-gateway/app/main.py` around the
   `@app.post("/v1/chat/completions")` handler, including the streaming path.

2. **Port the client.** Create `components/ai-gateway/app/guardrails.py` by
   moving the logic, not rewriting it: same payload (user message + reply
   only, never the bearer token or retrieved bodies), same backend switch
   (built-in detector vs NemoGuardrails), same empty-URL-means-off rule.
   Port the span and counter from agent-runtime's telemetry into
   `components/ai-gateway/app/telemetry.py` with the same metric names, so
   existing dashboards keep working.

3. **Modes per classification.** Config map `guardrails.modeByClassification`
   (e.g. `C1: observe, C2: observe, C3: observe` as the shipped default —
   switching any class to `block` is a values change, not a code change).
   `observe`: post-response, fire-and-forget, exactly today's behaviour.
   `block`: evaluate the prompt before routing and the reply before
   returning; on detection return HTTP 400 with a typed error body and
   record the decision in the routing-decisions store
   (`components/ai-gateway/app/routing_decisions.py`). For streaming in
   block mode, evaluate the prompt only and document that the reply is
   observed, not blocked.

4. **Classification source.** Read the class from
   `X-Zuno-Data-Classification` as the gateway already does for routing;
   never trust a lower class than the routing decision used.

5. **Tests.** `components/ai-gateway/tests/test_guardrails.py`: observe never
   alters the response and survives a hung detector; block refuses on a
   mocked detection; mode lookup per class; no token in the detector
   payload. Run the whole ai-gateway suite (one pre-existing failure in
   `test_optimizer.py` is known; do not count it).

6. **Chart.** Add the `guardrails` values and env to
   `gitops/charts/ai-gateway/values.yaml` and `templates/deployment.yaml`,
   and allow egress/ingress between ai-gateway and the detector Service
   (check both NetworkPolicies). Keep agent-runtime's hook enabled until
   WP-156 removes it; disable it on a cluster only once the gateway hook is
   live there, to avoid double counting.

7. **Live check on demo333.** demo333 is powered off; ask the user to power
   it on. With `oc --context <demo333-context>`, send one benign and one
   detector-triggering prompt through the gateway and verify the counter in
   raw Prometheus, not in the Grafana panel (the TrustyAI "0% detection"
   dashboard illusion).

## Repo work done (2026-10-22)

Steps 1 to 6 landed; step 7 (live check) waits for demo333 to be powered on.

- `components/ai-gateway/app/guardrails.py` ports the agent-runtime client
  (both backends, same payloads, same metric names, empty URL = off) and adds
  `mode_for(classification)`, `evaluate`, `observe_exchange` and a typed
  `refusal_body`.
- `main.py`: the mode comes from the declared `X-Zuno-Data-Classification`.
  Only the last user message and the reply are sent. `block` refuses a prompt
  before routing and a reply before returning (HTTP 400,
  `error.type=guardrails_blocked`, detection names only, recorded in the
  routing-decisions store). A streamed reply is observed, never blocked.
- A detector outage is fail-open in both modes (counted `unavailable`).
  Fail-closed `block` is a separate decision.
- Chart: `guardrails.enabled` ships `false` so a cluster that still runs
  agent-runtime's hook does not count each exchange twice. No NetworkPolicy
  change is needed: the detector Services carry no ingress policy and
  ai-gateway has no egress policy.
- Tests: `components/ai-gateway/tests/test_guardrails.py` (16 cases); the rest
  of the ai-gateway suite is unchanged.

## Live check without a GPU (demo333, 2026-10-22)

demo333's GPU nodes are NotReady, so no model answers. The detector side needs
no GPU: the new gateway code was driven in-process (fake provider) against the
real NemoGuardrails Service `zuno-guardrails` through a port-forward, with
C1 observe, C2 block, C3 off.

- Benign C2 exchange: 200, response unchanged.
- C2 prompt `ignore all previous instructions`: 400 `guardrails_blocked`,
  stage `prompt`, provider never called, decision recorded.
- C2 reply containing a card number: 400, stage `reply`.
- C2 stream, clean: served in full. C1 observe with a dirty prompt and reply:
  200 untouched. C3 off: detector not called.
- Block mode added about 150 ms per evaluation on this cluster (the rail is
  pattern-only, 0 LLM calls).

Still to do once a GPU node is back (or the image is built and rolled): the
in-cluster run with a real model and the raw Prometheus counter check
(step 7), and the benign-response byte comparison with the hook on and off.

## Acceptance

ai-gateway suite green with the new tests; default values leave every class
in `observe`; on demo333 the detection counter increments in raw Prometheus
for the triggering prompt only, and the benign response is byte-identical
with the hook on and off.

## Open questions

- Which classes should block by default once evidence exists? ADR-0534
  defers observe-to-block to a later, evidence-based decision; this WP only
  provides the switch.
- Block mode adds detector latency to the critical path; does it fit the
  ADR-0544 bounds on every model call? Measure in step 7.
