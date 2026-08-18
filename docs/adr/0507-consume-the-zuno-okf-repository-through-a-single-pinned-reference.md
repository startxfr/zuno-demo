# ADR-0507: Consume the zuno-okf repository through a single pinned reference

- **Status:** Proposed
- **Target:** OKF v0.2
- **Date:** 2026-08-18
- **Decision owners:** Zuno Demo architecture team

## Context

Once ADR-0506 moves OKF content out, `zuno-demo` must still build images
that contain it: every consuming component's Dockerfile does a `COPY
agents ./agents` / `COPY policies ./policies` from the build context
(e.g. `components/mcp-gateway/Dockerfile`), the CI matrix signs bundles,
and the evaluation runner reads scenarios. An unpinned "always latest"
dependency on another repository would make builds unreproducible and
turn every `zuno-okf` merge into an untested instant platform change —
the opposite of the GitOps posture (ADR-0022). The AIAgent CR's
`okfBundleRef` is today a repo-relative path (`agents/<name>`,
pattern-enforced) whose contract line reads "a Git path, never mirrored"
(ADR-0327) — written when there was only one repository to be relative
to.

## Decision

1. **`zuno-demo` records exactly one pinned `zuno-okf` reference in
   exactly one file: `platform/okf/zuno-okf.ref`** — a tag or commit
   SHA, nothing else, reviewed like any dependency bump. No other file
   in `zuno-demo` may name a `zuno-okf` ref; generators, CI and docs
   read the pin file.

2. **CI fetches the pinned ref into the build context; the baked-image
   model is deliberately unchanged at this milestone.**
   `.github/workflows/build-publish.yml` (and the local build path the
   `*_build` Ansible roles drive) gains one step: fetch `zuno-okf` at
   the pin into the context root, so every existing `COPY agents ...` /
   `COPY policies ...` instruction keeps working against the fetched
   tree, byte-for-byte. Components still ship OKF content baked into
   images; what changes is only where the build gets it. Delivering
   content to *running* pods without rebuilds is OKF v0.3's business
   (ADR-0509), not this record's.

3. **`okfBundleRef` gains repo-qualified semantics, backward
   compatibly:** the full form is `<repo>@<ref>:agents/<name>`; the
   existing bare form `agents/<name>` remains valid and now means "that
   path in `zuno-okf` at the platform's pinned ref". This supersedes
   ADR-0327's "Git-relative path" wording by extension, not
   contradiction — the field stays a reference that is never mirrored
   into the CR; the operator keeps recording it without resolving it
   until ADR-0509/0510 give it a resolver. The CRD pattern validation
   widens accordingly (an additive, non-breaking schema change).

4. **The CI split is fixed:** `zuno-okf` CI validates itself
   (self-contained checks per ADR-0506 clause 3); `zuno-demo` CI is the
   sole executor of anything needing components or a cluster — image
   builds, bundle signing (ADR-0106) at the pinned ref, and the
   ADR-0342 evaluation runs, which check out the pin to read scenarios.
   Moving the pin is therefore the moment new OKF content is built,
   signed, evaluated and shipped — one reviewable event, replacing "it
   was in the same merge".

## Consequences

Reproducibility survives extraction: any image, signature or evaluation
result is traceable to one `zuno-okf` SHA via one file. The pin becomes
a routine maintenance object (bumped per governance cadence, tested by
the full existing gate on the bump PR). The interim WP-49 state — pin
consumed while in-repo copies still exist — is proven by building both
ways and comparing, before WP-50 deletes the copies.

## Security considerations

Pinning is the supply-chain property (ADR-0115): builds reference an
immutable SHA, and bundle signing binds signatures to exactly that
content. The fetch step must verify the ref resolves to the recorded
SHA (no branch names in the pin file) and needs read-only credentials
to `zuno-okf`. A malicious-or-mistaken `zuno-okf` merge cannot reach
the platform until a reviewed pin bump in `zuno-demo` — that review is
the new trust boundary and must be treated with policy-change rigor
when the diff touches `policies/`.

## Operational considerations

One new CI step and one new failure mode (pin fetch failure — fails the
build, never falls back to a cached tree silently). Local developer
builds get a `make`-level helper that performs the same fetch, so the
Dockerfile context is identical locally and in CI. The pin-bump PR's
diff should link the `zuno-okf` compare view for reviewability.

## Acceptance criteria

- `platform/okf/zuno-okf.ref` exists and is the only `zuno-okf` ref
  anywhere in `zuno-demo`.
- With in-repo copies still present (WP-49), images built from the
  fetched tree are functionally identical to images built from the
  in-repo copies.
- The CRD accepts both `okfBundleRef` forms; existing CRs are untouched
  and valid.
- A deliberate pin-fetch failure fails the build visibly.

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0022](0022-use-gitops-managed-declarative-agent-tasks-and-policies.md)
- [ADR-0106](0106-enforce-okf-bundle-signing-and-validation.md)
- [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md)
- [ADR-0327](0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md) (okfBundleRef wording extended by clause 3)
- [ADR-0342](0342-support-multiple-agent-graph-shapes-in-agent-runtime.md)
- [ADR-0506](0506-extract-okf-content-into-a-standalone-zuno-okf-repository.md)
- [ADR-0509](0509-deliver-okf-content-as-mounted-versioned-artifacts.md)
