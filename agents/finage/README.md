# Finage Agent

- **Purpose:** Finance assistant
- **Primary integrations:** Sales and invoice data
- **Initial tasks:** Billable business; monthly invoice reporting

## Planned declarative structure

```text
finage/
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
