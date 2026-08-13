# ADR-0011: Define tool authorization as policy intersection

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

## Decision

Allow a tool only when agent declaration, task rights, user/group rights, classification and platform policy all permit it.

## Evolution (2026-08-13)

ADR-0203 applies the same least-privilege pattern to RAG/knowledge access. Tool authorization remains a five-factor intersection; knowledge authorization is a separate, analogous intersection and must not be collapsed into tool permissions or frontend visibility.

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution and Related ADRs.
