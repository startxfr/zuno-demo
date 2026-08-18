# WP-52: Mounted OKF artifacts (promotes ADR-0509)

- **State:** Not started
- **ADRs:** ADR-0509
- **Depends on:** WP-50, WP-51
- **Blocks:** WP-53
- **Estimated files touched:** ~15 (A, operator) + ~12 (B, components)

> Execute this brief as a standalone task from the repository root.
> Before authoring or editing the CRD field, run `oc explain` against
> the deployed CRD generation to confirm the base you are extending.

## Goal

The operator materializes signature-verified OKF content (bundle +
referenced policy slices at a resolved zuno-okf ref) as per-agent
mounted artifacts; component hooks read the mount with baked fallback
on absence (fail closed on corruption); Naveo runs `Mounted` as the
proof while everything else stays `Baked`, bit-for-bit.

## ADR references

ADR-0509 clauses 1–4; ADR-0106 (render-time signature verification);
ADR-0508 (hooks are the only seam that changes).

## Preconditions (verify before starting)

- WP-50 + WP-51 merged. Operator envtest suite green at head.
- Read: `operator/aiagent-operator/internal/controller/resources.go`
  (the OKF-reference ConfigMap this evolves), `CONTRACT.md` (the
  "operator must NOT" list — clause-3 signature gating is the argued
  exception, cite it), the WP-05/ADR-0106 signing flow.

## Repo changes (step by step)

**Part A — operator:**
1. API: `spec.okfContentSource` (`Baked` default | `Mounted`),
   `OKFContentReady` condition; regenerate deepcopy/CRD/chart copy.
2. Renderer: resolve the agent's ref (ADR-0507 semantics; bare form =
   platform pin), verify the bundle signature, render bundle + policy
   slices into versioned ConfigMaps (split per directory; manifest
   ConfigMap carries ref/hash/timestamp — evolve the existing
   OKF-reference ConfigMap into this), project into the owned
   frontend/BFF Deployments and the shared-service registration mount;
   `Baked` renders nothing and reproduces today's objects exactly
   (envtest golden comparison).
3. Failure paths as conditions: unsigned/signature-fail → never
   materialized, named condition reason; size overflow → documented
   OCI-artifact escape hatch (spec'd, may be stubbed behind a clear
   error at this WP).
4. envtest both modes + conditions + signature-fail path.

**Part B — components:**
5. Each WP-51 hook gains the content-source order: mounted artifact if
   present and hash-valid → else baked; hash-invalid → fail closed
   (named startup/reload error, never fallback); log the serving
   source. Conformance fixtures run against both paths in CI.
6. Naveo's chart: `okfContentSource: Mounted`; every other CR
   untouched.

## What NOT to touch

Standard list; plus: Tekos (plain-manifest coexistence proof — no CR,
no mounts); no OKF semantic interpretation in the operator (it ferries
verified bytes; the ceiling logic is WP-53's set comparison, not
here); baked copies stay in every image.

## Acceptance checks

- envtest: golden identity in `Baked` mode; all condition paths in
  `Mounted`; signature-fail never mounts.
- Component suites green with both source paths; corrupted-hash test
  fails closed.
- `helm lint` on touched charts; `check_docs.py` passes.

## Operator / human follow-up (not executable by the model)

Deploy the operator + Naveo chart bump; confirm on-cluster:
`OKFContentReady` True with ref+hash, hook logs show `mounted`, Naveo
answers identically to its baked behavior at the same ref.

## Status updates (then re-run check_docs.py)

On merge: ADR-0509 → `Partially implemented (operator + hooks merged;
live Naveo proof pending)`; after the cluster confirmation →
`Implemented - see operator/aiagent-operator/ and each hook module.`
Index + tracker + MEMORY.md accordingly.

## Out of scope / deferred

- Watching the repo (WP-53). Retiring baked fallback (post-stream
  decision, per the ADR).
