# Finage Agent

- **Purpose:** Finance assistant
- **Primary integrations:** Sales and invoice data
- **Initial tasks:** Billable business; monthly invoice reporting

## Declarative structure (ADR-0038: OKF v0.2 Markdown bundles)

```text
finage/
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
