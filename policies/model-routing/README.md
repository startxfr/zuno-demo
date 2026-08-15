# Policy: model-routing

Model/provider preference, fallback, cost, latency and sovereign-routing
policy.

`model-routing-policy.yaml` (ADR-0303, WP-39) is the one concrete file
here today: per-agent/task adapter declarations for the AI Gateway's
per-request dynamic LoRA adapter selection
(`components/ai-gateway/app/model_routing_policy.py`). Mechanism only -
which requests get an approved adapter, never which adapter is best
(ADR-0304/WP-40 extends this same file with objectives blocks rather than
adding a second file). References `gitops/charts/models/values.yaml`'s
own `loraAdapters` entries; never invents an adapter name.

The file ships inside the ai-gateway image (`components/ai-gateway/Dockerfile`)
alongside `platform/ai-gateway/provider-routing.yaml` - a deliberately
separate concern (provider/SaaS eligibility by classification, consumed
by `app/routing.py`), not merged into this file.
