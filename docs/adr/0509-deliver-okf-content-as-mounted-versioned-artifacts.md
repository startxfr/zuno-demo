# ADR-0509: Deliver OKF content as mounted versioned artifacts

- **Status:** Proposed
- **Target:** OKF v0.3
- **Date:** 2026-08-18
- **Decision owners:** Zuno Demo architecture team

## Context

After OKF v0.2, components still get OKF content the way they always
have: baked into images at build time from the pinned ref (ADR-0507
changed the source, not the mechanism). That makes any content change —
a reworded prompt, a widened task ceiling, a quota bump — an image
rebuild and rollout of up to five components, even though nothing about
the code changed. The stream's end state (ADR-0510: the operator watches
`zuno-okf` and reconciles running agents) is impossible while content
and image are one artifact. The seam to cut is already built: ADR-0508
confines every component's OKF reads to one hook module, and the AIAgent
operator already generates an OKF-reference ConfigMap per agent (pure
bookkeeping today — `internal/controller/resources.go`) and owns the
per-agent Deployments it would need to mount anything into.

## Decision

1. **The operator materializes OKF content as a per-agent mounted
   artifact.** For each `AIAgent` CR, the operator renders the agent's
   bundle (`agents/<name>/` at a resolved `zuno-okf` ref) plus the
   policy slices its declarations reference into versioned ConfigMaps
   projected into the frontend, BFF and — for the shared services'
   per-agent registrations — a well-known mount consumed by Agent
   Runtime and MCP Gateway. Size limits are respected by splitting per
   directory; if a bundle outgrows ConfigMap practicality the artifact
   becomes an OCI artifact pulled by an init container, same mount
   contract. The existing OKF-reference ConfigMap evolves into this
   artifact's manifest (ref, content hash, render timestamp).

2. **Components read OKF content from the mount through their ADR-0508
   hooks — and only there.** Each hook gains a content-source order:
   mounted artifact if present and valid, else the baked copy (which
   remains in images throughout OKF v0.3 as fallback and for
   non-CR-managed agents). The hook logs which source it serves; the
   conformance suite (ADR-0508) runs against both paths.

3. **Integrity is verified before mount.** The operator verifies the
   ADR-0106 bundle signature at the resolved ref before rendering;
   unsigned or signature-failing content is never materialized, and the
   failure is a named status condition, not a silent skip. Hooks
   additionally check the artifact's content hash against its manifest
   at load.

4. **The CR gains an explicit content source field and condition.**
   `spec.okfContentSource` — `Baked` (default; today's behavior,
   bit-for-bit) or `Mounted` (clauses 1–3 active) — makes the switch
   per-agent, reviewable and reversible. A new status condition
   `OKFContentReady` reports resolved ref, hash and mount state;
   `okfBundleRef` (ADR-0507 semantics) names *what* to resolve,
   `okfContentSource` says *how* it reaches pods. The five existing
   conditions are untouched.

## Consequences

Content changes decouple from image rebuilds: with `Mounted`, a new
`zuno-okf` ref can reach running agents by re-rendering artifacts —
which is exactly the lever ADR-0510's watch loop pulls. The operator
grows its first content-touching responsibility, a deliberate,
signature-gated exception to its "never the source of OKF semantics"
posture: it still interprets nothing, it ferries verified bytes.
Rollout is incremental by design — per agent, opt-in, with Naveo as the
WP-52 proof and `Baked` as the standing fallback.

## Security considerations

The mount path inherits the supply chain: signature verification
(ADR-0106) moves from build-time-only to render-time, so content
reaching pods is verified content, always. The operator needs read
access to `zuno-okf` — a read-only deploy credential, no write path.
ConfigMap artifacts are namespace-local, owner-referenced, and carry
definitions only (no secrets by construction — the package never holds
them, ADR-0506). A hook must fail closed if the mounted artifact is
present but hash-invalid: falling back to baked on *corruption* would
mask tampering, so fallback applies only to *absence*.

## Operational considerations

`OKFContentReady` makes content state observable per agent (`oc get
aiagents` shows ref and hash alongside the existing conditions).
Rendering failures requeue with backoff like every reconcile error.
The dual-path period is bounded: baked fallback remains until the
stream closes, then its retirement is a future decision, not assumed
here. Artifact size and count are bounded per agent; the OCI-artifact
escape hatch is specified before it is needed.

## Acceptance criteria

- With `okfContentSource: Mounted` on Naveo: pods serve mounted content
  (hook logs confirm), `OKFContentReady` is True with ref and hash, and
  behavior matches baked-mode byte-for-byte for identical refs.
- Signature-failing content is never mounted; the condition names the
  failure; a hash-corrupted mounted artifact fails closed.
- `okfContentSource: Baked` (and absence of the field) reproduces
  today's behavior exactly; envtest covers both modes and the
  conditions.

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0106](0106-enforce-okf-bundle-signing-and-validation.md)
- [ADR-0308](0308-expand-agent-lifecycle-management-through-the-aiagent-operator.md)
- [ADR-0327](0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md)
- [ADR-0350](0350-provide-an-aiagent-kubernetes-crd-and-operator.md)
- [ADR-0507](0507-consume-the-zuno-okf-repository-through-a-single-pinned-reference.md)
- [ADR-0508](0508-isolate-okf-parsing-behind-per-component-adaptation-hooks.md)
- [ADR-0510](0510-make-the-aiagent-operator-watch-the-zuno-okf-repository.md)
