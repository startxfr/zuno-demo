# Acceptance Criteria

The MVP is successful when authenticated users can open the portal, select each agent, receive responses whose model/context/tools differ according to the agent definition, and execute real MCP/database-backed tasks under policy control.

`make day2|d2 check agents` is the automated form of this gate (the ADR-0053 acceptance/security gate); see `docs/platform/installation.md` and `docs/platform/troubleshooting.md`.
