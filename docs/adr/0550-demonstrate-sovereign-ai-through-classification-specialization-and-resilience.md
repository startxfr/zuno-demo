# ADR-0550: Demonstrate sovereign AI through classification, specialization and resilience

- **Status:** Proposed
- **Target:** v0.4
- **Date:** 2026-09-05
- **Decision owners:** Zuno Demo architecture team

## Context

Zuno already provides most capabilities needed for a concrete sovereign-AI demonstration:

- user projects exist in the agent frontend/BFF and carry C1/C2/C3 classification;
- project classification already participates in the monotonic effective-classification mechanism;
- OpenShift AI serves local models on controlled GPU infrastructure;
- OVHcloud `gpt-oss-120b` and Mistral Codestral are already usable as approved external providers;
- `qwen3.5-9b-wesh` has already completed a PEFT/LoRA -> evaluation -> registry -> serving lifecycle and is consumed by Comage;
- the Qwen/Wesh failover has already been exercised live through a reusable Day 3 scenario and AAP Workflow Template;
- OpenShift AI MaaS `ExternalModel` remains a target transport for external providers but is not required to exercise Zuno's policy decisions.

The webinar has approximately twenty minutes for the live demonstration. The demo must primarily use web interfaces (Zuno, OpenShift AI Dashboard, OpenShift Console and AAP), with `make demo-*` commands acting as presenter assistance and deterministic preflight/reset tooling.

A previously considered operational `SOVEREIGN` mode would have required a new runtime policy overlay plus an AAP/GitOps mutation workflow. Those components are useful platform capabilities but are unnecessary to prove the webinar's central points and would add demo-specific implementation risk.

The existing model failover drill already provides a stronger operational story with no new routing mechanism: loss of the preferred local `qwen3.5-9b-wesh` model causes a real Comage request to fall back to `qwen3.5-9b`, and the preferred model is used again after restoration.

The originally imagined inverse demo — make `qwen3.5-9b` unavailable and show Tekos fall back to `qwen3.5-9b-wesh` — is not selected. Tekos's real chat-reachable primary task (`answer-technical-question`) currently prefers external `gpt-oss-120b` at C1/C2, while the Tekos tasks that lead with `qwen3.5-9b` are not independently reachable through a real chat turn. ADR-0536/WP-105 already discovered and documented this limitation and changed the live drill to the Comage direction.

## Decision

### 1. Use three independent routing dimensions as the demonstration spine

The webinar demonstrates that model placement is not a fixed model-to-agent mapping. Zuno combines at least:

1. **data sensitivity / effective classification**;
2. **task-specific model requirements**;
3. **runtime availability / fallback**.

Conceptually:

```text
agent + task + project/context
          |
          v
 effective classification
          |
          +---- task specialization
          |
          +---- provider/model eligibility
          |
          +---- runtime availability
          v
      selected model
```

No demo-only policy mode is introduced.

### 2. Make Arkos DAT project-classification driven

The Arkos DAT task is `draft-architecture-testimonial`.

Its baseline classification becomes:

- the selected project's classification when the conversation belongs to a project;
- `C1` when no project is selected.

The existing effective-classification mechanism remains authoritative and monotonic:

```text
effective classification = MAX(
  DAT baseline,
  project classification,
  user input classification,
  retrieved knowledge classification,
  MCP/tool result classification,
  conversation/history classification,
  generated intermediate context classification
)
```

Classification may stay equal or become stricter; it may never be automatically downgraded.

Source-level restrictions such as `external_model_policy.allow_context: false` remain stronger than the generic class and continue to force a local path.

This decision is scoped to the DAT task. It does not redefine unrelated Arkos task baselines.

### 3. Route Arkos DAT according to effective classification

The DAT model chain is:

| Effective classification | Preferred | Fallback | External inference |
|---|---|---|---|
| C1 | OVHcloud `gpt-oss-120b` | local `gpt-oss-20b` | allowed |
| C2 | local `gpt-oss-20b` | none outside approved local candidates | forbidden for DAT |
| C3 | local `gpt-oss-20b` | none outside approved local candidates | forbidden |

For C1, an OVH/provider failure may fall back to local `gpt-oss-20b`.

For C2/C3, loss of the permitted local model must never cause externalization. The request fails explicitly if no authorized local candidate remains.

Availability can reduce service quality or cause failure; it can never weaken sovereignty constraints.

### 4. Remove the DAT fixed-C2 external reflection exception

ADR-0416 introduced an Arkos `reflect_node` path that could use OVHcloud under a fixed C2 ceiling over an already-derived draft.

That behavior no longer matches the desired DAT rule. For `draft-architecture-testimonial`, reflection/review follows the same effective-classification placement as the DAT workload:

```text
C1    -> OVHcloud permitted
C2/C3 -> local only
```

The change supersedes the fixed-C2 external reflection exception for the DAT task only. Other ADR-0416 provider integration decisions remain unchanged.

### 5. Preserve the established Tekos and Comage default model pairing

For non-specialized tasks whose task policy does not override the agent default:

```text
Tekos:
  primary  = qwen3.5-9b
  fallback = qwen3.5-9b-wesh

Comage:
  primary  = qwen3.5-9b-wesh
  fallback = qwen3.5-9b
```

