# llm

Two responsibilities, both AI/model-layer concerns judged to belong
together rather than splitting into yet another role:

1. Seeds empty placeholders (never overwriting a real value) for the four
   external provider API keys at `secret/zuno/providers/{openai,gemini,anthropic,mistral}`,
   then applies `gitops/apps/llm` — a native ArgoCD Kustomize app pointing
   at `platform/ai-gateway/` (provider routing `ConfigMap` + the four
   `ExternalSecret`s resolving those keys). See ADR-0020, ADR-0021.
2. Applies `gitops/apps/agent-runtime` (`gitops/charts/agent-runtime`): the
   shared LangGraph orchestration service (`components/agent-runtime`,
   ADR-0009, ADR-0018) that consumes the provider routing config. It's
   applied here rather than from a dedicated role because it has no
   meaningful existence without the routing config next to it.

CONFIG_SCOPE only — no separate prepare phase.
