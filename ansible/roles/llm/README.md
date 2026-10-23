# llm

Two responsibilities, both AI/model-layer concerns judged to belong
together rather than splitting into yet another role:

1. Seeds empty placeholders (never overwriting a real value) for the four
   external provider API keys at `zuno/providers/{openai,gemini,anthropic,mistral}`,
   then applies `gitops/apps/llm` - a native ArgoCD Kustomize app pointing
   at `platform/ai-gateway/` (provider routing `ConfigMap` + the four
   `ExternalSecret`s resolving those keys). See ADR-0020, ADR-0021.
2. Applies `gitops/apps/ai-gateway` (`gitops/charts/ai-gateway`): the
   shared AI Inference Gateway (`components/ai-gateway`, ADR-0009) that
   consumes the provider routing config and holds every provider secret -
   applied here rather than from a dedicated role because it has no
   meaningful existence without the routing config next to it, and this is
   also where the config's other consumer used to live before the
   ADR-0009 split.

The agent-runtime Application this role also applied (the shared
LangGraph orchestration service, ADR-0009/ADR-0018) was retired with the
zuno agent stack (WP-156); UnifAI calls `ai-gateway` instead (ADR-0560).
`make d2 install llm` brings both Applications up together.

A Day 2 component (ADR-0060) - no operator dependency of its own.
