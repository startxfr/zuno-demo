# Comage Agent

- **Purpose:** Sales assistant
- **Primary integrations:** Sales data, Gmail
- **Initial tasks:** Follow-up prioritization; current deals without client PO; weekly sales synthesis

## Planned declarative structure

```text
comage/
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
