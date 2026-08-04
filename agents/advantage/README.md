# Advantage Agent

- **Purpose:** Sales administration assistant
- **Primary integrations:** Sales data
- **Initial tasks:** New client-PO-received business; monthly in-progress sales reporting

## Planned declarative structure

```text
advantage/
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
