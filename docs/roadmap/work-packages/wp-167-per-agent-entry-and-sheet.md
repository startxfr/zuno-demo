# WP-167: Serve a per-agent entry and descriptive sheet from the admitted bundle

- **State:** Not started
- **ADRs:** [ADR-0582](../../adr/0582-serve-a-per-agent-entry-and-descriptive-sheet-from-the-admitted-bundle.md), [ADR-0583](../../adr/0583-require-group-visibility-and-object-level-authorisation-before-per-agent-entries.md), [ADR-0584](../../adr/0584-define-agent-lifecycle-states-roles-and-incident-revocation.md)
- **Depends on:** [WP-155](wp-155-migrate-remaining-agents-and-cut-demo222-over.md)
- **Related:** [ADR-0575](../../adr/0575-upstream-generic-unifai-changes-and-isolate-zuno-specific-code.md), [WP-148](wp-148-unifai-parity-memory-routing-quota-ux.md)
- **Target:** v0.12
- **Estimated files touched:** ~15 in the UnifAI fork (operator mapping and CRD, multi-agent blueprint metadata, UI route and sheet component, tests) and ~4 in `zuno-demo` (OKF schema allowlists, chart values, evidence).

> A demo script opens one URL per agent, and the platform explains each agent
> from the artifact that defines it. Decisions taken 2026-10-23: the display
> block travels as blueprint metadata, so visibility is UnifAI's existing group
> rule (ADR-0583); the sheet owner and security reviewer are the demo decision
> owner (ADR-0584 acceptance note).

## Goal

`/agents/<agent>` shows a sheet built only from the public fields of the
admitted bundle, for a caller whose groups intersect the agent's access
groups; anyone else gets the same not-found as for an unknown agent.

## Steps

1. **Operator, display block (lot 1).** Parse `zuno.ui`, the title, the
   description, the state, the task titles, the maintainer and the
   classification ceiling into a typed `Display` value; check `icon` and
   `color` against allowlists; report it in `UnifaiAgentBundle.status.display`;
   write it into the emitted workflow's blueprint metadata. A unit test fails
   when a hidden field (system prompt, `allowed_tools`, `allowed_knowledge`,
   retrieval settings, `local_only_for`, quota class, access group names,
   digests, signatures) appears in either place. Operator release by a9.
2. **API (lot 2).** Return the display metadata on a blueprint read that the
   caller may see, with the existing object checks; no new endpoint.
3. **UI (lot 2).** The `/agents/<agent>` route and the sheet component, plain
   text or restricted Markdown, read-only, not-found for non-members.
4. **OKF schema.** Allowlists for `icon` and `color` in
   `platform/okf/schema/`, and a conformance test in `zuno-demo-agents`.
5. **Proof on demo333.** consultant-01 sees the tekos and arkos sheets and not
   the comage sheet; sale-01 sees the comage sheet only; an unknown agent and a
   hidden agent return identical responses; browser check of the sheet.

## Acceptance

- The hidden-field test passes and the sheet shows only the public fields.
- Visibility proof on demo333 as in step 5, with a screenshot in the evidence.
- The generic parts (route, display block, component) carry no Zuno field name
  and are ready to offer upstream (ADR-0575).

## Open questions

- Placeholder agents: no entry for ordinary users; whether the platform team
  sees a "coming soon" entry is left to ADR-0584 and is not built here.
