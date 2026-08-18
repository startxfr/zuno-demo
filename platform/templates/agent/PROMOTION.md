# Agent promotion checklist (ADR-0502)

The single, named path from **Stage 1 "scaffolded"** to **Stage 2
"promoted"** — superseding the ad-hoc tail every `NEXT_STEPS.md` used to
restate. An agent is Stage 2 when and only when it meets ADR-0502
clause 2's criteria; this checklist is those criteria in execution
order. Stage is determined by these criteria, never by directory shape.

Scaffold-time steps (persona review, Keycloak merge, policy entries,
GitOps Application, check.yml, validators) are the generated
`NEXT_STEPS.md`'s own numbered items and are assumed done before
promotion starts.

1. **Human scenario review** — review the 20 scenarios in
   `evaluations/<name>/scenarios.yaml` (ADR-0027). No live gate run
   counts before this checkpoint (ADR-0326's completion pattern).
2. **Operator deploy via the `AIAgent` CR** — the CR
   (`gitops/charts/<name>/templates/aiagent.yaml`) is the deployment
   interface (ADR-0327/ADR-0308); all five status conditions must reach
   `True`. (Tekos alone is grandfathered on plain manifests as the
   ADR-0350 coexistence proof.)
3. **Evaluation gate** — run the acceptance gate
   (`evaluations/<name>/run_acceptance_gate.py`); the ADR-0028 75 %
   threshold plus the security-negative checks must pass.
4. **Grow the Stage-2 directories with real content** — `deployment/`
   per ADR-0503 (generated CR-spec snapshot + README naming
   chart/Applications/sync-waves) and `tests/` per ADR-0504
   (`contract/`, `tasks/`, `prompts/` suites filled, green in the lint
   chain). Empty stub directories are not Stage 2.
5. **Flip `zuno.status` to `active`** in `agents/<name>/agent.okf.md` —
   only after steps 1–4; the portal tile and Agent Runtime's generic
   dispatch follow the flip.
6. **Update the agent README** — stage line to Stage 2, evolution facts
   (CR-managed, live route, gate date), next steps cleared. Re-run
   `python3 platform/supply-chain/validate_okf_bundle.py`,
   `python3 platform/docs/check_knowledge_refs.py` and
   `python3 platform/docs/check_docs.py`.
