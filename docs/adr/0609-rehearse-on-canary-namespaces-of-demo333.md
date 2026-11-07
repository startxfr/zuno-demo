# ADR-0609: Rehearse on canary namespaces of demo333

- **Status:** Accepted
- **Target:** v0.16
- **Date:** 2026-11-07
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0352](0352-run-day-0-platform-services-in-internal-or-external-mode.md), [ADR-0573](0573-pilot-unifai-on-demo333-with-tekos-before-cutting-demo222-over.md), [ADR-0602](0602-harden-the-platform-trust-boundaries-before-a-customer-runs-it.md), [ADR-0605](0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md), [ADR-0607](0607-pin-gate-and-schedule-pre-ga-dependencies.md)

## Context

demo222 was retired on 2026-10-23 (ADR-0573), so demo333 is the only cluster. Several open work packages assume a place
to rehearse that does not exist:

- WP-227 (the `hardened` profile of ADR-0602) is to be rehearsed on a "scratch cluster";
- WP-211 to WP-215 and WP-218 (ADR-0352's external mode) each need "a cluster rehearsal there and back";
- ADR-0607 wants a canary before a pre-GA release reaches the stack.

Partial patterns already exist on demo333: the `okf-dev` namespace used by the agents repository's run-dev workflow,
the `zuno-owui-scratch` and `zuno-claw-scratch` namespaces of WP-179, and the UnifAI canaries run with each release.

On 2026-11-07 the owner chose canary namespaces on demo333 over an on-demand cluster or a second permanent one.

## Decision

**Rehearsals run in labelled canary namespaces on demo333. What a namespace cannot hold is named as not rehearsed and
falls under ADR-0607's backup and rollback rules.**

1. **One pattern for canary namespaces.** `zuno-canary-<wp>` with the labels `zuno.io/canary: "true"` and
   `zuno.io/work-package: <WP>`, a ResourceQuota, a default-deny NetworkPolicy with explicit egress, no GPU unless the
   work package asks for one, and a teardown at the end of the work package. A shared task creates and removes it.
2. **What can be rehearsed in a canary:**
   - experience clients and other namespace-scoped components, as a second instance;
   - the namespace-scoped part of a UnifAI release (stack images), where the operator allows it;
   - firewall and egress rules of one namespace;
   - ADR-0352's external mode, against an external service simulated in the canary namespace (a second Keycloak,
     PostgreSQL or Redis instance), there and back.
3. **What cannot be rehearsed in a canary,** and is written as "not rehearsed" in the work package that changes it:
   cluster-scoped operators and CRDs, Vault (one instance), mesh-wide settings, ArgoCD and its AppProjects, GPU node pools.
   For these, ADR-0607 clauses 4 to 6 apply: backup, recorded rollback, a window outside any freeze, a golden-path run
   after.
4. **WP-227 rehearses per namespace.** Its namespace-scoped switches are rehearsed in a canary; its cluster-scoped ones
   are verified by its `make check` only. demo333 stays on the `demo` profile.
5. **Canaries stay out of the demonstration.** A canary namespace is never part of the golden path, its traffic is
   counted as `other` by the ai-gateway (it is not in `experienceClients`), and no canary is changed during a freeze.
6. **Revisit with a customer install.** If a customer needs the `hardened` profile proven end to end on a whole
   cluster, an on-demand cluster becomes a new ADR.

## Alternatives considered

- **An on-demand cluster, built by the same Ansible for each rehearsal.** It covers everything, including operators and
  Vault, for one to two hours of build and a cost per use. Not chosen by the owner for now; clause 6 keeps it open.
- **A second permanent cluster.** Immediate rehearsals, permanent cost and a second cluster to keep in step. Rejected.

## Consequences

- WP-227 and WP-211 to WP-218 can proceed without a second cluster, with their limits written down.
- Cluster-scoped changes stay the riskiest step; they are scheduled, backed up and followed by a golden-path run.
- The quota and NetworkPolicy of a canary keep a rehearsal from starving or reaching the live stack.

## Security considerations

A canary namespace holds rehearsal credentials only, read from Vault paths of its own; it never receives a live
persona's secrets.

## Operational considerations

Canary namespaces are listed by `oc get ns -l zuno.io/canary=true`; one left over after its work package is a finding
of the drift check (ADR-0608).

## Work packages

[WP-242](../roadmap/work-packages/wp-242-canary-namespace-pattern.md).
