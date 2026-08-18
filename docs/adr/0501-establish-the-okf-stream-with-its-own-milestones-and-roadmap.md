# ADR-0501: Establish the OKF stream with its own milestones and roadmap

- **Status:** Proposed
- **Target:** OKF v0.1
- **Date:** 2026-08-18
- **Decision owners:** Zuno Demo architecture team

## Decision

Open a standalone version stream for the Open Knowledge Format initiative,
decoupled from the platform's own v0–v0.4 bands, with three milestones:

- **OKF v0.1 — content excellence, in-repo.** Make the current OKF content
  under `agents/` the authoritative, validated statement of who (Keycloak
  entitlement group + business roles) can use what (MCP tools, RAG knowledge
  domains, model classification ceilings, quota classes) for what (tasks and
  prompts) under which policies (`policies/tools/`, `policies/knowledge/`,
  and the new `policies/quotas/`) — while `agents/` still lives in this
  repository.
- **OKF v0.2 — extraction.** Move all OKF content into a standalone
  `zuno-okf` git repository consumed by this repository through a single
  pinned reference, with per-component adaptation hooks and a shared
  conformance suite.
- **OKF v0.3 — live reconciliation.** The AIAgent operator watches the
  `zuno-okf` repository and reconciles running agent configuration from it,
  within the boundaries the `AIAgent` CR declares.

Mechanics fixed by this record: the **05xx ADR band is reserved for the OKF
stream** (a future platform v0.5 stream takes the next free band — the repo's
banding convention is bands-follow-streams, not bands-follow-platform-
versions); OKF-stream ADRs carry `- **Target:** OKF v0.1|v0.2|v0.3` headers;
work packages continue the existing global WP series (WP-43 onward) but are
tracked in [docs/roadmap/okf-roadmap.md](../roadmap/okf-roadmap.md), which
inherits the v0.1–v0.3 roadmap's execution model unchanged.
[docs/adr/README.md](README.md) remains the sole authority for ADR status.

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives,
Consequences, Security/Operational considerations, Migration/evolution and
Related ADRs.
