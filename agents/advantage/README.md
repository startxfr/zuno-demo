# Advantage Agent

- **Purpose:** Sales administration assistant
- **Primary integrations:** Sales data
- **Initial tasks:** New client-PO-received business; monthly in-progress sales reporting

## Declarative structure (ADR-0038: OKF v0.2 Markdown bundles)

```text
advantage/
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
