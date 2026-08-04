# ADR-0203: Add task-specific UI and richer human approval workflows

- **Status:** Proposed
- **Target:** v2
- **Date:** 2026-08-04

## Context

The MVP uses a chat-first UI, but complex tasks such as DAT and sensitive writes benefit from structured interaction.

## Decision

Add task-specific forms/status/progress/approval surfaces while keeping chat as the common entry point.

## Alternatives considered

Chat-only UX permanently.

## Consequences

Makes long and sensitive workflows clearer and safer.

## Security considerations

Approval identity and action details must be auditable.

## Operational considerations

Frontend contract expands beyond streaming chat.

## Migration / evolution

Can be introduced task by task.
