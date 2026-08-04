# ADR-0003: Use Make as the operator interface and Ansible as the automation engine

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

The project needs simple human commands for checking, preparing, configuring, installing, and validating the demo.

## Decision

Expose stable Make targets and delegate infrastructure/application automation to Ansible playbooks.

## Alternatives considered

Direct shell scripts; Terraform-only operations; manual runbooks.

## Consequences

Operators get a concise interface while Ansible remains testable and composable.

## Security considerations

Secrets are supplied externally to Ansible, never embedded in Make or repository files.

## Operational considerations

Make target names become a compatibility contract.

## Migration / evolution

Implementation roles can evolve without changing the public command surface.
