# agents

Day 2's `agents` component (ADR-0056/ADR-0060). Since WP-156 it deploys
nothing: the per-agent frontend/BFF Applications it used to apply
(`zuno-api` for Tekos, `zuno-arkos`, `zuno-comage`, `zuno-advantage`,
`zuno-finage`, `zuno-naveo`) and the Kuadrant quota-demo route Application
(`zuno-connectivity-link-quota-d1`) were retired with the zuno agent stack.
The agents are served by UnifAI (ADR-0561); their bundles are deployed by
the `unifai` Day 2 component from the admitted zuno-demo-agents release
(ADR-0580). `install.yml` and `uninstall.yml` only say so, and
`precheck.yml` reports the component installed when at least one
`UnifaiAgentBundle` exists in `zuno-unifai`.

`check.yml` (`make day2|d2 check agents`) is the ADR-0053 layered
acceptance and security gate - `day2_check.yml` runs it *instead of*
`precheck.yml` for this role. It:

1. admits the zuno-demo-agents release pinned in `platform/okf/agents.lock`
   (`admit_okf_bundle.py admit`: keyless signatures and contract-tests
   attestations verified offline, every model, tool and knowledge domain
   bound here - ADR-0578, ADR-0580) and extracts it
   (`ansible/tasks/okf_release_cache.yml`);
2. structurally checks every catalog agent's `agent.okf.md` of that release against its
   expected `zuno.status` (`active` for comage/arkos, `placeholder` for
   advantage, finage, naveo, soursage and cognos);
3. runs the availability check (`ansible/tasks/day2_availability_check.yml`):
   each agent of the admitted release is available when its
   `UnifaiAgentBundle` is Ready (placeholder agents pass as "not served by
   design", ADR-0007);
4. hands off to `run_acceptance_gate.yml`, which runs `evaluations/tekos/`'s
   full gate (the 20-scenario acceptance evaluation at a 75% threshold,
   ADR-0027/0028, plus every mandatory security-negative check,
   ADR-0032/0033/0034/0035/0037/0040) against UnifAI, as a one-shot
   in-cluster Job in `zuno-ai-run`, with persona tokens from the
   `zuno-evaluations` Keycloak client - see that file's own header
   comment for why a Job and for the "acceptance-gate" workload identity's
   narrow NetworkPolicy allowances. Running another agent's
   `evaluations/<agent>/run_acceptance_gate.py` the same way is the
   operator's job (`agent_name=<agent>`), not this role's default path.
