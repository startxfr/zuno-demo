# ADR-0029: Support command-dispatch Make syntax

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

The requested operator UX uses commands such as `make precheck keycloak`, even though Make normally treats the second word as another goal.

## Decision

Use a Make dispatcher pattern that interprets the second goal as the component/scope while absorbing it as a no-op target.

## Alternatives considered

Require `COMPONENT=keycloak`; create a separate target for every combination.

## Consequences

Keeps a compact discoverable interface.

## Security considerations

No security impact beyond ensuring arguments are validated by Ansible.

## Operational considerations

Ansible validates supported component/scope values.

## Migration / evolution

The command contract should remain stable.
