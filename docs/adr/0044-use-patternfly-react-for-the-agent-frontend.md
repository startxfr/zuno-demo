# ADR-0044: Use PatternFly React for the agent frontend

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

`components/agent-frontend/static/style.css` explicitly states that it is hand-written CSS approximating PatternFly 5. The project requirement is to use the PatternFly framework, not only its visual vocabulary.

## Decision

Build the shared frontend with PatternFly React components and a reproducible frontend toolchain (for example Vite). Produce static assets at build time and continue serving them with the lightweight Go server. Keep runtime API endpoint injection from environment into JavaScript context.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

The UI conforms to the requested framework and gains accessible, maintained components while preserving a small production runtime image.

## Security considerations

Use dependency pinning, vulnerability scanning, CSP-compatible assets and no runtime CDN dependency.

## Operational considerations

Replace hand-rolled PatternFly-like classes and add frontend build/lint/accessibility checks.

## Implementation state

**Implemented (2026-08-05).** `components/agent-frontend/web` is a Vite +
React + TypeScript project built against the real `@patternfly/react-core`
package (not an approximation) - `web/src/portal/Portal.tsx` and
`web/src/chat/Chat.tsx` replace the previous hand-rolled-CSS Go templates
with PatternFly `Masthead`/`Page`/`Gallery`/`Card`/`Form`/`Alert`/`Spinner`
components. This required first re-verifying the "no package-manager
access" assumption the earlier hand-rolled CSS was built under: this
environment does have real npm registry and nodejs.org access (verified by
actually installing `@patternfly/react-core`/`@patternfly/chatbot` and
downloading a Node 20 toolchain in this phase), so the earlier constraint
no longer holds and the ADR's own premise ("vendoring... rather than
approximating it") could be implemented literally rather than deferred.

Toolchain and reproducibility (Decision: "a reproducible frontend toolchain
... Produce static assets at build time"): Vite 5 + `@vitejs/plugin-react`,
TypeScript 5 in strict mode, with `package-lock.json` committed so
`npm ci` reproduces exact dependency versions. `components/agent-frontend/Dockerfile`
gained a `node:20-alpine` build stage (`npm ci && npm run build`) ahead of
the existing Go build stage; the final UBI9-minimal runtime image is
unchanged in kind (Decision: "continue serving them with the lightweight
Go server") - it just now copies `web/dist` instead of the old
`static/chat.js`/`static/style.css` (deleted).

Runtime config injection (Decision: "Keep runtime API endpoint injection
from environment into JavaScript context"): each Go-rendered page
(`internal/portal`, `internal/chat`) is now a thin per-request HTML shell -
a `<div id="root">` plus a `<script id="zuno-config" type="application/json">`
blob of server-computed state (session, portal tiles, agent display name -
`web/src/shared/types.ts`) - rather than server-templated HTML, since a
static Vite bundle can't have per-request/per-deployment values baked in
at `npm run build` time. `internal/assets` resolves each page's
content-hashed JS/CSS from `web/dist/.vite/manifest.json` at server
startup (Vite's own documented "backend integration" pattern), including a
transitive walk over the manifest's `imports` graph to collect CSS pulled
in by a shared chunk (verified against a real build's manifest - see the
component's git history for the exact resolved paths this produced).

Security considerations: dependency pinning is `package-lock.json`
(committed); CSP-compatible/no-runtime-CDN is satisfied by construction -
every asset (JS, CSS, the PatternFly font/icon/background files) is built
into `web/dist` and served same-origin under `/static/`, no `<link>`/`<script>`
ever points off-origin. `npm audit` was run manually against the pinned
set (real finding, not a placeholder): the entire Vite 5.x line bundles a
moderate-severity `esbuild` advisory
([GHSA-67mh-4wv8-2f99](https://github.com/advisories/GHSA-67mh-4wv8-2f99) -
`esbuild`'s *development* server accepts cross-origin requests). This
doesn't reach the shipped image - the Dockerfile's Node stage only ever
runs `npm run build`, never `vite dev` - but there is no non-breaking fix;
`npm audit fix --force` would move to Vite 6, a breaking change not taken
in this pass. Documented here as a **v1 hardening recommendation**
(upgrade to Vite 6+ once its breaking changes are reconciled) rather than
silently carried or silently "fixed" with an unverified major-version
bump. **Not done**: wiring `npm audit`/Trivy into CI as standing
coverage - this repository has no CI pipeline yet (`.github/workflows/`
doesn't exist, see `.github/README.md`), the same gap already noted for
every other CI-shaped operational consideration in this build.

Operational considerations ("add frontend build/lint/accessibility
checks"): `npm run build` (`tsc --noEmit` + `vite build`) and
`npm run lint` (ESLint with `@typescript-eslint`, `react-hooks`, and
`eslint-plugin-jsx-a11y`'s recommended accessibility rules -
`web/.eslintrc.cjs`) both ran clean in this phase's development
environment (Node 20, fetched fresh from nodejs.org since this sandbox's
default Node 16 predates Vite 5's minimum). Not wired into CI for the same
reason as the vulnerability-scanning gap above.

What ADR-0045 (SSE streaming) needed from this rewrite: the chat client
(`web/src/chat/Chat.tsx`) is what actually consumes the streamed response
- see that ADR's own implementation note for the client-side half of the
SSE contract.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0008
- ADR-0051

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
