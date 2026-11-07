# WP-234: World-model web, API and UI (delivers ADR-0604 D4, D7, D8)

- **State:** Repo work in review
- **ADRs:** ADR-0604
- **Depends on:** WP-231, WP-233
- **Blocks:** WP-235
- **Estimated files touched:** ~40

> Execute this brief as a standalone task from the repository root.

## Goal

The browser experience and its API, complete and tested end to end without a GPU against the runtime's mock adapters.

## ADR references

ADR-0604 D4, D7, D8, §4.2, §4.3, §6.1, §6.3, §8, §10.

## Repo changes

1. `components/world-model-web/` API (FastAPI): the §6.1 REST routes and `WS /api/sessions/{id}/stream` relayed to the
   runtime; identity from the oauth2-proxy token, validated (issuer, audience, groups `zuno-world-model-users`,
   `ocp-ai-ops`, `ocp-paas-ops`); the §4.3 state machine; one lease (409 when busy, idle and lease expiry); prompt
   pipeline: length ceiling and deny list always, then the D8 call to the ai-gateway (C1 header, user token, JSON
   verdict), degrading to the filtered prompt with a visible flag; a mid-session prompt becomes a world-edit request
   (ADR-0604 D3) and the UI shows the `RECONDITIONING` transition; `zuno_world_*` metrics without session ids or prompts
   as labels; OpenTelemetry spans.
2. UI (React 18, PatternFly 6, vite; stack from `git show b5c9b2bc^:components/agent-frontend/web/package.json`): preset
   cards, prompt box, canvas fed by a WebCodecs `VideoDecoder` (avc1), Pointer Lock with WASD and arrows, a state banner,
   the "generative AI, not a 3D simulation" disclosure, and a technical panel (displayed FPS against engine step time,
   input-to-display latency, prompt requested and applied, encoder in use).
3. `Dockerfile`: Node 20 build stage, then `python:3.12-slim` serving the API and the static UI; both from the
   `zuno-ai-build` mirrors; second image in `world_model_build` and the build matrix.
4. Tests: API unit tests registered in `lint.yml`; a local end-to-end run (podman: runtime with mocks + web, OIDC
   stubbed) driven by Playwright with the `chrome` channel, because the bundled Chromium has no H.264 decoder.

## Result (2026-11-07)

`components/world-model-web`: the API (28 tests, mutation-checked on the edit bypass, audience, ownership and lease), the UI
(typecheck, 5 unit tests, production build), the Dockerfile (built and run locally as an arbitrary UID), the build role and CI
steps, and `platform/world-model/tests/e2e` (a real Chrome against the mock runtime: 10 steps, three consecutive passes, input to
display measured). Findings that changed the design: the runtime's video header now carries the control sequence each frame
reflects (real latency, not an estimate), a detached session frees the GPU after 60 s, and files are made readable for an
arbitrary UID. OpenTelemetry spans are not in this lot: they ship with the dashboard in WP-236.

## Verification

The end-to-end run: login, preset, decoded video, WASD changes the frames, a re-prompt is applied, reset, a second session
gets "busy", a user outside the groups gets 403, the gateway switched off shows "enhancement off".
