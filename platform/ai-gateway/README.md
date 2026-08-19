# AI Gateway provider configuration (ADR-0009, ADR-0020, ADR-0021)

`platform/ai-gateway/` is the physical model catalog: which models exist,
where they're served, and which data classifications may route to them.
It defines **what** models are available and **where**, never which agent
or task prefers which one.

## Layout

- `provider-routing.yaml` — one entry per provider (`local`, `local-gpt-oss`,
  `openai`, `gemini`, `anthropic`, `mistral` today): served model id,
  endpoint, and `eligible_for` (which of C1/C2/C3 may route there per
  ADR-0021). Deployed as the `zuno-provider-routing` ConfigMap
  (`ansible/roles/llm`, `kustomization.yaml` in this directory) — this
  file is the single source of truth, never hand-copied elsewhere.
  Consumed by `components/ai-gateway/app/routing.py`'s `RoutingTable`.
- `externalsecret-*.yaml` — Vault-backed `ExternalSecret`s populating each
  SaaS provider's `api_key_env` referenced from `provider-routing.yaml`.

## Relationship to `policies/model-routing/`

`provider-routing.yaml` only decides *eligibility* (which providers a
classification permits) and their default fallback order (top-to-bottom
list order). It has no notion of any particular agent or task.

`policies/model-routing/model-routing-policy.yaml` (see its own README)
is the layer above it: per-`(agent, task)` **preference** (`preferences:`,
ADR-0412) — an ordered reorder of the already-eligible candidates, never
able to add one eligibility filtered out — and per-`(agent, task)`
**adapter** (`adapters:`, ADR-0303). It ships baked into the gateway
image, a deliberately separate lifecycle from this ConfigMap.

An agent's OKF bundle (`agents/<agent>/agent.okf.md`) never names a
specific model — its `zuno.model.preferred_classification` only sets the
eligibility ceiling (schema: `platform/okf/schema/zuno-okf-v0.2.schema.json`,
`model` property — *"the data-classification ceiling... not a specific
model name"*). This mirrors `knowledge/README.md`'s domain-descriptor
pattern deliberately: ADR-0038's Evolution note and ADR-0202 both reject a
parallel per-agent capability/model catalog in favor of one central file
agents reference by name/classification, not by duplicating entries.

The effective per-task model chain (reference model + fallback,
resolved from both files together) is rendered — generated, never
hand-authored — into each agent's `agent.okf.md` "Model routing" section
by `platform/okf/generate_authorization_matrix.py` (ADR-0503).
