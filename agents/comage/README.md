# Comage Agent

- **Purpose:** Sales assistant
- **Primary integrations:** Sales data, Gmail
- **Initial tasks:** Follow-up prioritization; current deals without client PO; weekly sales synthesis

## Declarative structure (ADR-0038: OKF v0.2 Markdown bundles)

```text
comage/
├── README.md
├── agent.okf.md         Agent index bundle (YAML frontmatter + Markdown body)
├── tasks/
│   └── coming-soon.md
├── prompts/
├── policies/
├── rag/
├── tools/
├── deployment/
└── tests/
```

The runtime implementation is shared. This directory contains only agent-specific declarative behavior, policy, knowledge references and deployment configuration.
