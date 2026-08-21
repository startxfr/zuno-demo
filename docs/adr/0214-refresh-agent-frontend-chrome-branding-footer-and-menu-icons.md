# ADR-0214: Refresh agent-frontend chrome: branding, footer and menu icons

- **Status:** Implemented (2026-08-19) - parts 1 and 2 exactly as decided below, part 3 with a deliberately narrower scope (see its own note) - all merged, verified (build/lint clean, browser-rendered screenshots), and live: `tekos-frontend` rebuilt and redeployed on the real cluster (same temporary `gitops/charts/tekos` unpin as [ADR-0212](0212-introduce-persistent-navigable-chat-conversations.md#status)). **Update (2026-08-21):** part 3's kebab menu itself has since shipped, via [ADR-0515](0515-per-conversation-tabs-one-browser-tab-per-agent.md)/WP-061 - `ConversationList.tsx` now has a right-aligned kebab with Rename, Star/Unstar, Delete (soft) and Delete permanently (hard). This is narrower than this point's original text described: Share and Clone are still not there, since those remain an [ADR-0213](0213-introduce-role-based-conversation-sharing.md) dependency, and ADR-0213 itself is still `Proposed` with no code and no work package - the kebab lands its remaining two actions whenever ADR-0213 does.
- **Target:** v0.2
- **Date:** 2026-08-18
- **Decision owners:** Zuno Demo architecture team

## Decision

Three independent, cosmetic changes to the one shared `agent-frontend` codebase (ADR-0008, so this applies identically to every agent), sequenced alongside/after ADR-0212 since the third change decorates its new left-hand conversation menu:

1. **Placeholder logo.** A static placeholder SVG asset added to `components/agent-frontend/web/src/assets/` and rendered inside `MastheadBrand`, to the left of the existing text, on `chat/Chat.tsx`, `portal/Portal.tsx`, and `profile/Profile.tsx`. Explicitly a placeholder to be swapped for real branding later - this ADR authorizes the mechanism (an SVG asset in the brand slot), not a final design.
2. **Shared footer.** A new `web/src/shared/Footer.tsx`, reused verbatim by all three pages exactly the way `shared/UserMenu.tsx` already is, rendered as the last `PageSection` of each page. Three links: startx.fr, the `zuno-demo` GitHub repository, and a GitHub "new issue" link for bug reports. On `chat/Chat.tsx` specifically, the message composer already occupies the page's one `stickyOnBreakpoint: "bottom"` slot, so the footer cannot share it - it renders as a normal, non-sticky `PageSection` reached by scrolling, unlike the always-visible footer on Portal and Profile.
3. **Left-menu icons.** Every entry in ADR-0212's `ConversationList.tsx` gets a `@patternfly/react-icons` icon (already a dependency in `web/package.json` - no new package): filled/outline `StarIcon`/`OutlinedStarIcon` for the star toggle, `CommentIcon` per row. **Implemented without the kebab menu** this point originally described: the kebab's own actions (share, clone, rename) are an ADR-0213 dependency that ADR-0213 itself was explicitly out of scope for this implementation pass (deferred, along with the rest of that ADR) - shipping a kebab with no actions behind it, or only "rename", would be worse than not shipping one. Rename is reachable via double-click on a row's title instead; the kebab lands whenever ADR-0213 does.

Explicitly out of scope: moving or restyling `shared/UserMenu.tsx`. Confirmed in `chat/Chat.tsx`, `portal/Portal.tsx`, and `profile/Profile.tsx` that it already renders inside PatternFly's right-aligned `MastheadContent`/`Toolbar` slot on every page, consistently, with no custom CSS overriding that layout - there is nothing to move.

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives considered, Consequences, Security/Operational considerations, Migration/evolution and Review evidence.

## Acceptance criteria

- Chat, Portal, and Profile all render the same placeholder SVG in `MastheadBrand` and the same `Footer.tsx` at the bottom, with three working links (startx.fr, the `zuno-demo` GitHub repo, a GitHub new-issue link).
- `UserMenu`'s position and content are visually unchanged - a regression check only, since this ADR makes no change there.
- Every `ConversationList.tsx` row (ADR-0212) shows a PatternFly icon; the `web/package.json` diff adds no new dependency.
- `Footer.tsx` has exactly one implementation, imported by all three pages - not three separate copies.

## Related ADRs

- [ADR-0008](0008-use-one-frontend-and-one-bff-deployment-per-agent.md)
- [ADR-0044](0044-use-patternfly-react-for-the-agent-frontend.md)
- [ADR-0212](0212-introduce-persistent-navigable-chat-conversations.md) (depends on - this ADR decorates its left menu)
