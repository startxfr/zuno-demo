# ADR-0510: Make the AIAgent operator watch the zuno-okf repository

- **Status:** Proposed
- **Target:** v0.10 (retargeted from v0.7 on 2026-09-05 — see ADR-0506's note. Previously retargeted from OKF v0.3 on 2026-08-30 — see ADR-0506's note)
- **Date:** 2026-08-18
- **Decision owners:** Zuno Demo architecture team

## Context

The AIAgent operator reconciles its CRs and nothing else: it watches
`AIAgent` plus owned objects (`SetupWithManager`,
`internal/controller/aiagent_controller.go`) and has never read git.
With ADR-0509 in place, OKF content reaches running agents as
operator-rendered mounted artifacts at a resolved ref — but something
still has to notice that `zuno-okf` moved and drive the re-render. Today
that something is a human bumping the pin (ADR-0507) and, for mounted
agents, nothing at all. The stream's goal — edit a prompt in the OKF
repository, watch the running agent update, keep every boundary intact —
needs the operator to close this last loop.

## Decision

1. **The operator gains a watch loop on `zuno-okf`:** it polls the
   configured tracking ref (a branch or tag pattern, set in
   `OperatorConfig`, webhook support an optional later addition) at a
   configured interval, resolves the commit SHA, and — when the SHA
   affecting a CR-managed agent's bundle or referenced policy slices
   changes — re-renders that agent's ADR-0509 artifact and updates its
   manifest. Per-agent pinning stays possible: a CR whose
   `okfBundleRef` names an explicit ref (ADR-0507 full form) is never
   moved by the tracking loop.

2. **The authority split is explicit and enforced in one direction.**
   The CR remains authoritative for infrastructure shape and for the
   ceilings it already declares (`groups`, `knowledgeDomains`,
   `toolCapabilities`); the OKF repository is authoritative for content
   *within* those ceilings. A repo change may **narrow** effective
   behavior without any CR change; a change that would **widen** beyond
   a CR-declared ceiling (a task adding a tool capability the CR does
   not list) renders nothing and surfaces as a condition failure — the
   widening lands only when a reviewed CR change raises the ceiling.
   The operator still interprets no OKF semantics; the ceiling check is
   a set comparison between CR lists and bundle declarations, in the
   same spirit as its existing namespace allowlist.

3. **Rollout semantics are fixed per change class:** content whose
   consumers re-read through their hooks (prompts, matrices, quota
   values read at request time) propagates by artifact update alone —
   hooks detect the manifest hash change and hot-reload; content that
   components load once at startup (task registry, schema-versioned
   structures) triggers a rolling restart of the affected Deployments,
   which the operator already owns. The per-change-class behavior is
   declared in the artifact manifest, not guessed by consumers.

4. **Scope: CR-managed agents with `okfContentSource: Mounted`, only.**
   Tekos, while it remains ADR-0350's plain-manifest coexistence proof,
   is out of scope; migrating it is a named optional precondition, not
   assumed. A new condition `OKFContentSynced` reports tracked ref,
   last-applied SHA, and drift/violation state per agent; signature
   verification (ADR-0106, per ADR-0509 clause 3) gates every render,
   unchanged.

5. **Every applied change is auditable:** the operator records (event +
   condition transition) the SHA pair, the affected agent, the change
   class and the rollout action taken — the GitOps property (ADR-0022)
   preserved at a faster cadence: git remains the only input, review
   happens in `zuno-okf`, and the cluster follows it observably.

## Consequences

The OKF stream closes: who/what/for-what/under-which-policy lives in one
governed repository, and a merged change there reaches running agents
without a platform release — bounded by CR ceilings, signatures and
conditions. The operator takes on periodic external I/O (git polling)
for the first time; interval, backoff and failure isolation keep it from
affecting the core reconcile loop. The ADR-0507 pin still governs what
gets *built into images* (the baked fallback and non-mounted agents);
tracking governs what gets *mounted* — two knobs, each reviewable, and
the platform can hold them equal when cadence should be unified.

## Security considerations

The ceiling check is the heart of it: live content updates must never
become a privilege-escalation path, so widening is structurally
impossible without a CR change (clause 2) and everything rendered is
signature-verified (ADR-0106). The git credential is read-only and
scoped to `zuno-okf`. Poll results are trusted only after signature
verification — a compromised branch cannot reach pods unsigned; a
compromised *signing* path is the existing ADR-0106 threat model,
unchanged by this ADR. Rollout actions are confined to Deployments the
operator already owns; no new RBAC beyond the git read.

## Operational considerations

`OKFContentSynced` plus events make the loop observable per agent;
"repo unreachable" degrades to "last verified content keeps serving"
with the condition reporting staleness — availability is never hostage
to git uptime. The poll interval is an `OperatorConfig` value with a
conservative default; envtest covers the resolver/ceiling/rollout logic
with a fake git source, and one end-to-end demo (edit a Naveo prompt in
`zuno-okf` → merged → running agent answers with the new prompt) is the
stream's closing proof (WP-53).

## Acceptance criteria

- A merged `zuno-okf` prompt change reaches a running Naveo without any
  image rebuild, with the event trail showing SHA pair, change class
  and action.
- A bundle change exceeding a CR ceiling renders nothing, sets
  `OKFContentSynced: False` with a named violation, and the running
  agent is unaffected.
- A startup-class change triggers exactly the affected Deployments'
  rolling restart; a hot-class change restarts nothing.
- Explicitly pinned CRs never move with the tracking ref; Tekos is
  untouched throughout.

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0022](0022-use-gitops-managed-declarative-agent-tasks-and-policies.md)
- [ADR-0106](0106-enforce-okf-bundle-signing-and-validation.md)
- [ADR-0308](0308-expand-agent-lifecycle-management-through-the-aiagent-operator.md)
- [ADR-0327](0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md)
- [ADR-0350](0350-provide-an-aiagent-kubernetes-crd-and-operator.md)
- [ADR-0507](0507-consume-the-zuno-okf-repository-through-a-single-pinned-reference.md)
- [ADR-0509](0509-deliver-okf-content-as-mounted-versioned-artifacts.md)
