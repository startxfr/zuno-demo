# WP-155: Migrate the remaining agents, then cut demo222 over

- **State:** Not started
- **ADRs:** [ADR-0573](../../adr/0573-pilot-unifai-on-demo333-with-tekos-before-cutting-demo222-over.md), [ADR-0561](../../adr/0561-adopt-unifai-as-the-agent-platform.md)
- **Depends on:** [WP-154](wp-154-tekos-pilot-on-demo333.md)
- **Related:** [ADR-0342](../../adr/0342-support-multiple-agent-graph-shapes-in-agent-runtime.md), [ADR-0564](../../adr/0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md), [WP-137](wp-137-arkos-dat-classification-routing.md), [WP-156](wp-156-retire-zuno-agent-and-rag-code.md), [WP-157](wp-157-slim-the-ai-gateway-via-maas.md)
- **Target:** v0.11
- **Estimated files touched:** ~20 in `zuno-demo` — `--target unifai` in each `evaluations/<agent>/`, `gitops/charts/unifai/values.yaml` per agent, per-cluster values for demo222, evidence files; fork fixes found per agent go to the fork in their own feature branches.

> tekos proved the stack. This WP repeats the proof for the seven other
> agents on demo333, then moves demo222 — the demo cluster — and only then.

> **Update 2026-10-23.** The cluster demo222 is retired (it is wiped) and the
> branch `demo222` was merged into the single working branch `devel`. demo333
> is now the demo platform: Part B below, the cutover of demo222, no longer
> applies. What replaces it is the parity proof of every agent on demo333 and
> the demo scripts pointing at its routes. Kept below as the record of the
> original plan.

## Goal

All eight agents run on UnifAI on demo333 with green evaluations, then
demo222 is cut over in a single planned window outside any demo freeze, with
agent-runtime, agent-bff and agent-frontend left deployed but unused until
WP-156 removes them.

## Steps

**Live prerequisites.** demo333 is powered off: ask the user to power it on
before part A. Pass `--context` explicitly on every `oc` command, and never
point a demo333 command at demo222 or the reverse. demo333 also runs
`unifai-devel` and `unifai-olm`; leave them alone.

### Part A — demo333

1. **Per agent, in this order:** advantage, cognos, comage, finage, naveo,
   soursage, arkos (last: it carries DAT classification routing from
   [WP-137](wp-137-arkos-dat-classification-routing.md)). For each:
   - check its `agents/<agent>/agent.okf.md` graph shape maps to an
     embedded blueprint (WP-150); a missing shape is a fork change first;
   - sign and publish the bundle (`make d3 sign agents`, OCI push);
   - enable its `UnifaiAgentBundle`, RAG sources and providers in
     `gitops/charts/unifai/values.yaml`;
   - run `evaluations/<agent>/` with `--target unifai` (the mode exists for every
     agent that has evaluations since wave 0: `run_scenarios.py`,
     `security_checks.py` and `run_acceptance_gate.py`, see
     `evaluations/README.md`). `cognos` and `soursage` have no `evaluations/` directory
     today: write a minimal scenario file for each before migrating them,
     and say so in the evidence.

2. **arkos specifics.** Re-run the DAT classification tiering checks
   (`components/ai-gateway/tests/test_arkos_dat_classification_tiering.py`
   covers the gateway side) end to end: the classification raised by the
   session must reach the gateway header (ADR-0565).

3. **Evidence.** One file under `docs/roadmap/evidence/` with each agent's
   pass rate on UnifAI vs agent-runtime.

### Part B — demo222 cutover (only after part A is complete)

4. **Window.** Ask the user for a window outside any demo freeze. Before
   starting, list the parallel sessions and message each of them (the
   pre-demo freeze protocol: name the namespaces, the ArgoCD Applications
   and every `make d0|d1 <verb>`); wait for their confirmation.

5. **Install.** Same chart and role as demo333, with demo222 values
   (catalog tag, image digests, Keycloak client). Ingest the corpus with
   `UnifaiRAGSource`; watch the GPU quota.

6. **Prove the execution chain, not the CRs.** Green `UnifaiStack` status is
   not proof. Run the tekos scenarios and one scenario per other agent with
   `--target unifai` against demo222, and a persona Playwright login.

7. **Switch users.** Point the demo entry points (persona bookmarks, demo
   scripts under `ansible/playbooks/demo_step_*.yml` if they open agent
   URLs) to the UnifAI UI. Keep the zuno agent stack running, unused, as
   the rollback path until WP-156.

## Preparation (2026-10-23, read-only inventory)

State: tekos is proven on UnifAI (94 % against 94 % for agent-runtime's baseline
on the same pilot; evidence file of WP-154). A smoke test already deployed
advantage, comage, finage and naveo with a group-bound team each: a member sees
the workflow and gets a streamed answer, a non-member sees nothing. That does
not prove parity: no evaluation was run on them. arkos, cognos and soursage are
signed and published but not deployed.

