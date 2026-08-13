# ADR-0044: Use PatternFly React for the agent frontend

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

`components/agent-frontend/static/style.css` explicitly states that it is hand-written CSS approximating PatternFly 5. The project requirement is to use the PatternFly framework, not only its visual vocabulary.

## Decision

Build the shared frontend with PatternFly React components and a reproducible frontend toolchain (for example Vite). Produce static assets at build time and continue serving them with the lightweight Go server. Keep runtime API endpoint injection from environment into JavaScript context.

## Consequences

The UI conforms to the requested framework and gains accessible, maintained components while preserving a small production runtime image.

## Security considerations

Use dependency pinning, vulnerability scanning, CSP-compatible assets and no runtime CDN dependency.

## Operational considerations

Replace hand-rolled PatternFly-like classes and add frontend build/lint/accessibility checks.

## Implementation state

**Implemented (2026-08-05).**

- `components/agent-frontend/web` is a Vite + React + TypeScript project built against the real `@patternfly/react-core` package (not an approximation) - `web/src/portal/Portal.tsx` and `web/src/chat/Chat.tsx` replace the previous hand-rolled-CSS Go templates with PatternFly `Masthead`/`Page`/`Gallery`/`Card`/`Form`/`Alert`/`Spinner` components. This required first re-verifying the "no package-manager access" assumption the earlier hand-rolled CSS was built under: this environment does have real npm registry and nodejs.org access, so the earlier constraint no longer holds and the ADR's own premise could be implemented literally rather than deferred.
- Toolchain: Vite 5 + `@vitejs/plugin-react`, TypeScript 5 strict mode, `package-lock.json` committed so `npm ci` reproduces exact dependency versions. `components/agent-frontend/Dockerfile` gained a `node:20-alpine` build stage (`npm ci && npm run build`) ahead of the existing Go build stage; the final UBI9-minimal runtime image is unchanged in kind - it now copies `web/dist` instead of the old `static/chat.js`/`static/style.css` (deleted).
- Runtime config injection: each Go-rendered page (`internal/portal`, `internal/chat`) is now a thin per-request HTML shell - a `<div id="root">` plus a `<script id="zuno-config" type="application/json">` blob of server-computed state (session, portal tiles, agent display name) - rather than server-templated HTML, since a static Vite bundle can't bake per-request values in at build time. `internal/assets` resolves each page's content-hashed JS/CSS from `web/dist/.vite/manifest.json` at server startup, including a transitive walk over the manifest's `imports` graph to collect CSS pulled in by a shared chunk.
- Security: dependency pinning via committed `package-lock.json`; CSP-compatible/no-runtime-CDN is satisfied by construction - every asset is built into `web/dist` and served same-origin under `/static/`. `npm audit` found a real moderate-severity `esbuild` advisory bundled with the entire Vite 5.x line ([GHSA-67mh-4wv8-2f99](https://github.com/advisories/GHSA-67mh-4wv8-2f99), affects only `vite dev`, never the shipped build) with no non-breaking fix - documented as a **v1 hardening recommendation** (upgrade to Vite 6+) rather than silently carried or force-fixed. Wiring `npm audit`/Trivy into CI is **not done** - no `.github/workflows/` existed yet at the time.
- Operational: `npm run build` (`tsc --noEmit` + `vite build`) and `npm run lint` (ESLint with `@typescript-eslint`, `react-hooks`, `eslint-plugin-jsx-a11y` recommended rules) both ran clean; not wired into CI for the same reason as above.
- What ADR-0045 (SSE streaming) needed from this rewrite: `web/src/chat/Chat.tsx` is what consumes the streamed response - see that ADR's own implementation note.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0008](0008-use-one-frontend-and-one-bff-deployment-per-agent.md)
- [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md)
