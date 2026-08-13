# ADR-0014: Use delegated Google OAuth for Google Workspace access

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

## Decision

Use per-user OAuth delegation so Gmail and Drive actions preserve the user effective Google permissions.

## Evolution (2026-08-13)

ADR-0208 extends this delegated-user model from Gmail and Drive to Google Calendar and Google Meet. Zuno authorization decides whether an agent/task may invoke a logical capability; Google OAuth and native Google Workspace permissions independently decide what the authenticated user may read or modify.

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution and Related ADRs.
