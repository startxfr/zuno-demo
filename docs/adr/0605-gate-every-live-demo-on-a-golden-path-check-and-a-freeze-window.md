# ADR-0605: Gate every live demo on a golden-path check and a freeze window

- **Status:** Accepted
- **Target:** v0.15
- **Date:** 2026-11-07
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0053](0053-make-make-check-an-end-to-end-acceptance-and-security-gate.md), [ADR-0057](0057-introduce-day-2-agent-availability-test-and-stresstest-operations.md), [ADR-0550](0550-demonstrate-sovereign-ai-through-classification-specialization-and-resilience.md), [ADR-0573](0573-pilot-unifai-on-demo333-with-tekos-before-cutting-demo222-over.md), [ADR-0587](0587-admit-additional-user-experiences-over-the-one-governed-backend.md), [ADR-0593](0593-key-the-per-user-quota-and-telemetry-by-persona-across-experiences.md), [ADR-0401](0401-introduce-agent-delegation-limited-to-targets-an-agent-declares.md), [ADR-0409](0409-introduce-human-approval-for-delegated-operations-resumable-from-persisted-checkpoints.md), [ADR-0606](0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md), [ADR-0607](0607-pin-gate-and-schedule-pre-ga-dependencies.md), [ADR-0608](0608-keep-the-repository-the-only-source-of-cluster-state.md)

## Context

A project review on 2026-11-07 measured the platform against its next audience, a live demonstration on demo333 on
2026-11-09 at 09:00. The demonstration has four moments: the tour of the user experiences over one governed backend,
an agent-to-agent delegation with a human approval, the sovereignty story (classification, local routing, guardrails,
quotas, traces) and, when it is ready, the world model of ADR-0604.

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | No check sends a real turn through each experience. | `make demo check` (`ansible/playbooks/demo_check.yml`, WP-136) was last changed on 2026-10-24 and covers none of the five experiences. The role prechecks (`make d2 check open-webui\|dify\|kagent\|openclaw\|unifai`) prove sync, digest, a 401 without a token and blocked egress, never a model answer. |
| F2 | Green status has hidden dead paths before. | ADR-0573 already states that a cut-over is "re-proved by an end-to-end Tekos chat through UnifAI, not by reading `UnifaiStack` status"; it was never automated. On 2026-11-02 green AAP resources hid a dispatcher that had run nothing for a week. |
| F3 | The freeze procedure is not in the repository. | It is quoted in passing by ADR-0573, WP-155 and `docs/platform/slo.md`, and written down only in an operator's notes. |
| F4 | A push to `devel` changes demo333 at once. | The Applications are applied with `zuno_gitops_target_revision` (`ansible/tasks/apply_gitops_app.yml`), which is `devel` on demo333: 110 of the 112 live Applications tracked `devel` with automated sync on 2026-11-07, while the manifests default to `main` and `RELEASING.md` said `main` is what demo333 deploys. |
| F5 | Pre-GA components move between two rehearsals. | The UnifAI catalog moved 0.1.61 → 0.1.62 → 0.1.63 between 2026-11-06 and 2026-11-07; 0.1.63 broke the approval relay (500 on `session.approval`). `platform/olm/known-good-demo333.yaml`, measured 2026-11-05, still lists 0.1.59. |
| F6 | Several sessions act on demo333 in parallel. | On 2026-11-07 twelve working sessions were open on this machine; the security, classification and world-model work each held their own branch and cluster windows. |

## Decision

**A live demonstration is given only after a golden-path check passes, and only inside a freeze window that starts with
that check and ends with the demonstration.**

1. **The golden path is one probe per demonstration moment, each a real call.** A probe passes only on a real answer,
   never on a resource condition alone. Each probe is read-only with respect to the platform: it may create a test
   conversation or session, which it cancels or deletes before it exits. The probes compose existing checks rather than
   re-implementing them:

   | Moment | Probe | Built from |
   |---|---|---|
   | Agents on UnifAI | Sign in as the presenter persona, open the agent's team workspace, get one answer from Tekos. | `evaluations/demo_presenter_probe.py` (sign-in, workspaces) plus one chat turn |
   | Open WebUI, OpenClaw, Dify, kagent | The role precheck, then one model answer through the ai-gateway under the client's own identity, seen as a new `zuno_model_*{client=<azp>}` sample or an ai-gateway audit line. | `make d2 check <component>`, `experienceClients` in `gitops/charts/ai-gateway/values.yaml` |
   | Zuno Code | One answer from the declared code model, routed to Codestral first (ADR-0596). | the Open WebUI probe with the code model |
   | Lightspeed | The health probe, then one answer. | `ansible/roles/day3/tasks/lightspeed_health_check.yml` |
   | Delegation | A delegating run (Arkos scenario 21), then the delegation evidence in the gateway logs. | `platform/testing/a2a_delegation_check.py` |
   | Human approval | One approval round trip, only on a pinned UnifAI release whose approval relay is proven. Otherwise the probe reports "not in this demonstration" and the runbook names the exception. | ADR-0409 proof recipe |
   | Sovereignty | One restricted (C3) turn answered by a local model, one seeded guardrails detection, and the quota and trace evidence of that turn (Tempo search by run id). | ai-gateway audit line, `zuno_guardrails_*`, ADR-0543 |
   | World model | Added when ADR-0604 ships a probe. Until then the demonstration presents it as roadmap, not live. | ADR-0604 |

   The probes run as `make demo golden-path` (`evaluations/golden_path_probe.py`), next to the webinar preflight
   `make demo check`, with the same read-only contract (ADR-0550). Moments that only a person can
   see on a screen get a manual checklist with the expected screen, in the demo-day runbook (clause 5).

