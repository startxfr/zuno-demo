# ADR-0582: Serve a per-agent entry and descriptive sheet from the admitted bundle

- **Status:** Implemented (2026-11-05, WP-167: the route, the typed `status` display block, the hidden-field tests, the schema allowlists and the visibility proof, repeated in a browser on UnifAI 0.1.59)
- **Target:** v0.12
- **Date:** 2026-10-22
- **Decision owners:** Zuno Demo architecture team
- **Amends:** [ADR-0561](0561-adopt-unifai-as-the-agent-platform.md) (clause "the per-agent frontend Route becomes one shared UI")
- **Related:** [ADR-0564](0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md), [ADR-0583](0583-require-group-visibility-and-object-level-authorisation-before-per-agent-entries.md), [ADR-0584](0584-define-agent-lifecycle-states-roles-and-incident-revocation.md), [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md), [ADR-0575](0575-upstream-generic-unifai-changes-and-isolate-zuno-specific-code.md)

## Context

Before UnifAI, each agent had a tile in the portal and its own frontend Route
([ADR-0008](0008-use-one-frontend-and-one-bff-deployment-per-agent.md)). The portal filtered tiles by `zuno.access.groups` and
`status: active`; the BFF enforced the `agent_<name>` group (ADR-0040) and
frontend visibility was never treated as authorisation. ADR-0561 retired the
per-agent Route in favour of one shared UnifAI UI.

The shared UI has no stable address for one agent: its agent repository is a
generic browser of workspace elements, and a chat is reached through a
blueprint id. The demo scripts, and users who bookmark an agent, need a stable
entry per agent and a short description of what the agent does, who maintains
it and what it may touch. The OKF frontmatter already carries most of it
(`title`, `description`, `zuno.ui`, tasks, classification), but the
unifai-operator maps only part of it: `zuno.ui` ends up in `status.unmapped`.

## Decision

**UnifAI serves one client-side entry and one descriptive sheet per agent,
rendered from the fields of the admitted bundle, never from hand-written
resources.**

1. **No new Kubernetes Route.** The entry is a path of the shared UI
   (`/agents/<agent>`), so ADR-0561's single UI and single Route stand.
   > **Correction note (2026-11-02).** The single UI and single Route are those of the **agent** platform; [ADR-0587](0587-admit-additional-user-experiences-over-the-one-governed-backend.md) admits other experience clients with their own Route, which serve no agent.
2. **Single source.** The sheet is built from the bundle the operator verified
   and admitted (ADR-0564, ADR-0578, ADR-0580). The operator maps the display
   fields into a typed `status` block of `UnifaiAgentBundle`; the UI reads that
   block. A field set on a custom resource by hand never reaches a sheet.
3. **Public fields**, shown to a caller who may use the agent: title,
   description, tile description, icon, color, state (ADR-0584), task titles,
   maintainer, classification ceiling.
4. **Hidden fields**, never in the sheet or the status block: system prompts,
   `allowed_tools`, `allowed_knowledge`, retrieval settings, `local_only_for`,
   quota class, access group names, digests, signatures and internal sources.
5. **Visibility.** The entry and the sheet exist only for a caller whose
   groups intersect the agent's access groups. Anyone else receives the same
   not-found response as for an unknown agent, so existence is not revealed.
   This depends on ADR-0583.
6. **Sanitised content.** Text fields are plain text or restricted Markdown
   (no raw HTML). `icon` and `color` are checked against allowlists by the
   OKF schema (`platform/okf/schema/`) at authoring time and again by the
   operator at admission.
7. **Read-only.** The sheet performs no state change. Actions on an agent
   (activate, deprecate, retire) are ADR-0584 operations done through pull
   requests, not through the sheet.
8. **Generic first.** The route, the `status` display block and the sheet
   component are written generically in the fork and offered upstream
   (ADR-0575). Zuno-specific field names stay in the operator mapping.

## Consequences

A demo script can open one URL per agent, and the platform explains each
agent from the same artifact that defines it, so a sheet cannot drift from
the running agent. The operator gains a display mapping and a CRD change,
which is an operator release. The UI gains a route and a sheet component.

Placeholder agents (not yet active) have no entry for ordinary users; the
platform team sees them as "coming soon" if ADR-0584 allows it.

## Security considerations

The sheet is a disclosure surface: the public and hidden lists above are the
contract, and a test must fail when a hidden field appears in the status block
or the rendered page. Author-controlled text is rendered without raw HTML and
visual fields are allowlisted. The entry is a navigation aid, not an
authorisation: the model and tool gateways keep enforcing group and
classification rules with the caller's own token (ADR-0563, ADR-0565).

## Operational considerations

Needs ADR-0583 first, an operator release (CRD `status` block and mapping)
and a fork change; none of it touches a cluster until the pilot (ADR-0573).
Verification: a user without the agent's group gets a not-found identical to
an unknown agent, and a user with it sees only the public fields.

## Implementation note (2026-11-05)

Every clause is in effect: the sheet is a path of the shared UI (clause 1), built from the admitted bundle through the operator's typed `status` block (2), with the public and hidden field lists tested (3, 4), the same not-found for a hidden and an unknown agent (5), plain-text content and the `icon` and `color` allowlists (6), no state change from the sheet (7) and no Zuno field name in the generic parts (8). The visibility proof was made on 2026-10-23 and repeated on UnifAI 0.1.59 on 2026-11-05: [evidence](../roadmap/evidence/wp-167-per-agent-sheet-proof-unifai-0.1.59-2026-11-05.md). The "coming soon" entry for placeholder agents is left to ADR-0584, as the decision says.
