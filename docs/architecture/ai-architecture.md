# AI Architecture

The AI architecture uses Red Hat OpenShift AI 3.5 EA2 as the primary AI platform. The design intentionally separates agent orchestration from inference governance.

- **Agent Runtime**: state, LangChain/LangGraph workflows, RAG, MCP and task orchestration.
- **AI/Inference Gateway**: model selection, local/SaaS routing, classification enforcement, quotas, costs, fallback and streaming.
- **OpenShift AI model serving**: local Granite, Qwen and Llama variants sized for NVIDIA L4 24 GB GPUs.
- **KServe / Models-as-a-Service / llm-d**: used where they map to the selected OpenShift AI 3.5 deployment path and maturity constraints.
- **OGX**: considered for OpenShift AI-native GenAI/RAG capabilities while retaining explicit application-runtime boundaries.
- **Model Registry / Pipelines / LM-Eval / guardrails**: included as architecture capabilities and activated according to MVP feasibility and component maturity.

SaaS provider default preference/fallback order is OpenAI, Gemini, Anthropic and Mistral, subject to C1/C2/C3 data policy.
