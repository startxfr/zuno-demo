# WP-227: Hardened deployment profile (delivers ADR-0602)

- **State:** Not started
- **ADRs:** ADR-0602
- **Depends on:** WP-223, WP-224, WP-225, WP-226
- **Blocks:** none
- **Estimated files touched:** ~12

> Execute this brief as a standalone task from the repository root.

## Goal

Give a customer one switch that turns on every hardening clause of ADR-0602, while the demo profile keeps its fast, permissive
behaviour under a name that says so.

## ADR references

ADR-0602 clauses 12 and 13.

## Preconditions

- WP-223 to WP-226 merged, each with its flag or value named. Read how the existing profile
  (`platform/docs/check_docs.py::_load_profile`) is selected before adding a second one.

## Repo changes

1. A `hardened` profile in the inventory group vars and chart values that sets: auto-unseal, per-tenant stores, per-component
   passwords, STRICT mesh, restricted AppProject, `JWT_AUDIENCE_REQUIRED`, `ADMIN_AUTH_MODE=enforce`, guardrails `block`,
   `ClusterImagePolicy` enforce.
2. A check (`make check`) that fails when a `hardened` install has any of those off.
3. `docs/security/threat-model.md` and `ai-security.md` rewritten from stubs: each of C1 to C10 with its attacker, asset and
   closing clause.

## Verification

Install the profile on a scratch cluster with the user's go; run the check; replay each finding of ADR-0602 and record the
result in `docs/roadmap/evidence/`.
