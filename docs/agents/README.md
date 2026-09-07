# Agent Catalog

The initial catalog contains Comage, Tekos, Arkos, Advantage and Finage. Naveo joined as the sixth agent via the ADR-0307 self-service template (WP-41); Soursage (recruiting) and Cognos (board financial/strategic) joined as ADR-0349 placeholder definitions - identity footprint and portal tile only, no runtime yet. Agent behavior is declared through OKF-based definitions and common runtime contracts.

Each agent has a dedicated documentation page in this directory and a matching implementation/configuration directory under `/agents`.

See [Agent Request Workflow](request-workflow.md) for the end-to-end diagrams (Tekos, Arkos, Comage) showing how a user request flows through the frontend, BFF, AI Gateway, OKF, RAG, MCP, model routing and tracing.

See [OKF Workflow](okf-workflow.md) for the upstream leg: how an OKF rule change is authored, signed and (today, still baked into images; live reconciliation is a Proposed target) rolled out before it reaches that runtime path.
