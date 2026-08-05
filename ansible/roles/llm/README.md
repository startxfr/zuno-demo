# llm

Three responsibilities, all AI/model-layer concerns judged to belong
together rather than splitting into yet another role:

1. Seeds empty placeholders (never overwriting a real value) for the four
   external provider API keys at `secret/zuno/providers/{openai,gemini,anthropic,mistral}`,
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
3. Applies `gitops/apps/agent-runtime` (`gitops/charts/agent-runtime`): the
   shared LangGraph orchestration service (`components/agent-runtime`,
   ADR-0009, ADR-0018). It no longer touches the provider routing config or
   any provider secret directly - it only needs `ai-gateway`'s in-cluster
   URL, set as a plain (non-secret) value in its own chart.

Order matters here: `ai-gateway` before `agent-runtime`, since the latter
calls the former. Applied in that order, always in the same `configure`
run (`ansible/playbooks/day1_configure.yml`'s `llm` step, ADR-0056), so
`make day1|d1 run` with no component brings both up together;
`make day1|d1 run llm` alone does the same.

A Day 1 component (ADR-0056) with a documented no-op `prepare.yml` - no
operator dependency of its own.
