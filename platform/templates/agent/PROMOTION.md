# Agent promotion checklist (ADR-0502)

The single, named path from **Stage 1 "scaffolded"** to **Stage 2
"promoted"** — superseding the ad-hoc tail every `NEXT_STEPS.md` used to
restate. An agent is Stage 2 when and only when it meets ADR-0502
clause 2's criteria; this checklist is those criteria in execution
order. Stage is determined by these criteria, never by directory shape.

Scaffold-time steps (the bundle, its entitlement group and corp policy
entries authored in zuno-demo-agents, the release admitted here,
validators) are the generated `evaluations/<name>/NEXT_STEPS.md`'s own
numbered items and are assumed done before promotion starts. Since WP-165
the bundle-side steps (4 and 5 below) happen in zuno-demo-agents and reach
this platform as a promoted release.

1. **Human scenario review** — review the 20 scenarios in
   `evaluations/<name>/scenarios.yaml` (ADR-0027). No live gate run
   counts before this checkpoint (ADR-0326's completion pattern).
2. **Operator deploy on UnifAI** — admit the zuno-demo-agents release
   carrying the bundle (`make d3 admit agents`, ADR-0580) and deploy it
   (`make d2 install unifai`); its `UnifaiAgentBundle` must be Ready
   (ADR-0564). The AIAgent CR path this step used was retired in WP-156.
3. **Evaluation gate** — run the acceptance gate
   (`evaluations/<name>/run_acceptance_gate.py`); the ADR-0028 75 %
   threshold plus the security-negative checks must pass.
4. **Grow the Stage-2 directories with real content** — `tests/` per
   ADR-0504 (`contract/`, `tasks/`, `prompts/` suites filled, green in the
   zuno-demo-agents CI, attested by its release). Empty stub directories
   are not Stage 2.
5. **Flip `zuno.status` to `active`** in the bundle's `agent.okf.md` in
   zuno-demo-agents and promote that release (`make d3 admit agents`) —
   only after steps 1–4; UnifAI serves only an `active` agent (ADR-0007).
6. **Update the agent README** — stage line to Stage 2, evolution facts
   (served by UnifAI, gate date), next steps cleared. Re-run
   `python3 platform/docs/check_knowledge_refs.py` and
   `python3 platform/docs/check_docs.py`.
