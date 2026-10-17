# WP-155: Migrate the remaining agents, then cut demo222 over

- **State:** Not started
- **ADRs:** [ADR-0573](../../adr/0573-pilot-unifai-on-demo333-with-tekos-before-cutting-demo222-over.md), [ADR-0561](../../adr/0561-adopt-unifai-as-the-agent-platform.md)
- **Depends on:** [WP-154](wp-154-tekos-pilot-on-demo333.md)
- **Related:** [ADR-0342](../../adr/0342-support-multiple-agent-graph-shapes-in-agent-runtime.md), [ADR-0564](../../adr/0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md), [WP-137](wp-137-arkos-dat-classification-routing.md), [WP-156](wp-156-retire-zuno-agent-and-rag-code.md), [WP-157](wp-157-slim-the-ai-gateway-via-maas.md)
- **Target:** v0.11
- **Estimated files touched:** ~20 in `zuno-demo` — `--target unifai` in each `evaluations/<agent>/`, `gitops/charts/unifai/values.yaml` per agent, per-cluster values for demo222, evidence files; fork fixes found per agent go to the fork in their own feature branches.

> tekos proved the stack. This WP repeats the proof for the seven other
> agents on demo333, then moves demo222 — the demo cluster — and only then.

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
   - run `evaluations/<agent>/` with `--target unifai` (add the mode as in
     WP-154). `cognos` and `soursage` have no `evaluations/` directory
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

## Acceptance

Every agent's evaluations on demo333 pass at a rate not lower than its
agent-runtime baseline; on demo222 the step-6 runs pass and the demo
playbooks open UnifAI; parallel sessions confirmed the window; no demo
freeze was broken.

## Open questions

- Rollback criterion on demo222: how long does the zuno agent stack stay
  deployed after cutover before WP-156 may start? Ask the user.
- Which demo scripts hard-code agent-frontend URLs? Grep
  `ansible/playbooks/demo_*.yml` and `docs/` during step 7.