Task-specific model requirements take precedence over these defaults.

A task requiring an MCP/tool operation executes that required tool path as defined by the task/graph before downstream reasoning where applicable.

### 6. Use Codestral to demonstrate task specialization

A short public/C1 coding request is issued to Tekos.

The `write-code` task remains the demonstration of task-specific model specialization: Codestral is selected because the task requires a code-specialized model, even though Tekos's ordinary local model pairing is Qwen-based.

Existing eligibility and fallback behavior from ADR-0417 remains unchanged.

This proves that the model is selected from **task + policy**, not from agent identity alone.

### 7. Use `qwen3.5-9b-wesh` as the training-sovereignty proof

No training operation is started during the webinar.

The demo shows the already-completed lifecycle:

```text
style corpus
   -> OpenShift AI / MLOps training
   -> PEFT / LoRA
   -> evaluation gates
   -> merged qwen3.5-9b-wesh artifact
   -> Model Registry
   -> OpenShift AI serving
   -> Comage
```

The presenter then opens Comage and shows that the model produced by the platform lifecycle is actually the preferred model for the business agent.

This demonstrates infrastructure and model sovereignty without introducing a long-running, timing-sensitive live training operation.

### 8. Reuse the existing Comage failover drill as the resilience scenario

No new failover mechanism is implemented for the webinar.

Reuse ADR-0536 / WP-105:

```text
normal:
  Comage -> qwen3.5-9b-wesh

failure injected:
  cordon node carrying qwen3.5-9b-wesh
  delete Wesh serving pod
  replacement remains unschedulable
  Comage -> qwen3.5-9b

restore:
  uncordon
  Wesh reschedules
  Comage -> qwen3.5-9b-wesh
```

The preferred execution surface for the webinar is the existing AAP Workflow Template:

`zuno-day3-scenario-failover-node-workflow`

The workflow already contains:

- failure injection;
- application-level verification;
- a human approval checkpoint;
- restoration;
- post-restore verification.

The existing local equivalent remains:

`make d3 scenario-failover-node`

The webinar does not add a second Tekos-specific failover implementation solely for presentation purposes.

### 9. Surface routing decisions in the Zuno frontend

Each demonstrated response should expose an expandable technical routing summary derived from the real server-side decision.

At minimum:

```text
Agent
Task
Project
Project classification
Effective classification
Selected model
Provider
Execution location: local / external
Fallback used: yes / no
Fallback-from provider/model when applicable
Routing reason
```

The frontend and BFF must not reimplement routing logic.

The metadata is generated by the model-routing/inference path and propagated through Agent Runtime and BFF to the UI.

The panel may be restricted to demo/admin/technical personas if exposing it to all business users is undesirable.

### 10. Keep OpenShift AI MaaS ExternalModel non-blocking

ADR-0541/WP-125 remains the owner of the external-provider-via-MaaS problem.

The webinar works using today's proven direct provider path for OVHcloud/Codestral.

If the RHOAI `ExternalModel` path becomes functional before the webinar, it may replace the transport without changing the demo scenario or business routing policy.

No new WP is created here for that topic.

## Twenty-minute live sequence

### Step 1 — 0:00 to 4:00 — Same platform, approved external reasoning

**UI:** Zuno Arkos.

Open Arkos with no project or a C1 demo project and launch the DAT task.

Expected routing:

```text
Task: draft-architecture-testimonial
Classification: C1
Model: gpt-oss-120b
Provider: OVHcloud
Execution: external
```

Message: sovereignty does not mean "never use cloud AI"; it means deciding when external inference is authorized.

### Step 2 — 4:00 to 8:00 — The same business task becomes local because the data changes

**UI:** Zuno Arkos -> OpenShift AI Dashboard -> OpenShift Console.

Run the same DAT task from a C2 project (C3 can be shown as the policy ceiling but does not need a second full generation).

Expected routing:

```text
Classification: C2
Model: gpt-oss-20b
Provider: local
Execution: controlled OpenShift AI infrastructure
```

Open the local model serving view and then the actual OpenShift workload/GPU placement.

Message: the task did not change; the data classification changed the execution location.

### Step 3 — 8:00 to 11:00 — Task specialization selects another external model

**UI:** Zuno Tekos.

Issue a public coding request that reaches the existing `write-code` path.

Expected:

```text
Task: write-code
Model: Codestral
Provider: Mistral
Execution: external
```

Message: model selection also depends on task specialization, not only sensitivity.

### Step 4 — 11:00 to 14:00 — The platform owns a model adaptation lifecycle

**UI:** OpenShift AI Dashboard / model registry / training evidence -> Zuno Comage.

Show the completed Wesh PEFT/LoRA training run, evaluation gate, registered artifact and serving endpoint.

Then open Comage and issue a normal task whose preferred provider is `qwen3.5-9b-wesh`.

Message: sovereignty includes the ability to train/adapt, evaluate, register and serve a controlled model artifact.

### Step 5 — 14:00 to 20:00 — Resilience without violating policy

**UI:** AAP -> Zuno Comage -> AAP.

