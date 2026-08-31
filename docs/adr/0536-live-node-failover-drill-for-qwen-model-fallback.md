# ADR-0536: Live GPU-node failover drill for the qwen-normal/qwen-wesh fallback, and a reusable `make d3 scenario-failover-node` command

- **Status:** Implemented (2026-08-31 - both Part A, local path, and Part B,
  AAP Workflow Template with a real human approval-click in the Controller
  UI, live-verified end to end; see the evidence doc for the two live-run
  attempts, three real bugs found and fixed, and full verdict JSON)
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

**Revision, 2026-08-30, before this drill's first live run:** the drill as
originally scoped here — kill `qwen3.5-9b`'s pod and watch Tekos fail over to
`local-wesh` — turned out to be unprovable through Tekos's real chat traffic.
Tekos's `POST /v1/agents/tekos/chat` endpoint always executes its one
primary task, `answer-technical-question` (`components/agent-runtime/app/graph/nodes.py:63-66`
- Tekos's other declared tasks, `find-relevant-docs`/`check-my-drive-docs`,
have no dedicated route yet, v1 scope). WP-096/ADR-0531 (closed the same day
as this ADR was first drafted) flagged that exact task "reflexional" and
routes it to `ovhcloud-gpt-oss-120b` *first*, ahead of every local model, at
compute tiers C1/C2 (`policies/model-routing/model-routing-policy.yaml:94-97`).
The only tasks that lead with `local-qwen35(-maas)` in the routing policy
(`find-relevant-docs`/`check-my-drive-docs`) are exactly the two Tekos never
reaches via a real chat turn. So a genuine chat message to Tekos can never
land on `local-qwen35` today, regardless of node health — killing that pod
would change nothing a live Tekos user actually sees, and this ADR would have
been "proving" a fallback path that no live traffic ever takes.

Comage has the identical one-task-per-turn architecture (`components/agent-runtime/app/graph/build.py:111-120`,
same `retrieve_reason_respond` shape, confirmed no Comage-specific branching
anywhere in `app/graph/nodes.py`), but its own primary task, `check-deal-status`,
is **not** flagged reflexional and its preference list already leads with
`local-wesh(-maas)` then `local-qwen35(-maas)`
(`policies/model-routing/model-routing-policy.yaml:162`) — exactly the two
models on the two MIG nodes this drill can physically fail between, and a
task genuinely reachable by a real chat turn. This ADR therefore closes the
*other* half of ADR-0526's own gap statement instead — "Comage when the
[wesh] variant is unavailable" — by cordoning the node carrying
`qwen3.5-9b-wesh-kserve` (not `qwen3.5-9b`) and proving Comage's real chat
traffic fails over from `local-wesh` to `local-qwen35` and back. Tekos is
kept in the drill as a second, real chat probe, but its role changes from
"the other half of the fallback" to a **decoupling control**: because its
reflexional task is served off-cluster via OVH, it should show zero change
throughout the whole drill window — a genuine, different, and arguably more
useful proof (on-prem GPU node health has no bearing on OVH-routed traffic)
than the original framing. ADR-0526's "Tekos on either path" gap statement
stays explicitly open after this ADR — not silently dropped: it cannot be
closed by a real chat probe until a v1 route exists for
`find-relevant-docs`/`check-my-drive-docs`, and this ADR does not build that
route (out of scope, see WP-105's deferred section).

This ADR closes that (revised) gap with a real drill — cordon the node
carrying `qwen3.5-9b-wesh-kserve`, delete its pod, and prove from Comage's
own live chat traffic that it fails over to `local-qwen35` while Tekos
(routed off-cluster to `ovhcloud-gpt-oss-120b`) is unaffected — and packages
the drill as a standing, repeatable demo/operational capability rather than a
one-off manual exercise.

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
   from the running pod's own label (`app.kubernetes.io/name=qwen35-9b-wesh,kserve.io/component=workload`
   — the `kserve.io/component=workload` half is required, or the selector also
   matches the unrelated `*-router-scheduler` pod on a different
   node; found live 2026-08-30 by this drill's own precondition check refusing
   to proceed on "found 2" instead of failing silently — namespace
   `zuno-ai-run`) at run time, and only ever deletes that one pod —
   never a blanket delete on the node, so the co-located `gpt-oss-20b`
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
   for both agents. Comage's delta is the actual fallback proof
   (`local-wesh(-maas)` → `local-qwen35(-maas)`); Tekos's delta is the
   decoupling control and is expected to show **no** change
   (`ovhcloud-gpt-oss-120b` throughout). A warning-level log line
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

6. **Node separation is a hard requirement for this pair, not a soft
   preference.** Live-cluster-confirmed 2026-08-30, before this drill's
   first live run: `qwen3.5-9b` and `qwen3.5-9b-wesh` were found colocated
   on the same node despite WP-092/ADR-0414's `preferred` anti-affinity —
   both pods had been recreated within the same ~40-second window during a
   routine restart, and scoring chose to violate the soft term even though
   it was satisfiable elsewhere. Left uncorrected, this drill's own
   precondition ("each on a different node") would fail intermittently, and
   worse, a cordon+kill of `qwen3.5-9b` could silently reschedule onto
   whichever node `qwen3.5-9b-wesh` occupies if that node had a free
   matching slice — defeating the whole demonstration. Fixed by promoting
   this one pair's anti-affinity term to
   `requiredDuringSchedulingIgnoredDuringExecution` (amendment to ADR-0526
   decision 5, see that ADR) and physically re-separating the two live pods
   onto their originally-intended nodes before the drill's first run. This
   is scoped to this pair only — every other model on the platform keeps
   its existing soft-only anti-affinity.

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
- Closes half of ADR-0526's "STILL NOT TRUE" gap for the node/pod-failure
  fallback path — specifically "Comage when the [wesh] variant is
  unavailable" — once the drill has actually run and its evidence is
  recorded, via this ADR's own evidence doc. The other half, "Tekos on
  either path," stays explicitly open: it is structurally unprovable through
  real chat traffic today (see Context) and is not addressed by this ADR.
  ADR-0526's Status line is otherwise left untouched. Decision 6 above **is**
  recorded as an in-place Amendment on ADR-0526 itself (its decision 5, the
  `preferred`→`required` anti-affinity promotion), following this repo's
  existing amendment convention (ADR-0526 already carries one, for decision
  7) — narrower in scope than the fallback-gap statement, and a genuine
  correction to a decision that no longer matched live reality, not a
  rewrite of history.

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
playbook runs, the node is left cordoned and `local-wesh` left `Pending`
until an operator manually runs `oc adm uncordon` and re-deletes the pod (or
re-runs `make d3 scenario-failover-node`'s restore half) — this is a known,
documented recovery path, not a failure mode of the command.

## Acceptance criteria

Beyond the Standard clauses:

- `make d3 scenario-failover-node` (local path) runs end-to-end on the real
  cluster at least once, with before/during/after evidence for **both**
  Comage (expected: `local-wesh` → `local-qwen35` → `local-wesh`) and Tekos
  (expected: `ovhcloud-gpt-oss-120b` throughout, unaffected — the decoupling
  control) captured in `docs/roadmap/evidence/adr-0536-node-failover-drill.md`.
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
