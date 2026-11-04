# WP-197: Declare UnifAI built-in resources through the operator

- **State:** Repo work in review
- **ADRs:** [ADR-0597](../../adr/0597-declare-unifai-built-in-resources-through-the-operator.md)
- **Depends on:** none
- **Related:** [WP-198](wp-198-default-unifai-team-workspaces-shared-inventory-and-catalog.md) (its first user)
- **Target:** v0.13
- **Estimated files touched:** ~14 in the fork (types, controller, validate rules, tests, six CRDs, README); the catalog pin here

> Why: the platform's gateway LLM and MCP provider live in ai-ops-01's personal workspace, so no other persona sees them.
> UnifAI has public built-ins for exactly this; the operator could not declare them. User decision of 2026-11-04: use
> the native built-ins through the operator (fork change, release lifecycle alpha + digest pin).

## Goal

`spec.builtin: true` on an UnifAI resource object makes it a public built-in, promoted in place, never turned off.

## Steps

1. **Fork, operator (own worktree, branch `wp194-builtin-resources`).**
   - `api/v1alpha1/resource_types.go`: the `builtin` field on six kinds, plus `IsBuiltin()` on all seven.
   - CEL rules: exclusive with `teamId`/`teamRef`, and never turned off.
   - `resource_controller.go`: `builtin.toggle` after save or update, when the hash changes. A 403 is a permanent error
     naming the owner.
   - `internal/validate`: the static rule, plus fixtures (replayed at admission).
   - Envtests `builtin_test.go`, fake MAS endpoint, README section, `make manifests generate`.
2. **Release.**
   - Push the branch to fork devel (this session has no push access to the fork: the user or a fork session pushes).
   - Then either the Friday alpha, or a manual release: ci-image, canary-e2e-full including TestUpgrade (CRD change), then
     cut-release by the user.
3. **Pin here.** `pin_operator_catalog.py` to the release carrying the field.

## Acceptance

- `go test ./internal/... ./api/...` and golangci-lint pass in the fork. Canary green.
- Live on demo333: `oc get unifaillm zuno-gateway -o yaml` shows `builtin: true` and Ready with the same rid. As
  consultant-01, the inventory's "Built-in" tab lists the LLM and the MCP provider.