2. **The golden path runs four times.** A dry run the day before (failures are fixed then), the baseline run that opens
   the freeze, and two runs on the morning of the demonstration (about 90 and 30 minutes before). It never runs while
   the audience watches. A red probe on the morning switches that moment to its fallback (clause 5); it does not open a
   fix.

3. **The freeze window.** It starts with the baseline run and ends when the demonstration ends. Inside it:
   - nothing is pushed to `devel` or `main` (F4: a push is a deployment);
   - no `make d0|d1|d2 install|reconcile|build`, no `make d3 release|restore|stresstest|run`, no operator, catalog or
     image pin, no node or MachineSet change;
   - every working session that can act on the cluster is told by name which namespaces, Applications and make verbs
     are frozen, and answers before the freeze starts;
   - editing files and committing locally stay allowed;
   - one break-glass change is allowed only with the owner's explicit go, names one change, and is followed by a full
     golden-path run.

4. **The baseline is recorded at the start of the freeze.** `python3 platform/olm/audit_operator_updates.py --oc-context
   <context> --format known-good` regenerates `platform/olm/known-good-<cluster>.yaml`, and the running digests of the gateways, UnifAI and
   the experience clients (already read by their role checks) are written into the demo-day runbook as the rollback
   point. Both are committed locally during the freeze and pushed after it.

5. **One demo-day runbook per demonstration.** `docs/demo/demo-day-<date>.md` holds the order of the moments, the probes
   and their last result, the manual checklist, the named exceptions with their fallbacks, the presenter accounts (names
   and Vault paths, never values) and the list of frozen sessions. The freeze protocol itself lives in
   `docs/demo/freeze-protocol.md`, so it no longer depends on any operator's notes (F3).

## Alternatives considered

- **Trust resource conditions and pod status.** F2 shows they stay green on a dead path. Rejected.
- **Automate every screen with a browser test now.** It is the right end state and it is planned under ADR-0606's
  definition of done (WP-243). It cannot be built and trusted in the day left before the 2026-11-09 demonstration.
  Deferred, not rejected.
- **Point every Application at a demo branch during the freeze.** It changes the `targetRevision` of every Application
  right before an audience, a larger change than the risk it removes. A no-push rule gives the same protection.
  Rejected for now; ADR-0608 may revisit the deployment branch.
- **Pause ArgoCD automated sync during the freeze.** Self-heal is what repairs a drift during the window; pausing it
  hides the drift instead. Rejected.

## Consequences

- A new experience cannot be demonstrated before it has a probe. ADR-0606 makes that part of its definition of done.
- Work done during a freeze piles up as local commits. The window is kept short: it opens the evening before and closes
  with the demonstration.
- The probes spend tokens under the evaluation clients' quotas (ADR-0593). They use a small output budget and one turn
  each; the delegation probe is the most expensive and runs once per golden-path run.
- A fallback is part of the demonstration, not an improvisation: each moment that can fail has one written down.

## Security considerations

The probes read persona passwords and client secrets from Vault at run time and never print them, as
`evaluations/demo_presenter_probe.py` already does. No NetworkPolicy is widened for a probe: a probe that cannot reach a
service from its pod uses the Kubernetes API or the public route, as `demo_check.yml` already does for the models.

## Operational considerations

A full golden-path run is budgeted at about 15 minutes, the delegation probe included. The freeze message to the
working sessions names: the namespaces `zuno-ai-run`, `zuno-unifai`, `zuno-data`, `zuno-auth`, the experience-client
namespaces, the gateways' and the experience clients' Applications, and every `make d0|d1|d2|d3` verb that writes.

## Work packages

[WP-238](../roadmap/work-packages/wp-238-golden-path-check-freeze-protocol-and-demo-day-runbook.md) (the probes, the
freeze protocol and the first demo-day runbook, for 2026-11-09).
