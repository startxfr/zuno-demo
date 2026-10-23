# ADR-0008: Use one frontend and one BFF deployment per agent

- **Status:** Superseded by [ADR-0561](0561-adopt-unifai-as-the-agent-platform.md) (2026-10-23, WP-156) - UnifAI serves every agent through its own UI, so there is no per-agent frontend or BFF any more; both were uninstalled on demo333 and their code removed. Previously: Implemented
- **Target:** v0
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

## Decision

Provide isolation and per-agent configuration while reusing common frontend and BFF codebases.

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution and Related ADRs.
