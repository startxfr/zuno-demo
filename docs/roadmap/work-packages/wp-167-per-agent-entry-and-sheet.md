# WP-167: Serve a per-agent entry and descriptive sheet from the admitted bundle

- **State:** Repo work in review
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

## Progress (2026-10-23)

Fork `devel` (9d4eb0218) carries lot 1 and the UI sheet; nothing is deployed yet.

- Operator: `bundleDisplay` builds the closed public list (agent, title, description, tile
  presentation, maintainer, state, classification ceiling, task titles) from the admitted bundle,
  reports it in `status.display` and writes it as the `display` metadata of each emitted workflow
  (`blueprint.metadata.set`). Tests: the sheet never carries a sentinel placed in a prompt, tool,
  knowledge, retrieval, access group or limit field, and the field list is pinned.
- multi-agent: `display` is a client-settable blueprint metadata key with a validator (known
  fields, bounded plain text without raw HTML, icon and color shapes, at most 20 tasks); 26 unit tests.
  The existing summary endpoint already returns the metadata under the caller's visibility rules.
- UI: `/agents/<agent>` reads the summaries the caller can see and shows the sheet, or the same
  not-found for an unknown and a hidden agent. The image builds; not yet seen in a browser.
- Next: an operator release (a9), a UI image and the role rerun (68), then the proof of step 5
  (consultant-01 sees tekos and arkos, sale-01 sees comage only, hidden equals unknown).
- Open point: the OKF schema allowlists for `icon` and `color` (step 4) are not written; the
  runtime validator accepts a keyword of lower case letters, digits and hyphens.

