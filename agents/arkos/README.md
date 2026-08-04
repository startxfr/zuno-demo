# Arkos Agent

- **Purpose:** Architecture assistant
- **Primary integrations:** Technical RAG, Confluence, Google Drive/Docs, Lucidchart
- **Initial tasks:** Create DAT; prepare Odyssey workshops

## Planned declarative structure

```text
arkos/
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
