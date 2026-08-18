# ADR-0508: Isolate OKF parsing behind per-component adaptation hooks

- **Status:** Proposed
- **Target:** OKF v0.2
- **Date:** 2026-08-18
- **Decision owners:** Zuno Demo architecture team

## Context

Three services parse the OKF bundle format independently, by documented
design: `components/agent-frontend/internal/okf/okf.go` (Go),
`components/mcp-gateway/app/agent_declarations.py` and
`components/agent-runtime/app/registry.py` (Python) — "three independent
parsers of the same bundle format, per this repo's convention of
duplicating small well-specified parsing code across independently
deployed services rather than sharing a module"
(`platform/architecture/agent-platform-separation.md`). Two more
components carry OKF knowledge less visibly: `agent-bff` re-derives the
entitlement group by string concatenation (`"agent_" + agentName`,
`main.go`) instead of reading any declaration, and `ai-gateway`
(`maas_adapter.py`, plus the ADR-0511 token-budget check) consumes
policy semantics. The convention has served: each service bakes its own
copy and deploys independently. What it lacks is any shared statement of
*correct parsing behavior* — when the format evolves (a new frontmatter
key like `zuno.project_required`, a schema field rename), each consumer
drifts or breaks on its own schedule, discovered by whichever test suite
happens to import first (the WP-41 prompt-frontmatter bug pattern). With
the format moving to its own repository and cadence (ADR-0506/0507),
"each consumer figures it out" stops scaling.

## Decision

1. **Each consuming component confines all OKF knowledge to one
   designated adaptation module — its hook.** The hook is the only code
   in the component allowed to read OKF files or derive OKF-shaped
   values; the rest of the component consumes the hook's typed output.
   Designated hooks: `agent-frontend` — `internal/okf/` (already true);
   `agent-runtime` — `app/registry.py` (already true); `mcp-gateway` —
   `app/agent_declarations.py` (already true); `agent-bff` — a new
   small hook module that owns the `agent_<name>` derivation, replacing
   the inline concatenation; `ai-gateway` — a hook wrapping its policy/
   budget reads. For the three existing parsers this is a formalization,
   not a rewrite.

2. **The `zuno-okf` repository ships a schema version marker and a
   language-neutral conformance suite.** A root `okf-package.yaml`
   declares the package's schema version; a `conformance/` tree holds
   fixture bundles — valid and invalid — each paired with its expected
   parse result (JSON). Every hook gains a test that runs its parser
   over the fixtures at the pinned ref and compares against the expected
   results; that test is blocking in the component's CI. A format change
   is therefore made *in* `zuno-okf` (fixtures updated in the same PR),
   and the next pin bump tells each component exactly which hook broke
   and how — N small, pinpointed fixes instead of N discoveries.

3. **Each hook checks the version marker at startup** against the range
   it supports, failing fast with a named error on mismatch — the same
   fail-fast posture bundle validation already takes at startup. The
   supported range lives in the hook, one line per component.

4. **This ADR refines the three-independent-parsers convention; it does
   not overturn it.** No shared parsing library is introduced, in either
   language; parsers stay per-component and per-language, each baking
   its own copy, exactly as `agent-platform-separation.md` documents.
   What is added is a shared behavioral contract (fixtures + expected
   results) and a version handshake — the duplication stays cheap
   because divergence is now caught mechanically at the pin, not
   organically in production or an unrelated suite.

## Consequences

"Rules defined in the OKF package with code in frontend, bff, gateway,
runtime and MaaS that adjusts easily when the package changes" becomes
mechanical: the package changes, fixtures change with it, the pin bump
runs every hook against the new truth, and the failing hooks enumerate
the adjustment work. The BFF's hidden string-concat contract becomes
explicit and testable. WP-51 executes the hook boundaries and the
fixture suite; ADR-0509 later reuses the hooks as the single seam
through which mounted content replaces baked content.

## Security considerations

Hooks concentrate the code that turns untrusted-until-validated files
into authorization-relevant values — a smaller, named audit surface per
component. Conformance fixtures must include negative cases that
matter for security: unknown `access.groups` values, missing
`allowed_tools`, a task naming an undeclared knowledge domain — with
expected results that reject, so a hook that fails open diverges from
the fixtures and fails CI. The version handshake prevents a component
silently interpreting a newer schema with older assumptions.

## Operational considerations

Per component: one module boundary, one fixture-driven test, one
startup check. The conformance suite is part of the `zuno-okf` package
and versions with it; component CI fetches it via the ADR-0507 pin, so
hook tests are reproducible. Hook boundary violations (OKF reads
outside the hook) are kept out by review plus a light lint (grep-level
path check) in each component's CI.

## Acceptance criteria

- All five hooks exist at the named module boundaries; `agent-bff` no
  longer derives `agent_<name>` outside its hook.
- `zuno-okf` ships `okf-package.yaml` and a `conformance/` suite with
  valid and security-negative fixtures; every hook's fixture test is
  blocking in its component CI at the pinned ref.
- A deliberately mismatched version marker fails each component fast at
  startup with a named error.
- A fixture change in `zuno-okf` surfaces as precise hook-test failures
  on the next pin bump, component by component.

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0038](0038-use-standards-compliant-okf-v0-2-markdown-bundles.md)
- [ADR-0039](0039-make-agent-runtime-execute-the-okf-agent-contract.md)
- [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md)
- [ADR-0506](0506-extract-okf-content-into-a-standalone-zuno-okf-repository.md)
- [ADR-0507](0507-consume-the-zuno-okf-repository-through-a-single-pinned-reference.md)
- [ADR-0509](0509-deliver-okf-content-as-mounted-versioned-artifacts.md)
- [ADR-0511](0511-define-okf-quota-policy-enforced-via-kuadrant.md)
