# ADR-0536: Live GPU-node failover drill for the qwen-normal/qwen-wesh fallback, and a reusable `make d3 scenario-failover-node` command

- **Status:** Proposed
- **Target:** v0.4
- **Date:** 2026-08-30
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0526 (WP-087) routes Tekos to `local-qwen35(-maas)` first and `local-wesh(-maas)`
second, and routes Comage to `local-wesh(-maas)` first and `local-qwen35(-maas)`
second (`policies/model-routing/model-routing-policy.yaml`). Its own acceptance
criteria claim both directions of this fallback work, but its Status line records
the honest state: *"STILL NOT TRUE: the fallback behaviours (Comage when the
variant is unavailable, Tekos on either path) remain untested"*
(`docs/adr/0526-fine-tune-and-serve-a-french-urban-register-model-variant.md:3`).

The only fallback drill this platform has actually run live is ADR-0521's
"controlled deny drill" (`docs/roadmap/evidence/adr-0521-maas-local-traffic.md:90-115`),
and it exercises a different mechanism entirely: MaaS-unreachable → the same
model served directly, forced by scaling the `payload-processing` ext_proc
backend to zero. It says nothing about what happens when the *model itself*
becomes unschedulable — a GPU pod killed, its node cordoned, no replacement
capacity anywhere in the cluster. ADR-0526's own Consequences section already
names the risk this leaves untested: with two permanent MIG nodes fully
allocated across five model workloads, *"losing a node now leaves at least two
models unschedulable until capacity returns"* — exactly the condition under
which `ai-gateway`'s candidate-exhaustion fallback (`app/main.py:_invoke_with_fallback`)
is supposed to save the turn, and never has been proven to.

This ADR closes that gap with a real drill — cordon the node carrying
`qwen3.5-9b-kserve`, delete its pod, and prove from the two calling agents'
own live traffic that Tekos fails over to `local-wesh` while Comage (whose
primary is already `local-wesh`) is unaffected — and packages the drill as a
standing, repeatable demo/operational capability rather than a one-off manual
exercise.

## Decision

1. **Reusable drill, not a one-off script.** The drill is exposed as
   `make d3 scenario-failover-node`, following this repo's existing Day 3
   "operational tasks" tier (ADR-0057/ADR-0058) and its uniform AAP-routing
   convention (`aap_route`, ADR-0418 clause 6): every new `make` action gets
   both a local (`ansible-playbook`) path and an AAP Job/Workflow Template
   path, local built and validated first. See WP-105 for the full
   implementation.

2. **Split into two playbooks around a mandatory human checkpoint.**
   `day3_scenario_failover_node_inject.yml` (baseline probe → cordon → kill
   pod → verify `Pending` → re-probe to confirm the live failover) and
   `day3_scenario_failover_node_restore.yml` (uncordon → reschedule → verify
   `Running` → re-probe to confirm the return to normal). The command pauses
   for interactive human confirmation between the two (`read -r -p`, refusing
   to run at all outside a TTY) — this mutates shared GPU infra and is meant
   to be watched, not fired-and-forgotten. The same split lets the eventual
   AAP Workflow Template (Part B, WP-105) place a real approval node between
   the two jobs instead of an interactive shell prompt.

3. **Node discovery is dynamic, never a hardcoded IP.** Every prior write-up
   of this exact cordon/kill maneuver (`wp-086-spread-models-and-platform-hygiene.md:258-261`,
   `wp-092-qwen35-wesh-targeted-anti-affinity.md:100-125`) hand-copied a node
   IP out of `oc get pods -o wide`. The playbook instead resolves the node
   from the running pod's own label (`app.kubernetes.io/name=qwen35-9b`,
   namespace `zuno-ai-run`) at run time, and only ever deletes that one pod —
   never a blanket delete on the node, so the co-located `qwen3.6-27b-instruct`
   pod on the same node is left running undisturbed (cordon blocks new
   scheduling only; it does not evict what is already there).

4. **Proof is a live application-level probe, not a log read.** `zuno_provider`
   (the field that names which candidate actually served a request,
   `components/ai-gateway/app/schemas.py:84/107`) is never propagated past
   ai-gateway — agent-runtime, agent-bff and the frontend all drop it. The
   drill instead proves the switch by (a) issuing one real chat turn to
   Comage and one to Tekos through the real agent-runtime chat endpoint,
   reusing this repo's existing evaluation-harness auth helpers
   (`evaluations/tekos/run_scenarios.py:get_token/auth_headers`), and (b)
   reading the before/after delta of the `zuno_model_calls_total{agent,
   provider, outcome}` counter (`components/ai-gateway/app/telemetry.py`,
   already scraped by prometheus-k8s per `gitops/charts/grafana/templates/datasource-prometheus.yaml`)
   for both agents. A warning-level log line
   (`components/ai-gateway/app/main.py:502-506`, `"provider '...' failed ...
   trying next fallback"`) is captured as corroborating evidence only, never
   as the sole proof.

