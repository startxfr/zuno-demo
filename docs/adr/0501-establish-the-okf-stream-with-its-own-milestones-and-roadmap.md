# ADR-0501: Establish the OKF stream with its own milestones and roadmap

- **Status:** Implemented
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

## Update (2026-11-11): Implemented

Nothing remains open under this record. The stream mechanic (the 05xx band, the `OKF v0.x` targets, one ADR index)
has been in force since 2026-08-18, and the OKF v0.1 milestone closed on 2026-08-29. The outcomes of the two later
milestones were delivered in the platform bands, by records that supersede the ones that first defined them:

- **Extraction (OKF v0.2):** [ADR-0576](0576-extract-agent-definitions-and-corp-policies-into-the-zuno-demo-agents-repository.md)
  moved the agent definitions and corp policies into the `zuno-demo-agents` repository (superseding ADR-0506, ADR-0507
  and ADR-0510); [ADR-0508](0508-isolate-okf-parsing-behind-per-component-adaptation-hooks.md) isolates OKF parsing
  behind per-component hooks.
- **Live delivery (OKF v0.3):** [ADR-0580](0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md)
  consumes the signed corp OKF bundle by one digest pin, promoted by pull request (superseding ADR-0509), and
  [ADR-0611](0611-mirror-the-admitted-okf-release-into-the-internal-registry.md) serves the admitted release from an
  in-cluster mirror.

The OKF v0.2 and v0.3 milestones stay vacant; new OKF work is recorded in the platform bands.