| Agent | Status | Tasks | Tools and knowledge | Ceiling | Needs UnifAI work |
|---|---|---|---|---|---|
| naveo | placeholder | 1 | Confluence search, web search, Drive; tech and project | C1 | none, simplest |
| advantage | placeholder | 4 | web search, image generation, Drive, Gmail; `adv` has no source | C2 | no corpus: weak parity point |
| finage | placeholder | 4 | web search, Salesforce read, Drive, Gmail | C2, `local_only` | `local_only` has no known equivalent in the chart |
| comage | active | 4 | Salesforce read and update, web search, images, diagrams, Drive, Gmail | C2 | Salesforce MCP deferred, `comage-lora` routing |
| arkos | active | 4 | Confluence, git including writes, diagrams, AAP audit | C3, project-derived (WP-137) | `plan_draft_write` shape has no blueprint template; project memory |
| cognos, soursage | placeholder | 2, 1 | none | C3, C2 | no `graph_shape`: cannot be instantiated |

Waves: 0 prerequisites (real signing key through WP-158 to WP-162, the
evaluations' `--target unifai` extended to every agent, same-day agent-runtime
baseline); 1 naveo, advantage, finage; 2 comage; 3 arkos last; 4 cognos and
soursage.

Cutover to demo222 (needs the user, a window outside any demo freeze, parallel
sessions frozen first): same chart and role as demo333 next to the old stack,
corpus ingested, execution chain proven (scenarios plus a browser login, never
only custom resources), agents switched one at a time with tekos first, demo
entry points redirected (`ansible/playbooks/demo_step_1..5.yml` open
`https://<agent>.<domain>`). Rollback: the old stack stays deployed and unused
until WP-156, so rollback re-enables its routes and applications.

Gaps found: `min_reasoning_length` not exposed through `agentConfig`;
scenarios 10 and 17; the parity-table rows still marked unverified
(cross-user resume, citations, team rights); agent tiles and cross navigation
(ADR-0515) have no UnifAI equivalent; images are held in demo333's internal
registry, a reproducible path is needed for demo222.

## Acceptance

Every agent's evaluations on demo333 pass at a rate not lower than its
agent-runtime baseline; on demo222 the step-6 runs pass and the demo
playbooks open UnifAI; parallel sessions confirmed the window; no demo
freeze was broken.

## Decisions taken (2026-10-23)

- **Placeholders (ADR-0007):** the operator skips a bundle whose OKF is
  `zuno.status: placeholder` (phase `Pending`, "placeholder agent: not served")
  and prunes what it emitted, unless `spec.servePlaceholder: true`. No placeholder
  is served on demo333 for now. Implemented by the session owning the operator and
  the unifai chart, shipped with operator 0.1.26. After it, advantage, finage and
  naveo have no workflow, so the harness' placeholder logic (chat skipped, blocked
  scenarios expected) becomes correct as it stands.
- **Evaluation token budget:** budgets are per user (`sub`) and per day in
  `policies/quotas/quota-policy.yaml` (`standard`: 3 000 000 tokens, 24 h).
  A campaign that repeats the same persona exhausts it (consultant-01 did on
  2026-10-23). No policy change: spread a campaign over personas holding the same
  group (for tekos consultant-01 and consultant-02 both carry `agent_tekos`), or
  run after the window resets. The evaluation scripts report `quota_exceeded` as
  an environment failure, never as a pass.
- **finage and Salesforce:** the check accepts `salesforce.opportunity.read` on
  `project_required` tasks only (ADR-0512 exception); no bundle change.
- **comage scenario 11:** the retriever is attached; the model chooses
  Salesforce first. The lever is `retrieve_first` (operator 0.1.26,
  `spec.retrieveFirst`, opt-in).

## Open questions

- Salesforce: repair the Vault secret `salesforce/technical` (missing `url`)
  so comage and finage are really testable, or accept those tasks out of
  parity at cutover?
- cognos and soursage: write minimal scenarios as this WP says, or accept
  `Valid=False` as ADR-0573 does? Which agents must appear on demo222?
- Cut over before or after WP-161, WP-163 and WP-165 (OKF delivery chain)?
  Before means `okf.bundles[]` is filled by hand once more.
- Window and soak: which date outside any freeze, and how long the old stack
  stays before WP-156.
- Accepted losses to confirm: classification per session instead of per turn,
  no stars or hard delete, one UI instead of one Route per agent.
- **Agents not migrated in this wave (2026-10-23):** cognos and soursage stay on
  agent-runtime; their absence on UnifAI is an accepted gap, documented here.
  Arkos follows the same rule until its bundle is served.
- **Salesforce on demo333:** Vault `salesforce/technical` has no `url`, so the live
  Salesforce read stays unwired (WP-101 has no owner). Scenarios that need it are
  an accepted failure; comage scenario 10 and 11 prove the reply path only.
- **comage first-token latency:** scenario 8 measures 9-10 s inside a full run but
  3.7-4.2 s when run alone (3 runs, sign-in included), under the 6 s objective.
  Suspected cause: load from the preceding scenarios; not yet proven.

