# Tekos Agent

- **Purpose:** Technical consultant assistant
- **Primary integrations:** Official technical RAG, Confluence, web search
- **Initial tasks:** Technical Q&A with concise citations; first MVP vertical slice

## Declarative structure (ADR-0038: OKF v0.2 Markdown bundles)

```text
tekos/
├── README.md
├── agent.okf.md         Agent index bundle (YAML frontmatter + Markdown body)
├── tasks/
│   ├── answer-technical-question.md   (the one task with a live route in v0)
│   ├── find-relevant-docs.md
│   └── check-my-drive-docs.md
├── prompts/
│   └── answer-technical-question.md   System prompt, loaded by app/registry.py
├── policies/
├── rag/
├── tools/
├── deployment/
└── tests/
```

The earlier `agent.okf.yaml` (a single Kubernetes-style YAML file) was
replaced by `agent.okf.md` plus linked per-task/per-prompt Markdown
documents under `tasks/`/`prompts/` per ADR-0038.

The runtime implementation is shared. This directory contains only agent-specific declarative behavior, policy, knowledge references and deployment configuration.
