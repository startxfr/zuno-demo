# Tekos Agent

- **Purpose:** Technical consultant assistant
- **Primary integrations:** Official technical RAG, Confluence, web search
- **Initial tasks:** Technical Q&A with concise citations; first MVP vertical slice

## Planned declarative structure

```text
tekos/
├── README.md
├── agent.okf.yaml
├── tasks/
├── prompts/
├── policies/
├── rag/
├── tools/
├── deployment/
└── tests/
```

The runtime implementation is shared. This directory contains only agent-specific declarative behavior, policy, knowledge references and deployment configuration.