5. **Assert the semantic-cache precondition instead of assuming it.** Today
   no provider sets `cache_enabled` in `platform/ai-gateway/provider-routing.yaml`,
   so the semantic cache (`components/ai-gateway/app/semantic_cache.py`,
   keyed on the *requested* model, not the candidate that actually served it)
   cannot mask the restore-phase re-probe with a stale `local-wesh` answer.
   The inject playbook reads this value live and fails loudly, before
   drawing any conclusion from the probes, if it is ever `true` for
   `local-qwen35`/`local-wesh` — this is exactly the kind of drift the
   ADR-0526 gap analysis warns must be checked live, not read once and
   trusted forever.

## Consequences

- The cluster spends the drill window (cordon-to-uncordon) with **zero**
  spare GPU capacity beyond what ADR-0526 already accepted losing: if any
  *other* pod on the cordoned node were to restart during that window for an
  unrelated reason, it too would go `Pending` until uncordon. The drill keeps
  this window short and touches only the one target pod.
- This is the first ADR-0418-family Workflow Template to need a human
  approval gate rather than a straight-line job DAG. Part B of WP-105
  extends `gitops/charts/aap-config`'s Workflow Template rendering to support
  an `approval`-type node and a per-node Job Template (today every node in a
  given workflow shares one Job Template, `templates/workflowtemplate.yaml:59-78`)
  — a reusable capability for future gated, human-in-the-loop scenarios, not
  a one-off hack for this drill alone.
- Closes ADR-0526's "STILL NOT TRUE" gap for the node/pod-failure fallback
  path once the drill has actually run and its evidence is recorded; it does
  **not** amend ADR-0526 itself (that record stays immutable) — the gap is
  closed by this ADR's own evidence doc plus a note added to ADR-0526's
  index entry pointing here.

## Security considerations

No identity, classification or authorization boundary changes. The drill
only cordons/uncordons a node and deletes one already-authorized workload's
pod using existing cluster-admin `oc` access; the live probes authenticate
as the same demo personas (`consultant-01`, `sale-01`) the evaluation
harnesses already use, via the same Keycloak Resource-Owner-Password grant.

## Operational considerations

Requires coordination with any other live session already operating on this
shared cluster before running (standing house rule since the WP-084
collision) — this command mutates a GPU node's schedulability and deletes a
production-serving pod. If interrupted after cordon but before the restore
playbook runs, the node is left cordoned and `local-qwen35` left `Pending`
until an operator manually runs `oc adm uncordon` and re-deletes the pod (or
re-runs `make d3 scenario-failover-node`'s restore half) — this is a known,
documented recovery path, not a failure mode of the command.

## Acceptance criteria

Beyond the Standard clauses:

- `make d3 scenario-failover-node` (local path) runs end-to-end on the real
  cluster at least once, with before/during/after evidence for **both**
  Tekos (expected: `local-qwen35` → `local-wesh` → `local-qwen35`) and Comage
  (expected: `local-wesh` throughout, unaffected) captured in
  `docs/roadmap/evidence/adr-0536-node-failover-drill.md`.
- The same scenario re-runs cleanly via the AAP Workflow Template (Part B),
  with the human approval step exercised in the Controller UI.
- `python3 platform/docs/check_docs.py` exits 0.

## References

- Work package: [WP-105](../roadmap/work-packages/wp-105-node-failover-drill-scenario-command.md).
- Drill evidence: [adr-0536-node-failover-drill.md](../roadmap/evidence/adr-0536-node-failover-drill.md).

See [Standard clauses](README.md#standard-clauses) for Alternatives considered,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0526](0526-fine-tune-and-serve-a-french-urban-register-model-variant.md) - names the untested fallback gap this ADR closes
- [ADR-0521](0521-route-local-model-traffic-through-maas.md) - the only prior live fallback drill (different mechanism: MaaS-unreachable, not pod/node-down)
- [ADR-0418](0418-execute-day-0-and-day-1-operations-as-aap-job-templates.md) - the `aap_route`/local-then-AAP convention this new `make` verb follows
- [ADR-0351](0351-share-rtx-pro-6000-gpus-via-nvidia-mig-with-scale-from-zero-burst-capacity.md) - the two-node MIG topology that makes the cordon deterministic (no third node to absorb it)