Launch the existing `zuno-day3-scenario-failover-node-workflow`.

Show the baseline where Comage uses Wesh, inject the failure, then issue/observe Comage traffic using base Qwen.

Use the AAP human approval node to restore the model and confirm Wesh is preferred again.

Expected transition:

```text
qwen3.5-9b-wesh
        -> failure
qwen3.5-9b
        -> restore
qwen3.5-9b-wesh
```

Message: model availability is handled as an operational concern without changing the business request or sovereignty boundary.

## Demo automation

Add presenter-oriented helpers:

```text
make demo-check
make demo-reset
make demo-step-1
make demo-step-2
make demo-step-3
make demo-step-4
make demo-step-5
```

The helpers do not replace the web UI.

For each step they:

- verify prerequisites;
- print the exact web surface to open;
- print the exact project/task/prompt to use;
- print the expected classification/model/provider;
- execute only safe, repeatable setup operations;
- refuse to continue if the expected platform state is absent.

`demo-step-5` reuses WP-105 artifacts rather than implementing failover again.

`demo-reset` verifies that any GPU node touched by the failover drill is uncordoned and that both Qwen models are back to their expected running/ready state.

## Security considerations

- Effective classification remains monotonic.
- Source-level local-only restrictions remain stronger than classification.
- C2/C3 DAT requests cannot fall back to an external provider.
- Model unavailability may cause a fallback only among candidates that are already authorized for the effective context.
- The failover drill mutates shared GPU infrastructure and must keep WP-105's existing human approval/recovery controls.
- GPU MIG quota (`zuno-ai-run-gpu-cap`) was found fully saturated (`mig-1g.24gb` 3/3, `mig-2g.48gb` 2/2, zero headroom) as of 2026-09-05 (WP-131 step 8), after the last live proof of the WP-105 failover drill. Re-confirm before the webinar that Wesh's restore reschedule does not require the manual ReplicaSet-scaling workaround WP-131 hit on RollingUpdate flips — the cordon/delete/uncordon shape should not surge the way a RollingUpdate does, but this has not been re-proven under the current saturated quota.
- Demo helper commands must not bypass application authentication or routing policy.

## Consequences

### Positive

- The live scenario becomes shorter to prepare and more deterministic.
- The webinar reuses a failure scenario that has already been exercised against the real platform.
- AAP gets a meaningful web-UI role without building a demo-only automation workflow.
- The demo now covers four complementary sovereignty concerns:
  - data-controlled placement;
  - external model consumption;
  - internal inference and GPU ownership;
  - training/model ownership and runtime resilience.

### Trade-offs

- The fallback demonstration is Comage Wesh -> base Qwen rather than the inverse Tekos direction.
- Tekos still demonstrates Codestral specialization and therefore remains part of the demo.
- The failover drill can exhibit cold-start/telemetry latency during the transition window; the presenter runbook must account for this and keep the existing WP-105 warning semantics.

## Acceptance criteria

1. Arkos DAT outside a project is treated as C1.
2. Arkos DAT in a C1 project selects OVHcloud `gpt-oss-120b` when healthy.
3. C1 OVH failure can fall back to local `gpt-oss-20b`.
4. Arkos DAT in C2 and C3 projects cannot select an external provider.
5. C2/C3 DAT selects local `gpt-oss-20b` when healthy.
6. C2/C3 local model loss never relaxes the externalization policy.
7. A C1 project whose context escalates to C2 is routed as C2.
8. The Zuno UI shows the real effective classification and selected provider/model.
9. Tekos `write-code` visibly selects Codestral on an eligible request.
10. The existing successful Wesh training/evaluation/registry evidence is reachable during the demo.
11. Comage visibly uses `qwen3.5-9b-wesh` before the failover drill.
12. The existing AAP failover workflow can be launched from the Controller UI.
13. During failure, Comage traffic is served by `qwen3.5-9b`.
14. After approval/restoration, Comage returns to `qwen3.5-9b-wesh`.
15. `make demo-check` validates all critical webinar prerequisites.
16. `make demo-reset` returns the environment to the documented initial state.
17. Two consecutive timed rehearsals complete the planned scenario in twenty minutes without unplanned CLI repair.

## Related ADRs

- ADR-0021 — route models according to C1/C2/C3 classification
- ADR-0034 — compute effective classification from the complete context
- ADR-0035 — prevent restricted context from reaching external models
- ADR-0416 — consume `gpt-oss-120b` via OVHcloud AI Endpoints
- ADR-0417 — consume Codestral via Mistral API
- ADR-0418 — execute operational workflows through AAP
- ADR-0526 — fine-tune and serve `qwen3.5-9b-wesh`
- ADR-0527 — project as sharing and context boundary
- ADR-0531 — `qwen3.5-9b` fleet default and task-specific model preferences
- ADR-0536 — live Qwen/Wesh GPU-node failover drill
- ADR-0541 — external models through OpenShift AI MaaS `ExternalModel`

## References

- Proposed execution: WP-137, WP-135, WP-136.
- Existing failover implementation reused unchanged: WP-105.
- Existing external-model/MaaS effort reused unchanged: WP-125.
