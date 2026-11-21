# WP-320: Inventory the capabilities and propose the Core / Enterprise / Labs overlays

- **State:** Not started (proposed by ADR-0625 on 2026-11-21; the ADR is `Proposed`, so this work package is not approved)
- **ADRs:** [ADR-0625](../../adr/0625-evolve-zuno-toward-a-modular-sovereign-enterprise-ai-platform.md)
- **Depends on:** none
- **Related:** [ADR-0606](../../adr/0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md), [ADR-0352](../../adr/0352-run-day-0-platform-services-in-internal-or-external-mode.md), [ADR-0547](../../adr/0547-parameterize-every-cluster-specific-value-in-ansible.md), [ADR-0616](../../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md)
- **Target:** v0.19
- **Estimated files touched:** ~10: an inventory page, a dependency graph, one overlay, this brief

## Goal

A capability inventory with a dependency graph, a proposed split into Core, Enterprise and Labs, and one minimal Core deployment that runs.

Horizon in the ADR's indicative roadmap: Day 0-30. The horizons count from the start of an approved initiative. They are not calendar dates.

## Proposed work

1. Describe each capability: prerequisites, supported versions, operator dependencies, resources, exposed interfaces, owner.
2. Draw the dependency graph between capabilities.
3. Propose the deployment overlays and the support boundaries.
4. Deploy and exercise a minimal Core.

## Existing work it builds on

- The per-cluster inventory layout planned for after the 2026-11-24 demo (finding F8): an overlay is a per-cluster inventory.
- The day-0 modes of [ADR-0352](../../adr/0352-run-day-0-platform-services-in-internal-or-external-mode.md), the per-cluster values of [ADR-0547](../../adr/0547-parameterize-every-cluster-specific-value-in-ansible.md), the admission rule of [ADR-0606](../../adr/0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md) and the demo catalogue of [ADR-0616](../../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md).

## Acceptance

- The Core layer is deployed and exercised without installing the Enterprise or Labs capabilities.
- Every capability has an owner and a declared layer.
