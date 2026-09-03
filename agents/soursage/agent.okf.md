---
okf_version: v0.2
type: agent
title: Soursage
description: >-
  Recruiting assistant. Interacts with Workday and LinkedIn to source new
  consultant candidates and to find, among existing consultants, the best
  profile for a mission.
provenance:
  maintainer: Zuno Demo architecture team
  repository: zuno-demo
verification:
  status: unverified
freshness:
  last_reviewed: "2026-08-15"
sources: []
zuno:
  name: soursage
  status: placeholder
  tasks:
    - coming-soon
  model:
    preferred_classification: C2
    notes: >-
      Placeholder pending a future build (ADR-0349 defines only the
      identity footprint); C2 anticipated because candidate/consultant
      profile data requires context filtering rather than unrestricted
      SaaS use.
  access:
    # ADR-0040: agent entitlement group, orthogonal to the `recrut` and
    # `sales` business roles that will govern tool/data permissions
    # inside Soursage (ADR-0349 §6 - future tools gate on those roles
    # and on the ADR-0340 Workday capability scopes,
    # workday.profile.any.read, read-only).
    groups:
      - agent_soursage
  ui:
    displayName: Soursage
    tileDescription: Consultant sourcing and staffing assistant - coming soon.
    color: "#00695C"
    icon: users
---

# Soursage

ADR-0349 §6: `status` is `placeholder` - this bundle, the
`soursage-frontend` Keycloak client, the `agent_soursage` entitlement
group and this portal tile are the only things that exist for Soursage
today (the original placeholder pattern comage/advantage/finage/arkos
each started from). No dedicated namespace is reserved (ADR-0329): a
future active Soursage deployment would run in the shared `zuno-ai-run`
namespace, CR-managed via the AIAgent operator (ADR-0327/ADR-0308) like
every agent onboarded since WP-38.

`tasks/coming-soon.md` describes the intended build - sourcing new
consultant candidates and matching existing consultants to missions via
Workday (`workday.profile.any.read`, the read-only ADR-0340 scoped
capability WP-32 already registered) and a future LinkedIn capability -
kept here so onboarding Soursage later is primarily a `status: active`
flip plus real task implementation through the ADR-0307 template
workflow (`platform/templates/agent/`), not a redesign.

<!-- BEGIN GENERATED AUTHORIZATION MATRIX (ADR-0503) - do not edit; regenerate with: python3 platform/okf/generate_authorization_matrix.py -->

## Authorization matrix

Generated per ADR-0503 from this bundle's frontmatter, `policies/tools/tool-policy.yaml`, `policies/knowledge/knowledge-policy.yaml`, `platform/ai-gateway/provider-routing.yaml` and `policies/model-routing/model-routing-policy.yaml` — the enforced intersection (ADR-0011/ADR-0203) restated for review, never read at runtime. Entitlement (ADR-0040): `agent_soursage`; model classification ceiling (ADR-0021): `C2`; status: `placeholder`.

No capabilities declared: every task's `allowed_tools`/`allowed_knowledge` is empty, so this agent can invoke no tool and retrieve from no knowledge domain regardless of caller groups (the honest Stage-1 zero-capability state, ADR-0502).

### Model routing

Effective per-task model chain (ADR-0021/ADR-0303/ADR-0412), resolved from `platform/ai-gateway/provider-routing.yaml`'s classification eligibility reordered by this `(agent, task)`'s `policies/model-routing/model-routing-policy.yaml` preference — the first entry is the reference model, the rest are fallback alternatives, in try order. The reference model is annotated with the model id it actually serves and that model's architectural role (`default`, `quality`, `reasoning`, `specialized`, `reasoning-external`, `code`, `general-external`); `provider-routing.yaml`'s `role` key is the authority for both, and every model reachable through the fallback chain is named in the **Available models** rollup below the table.

| Task | Classification ceiling | Reference model | Fallback chain | Adapter | Policy source |
|---|---|---|---|---|---|
| `coming-soon` | `C2` | `local-qwen35-maas` → `qwen3.5-9b` (default) | `local-qwen35`, `local-gpt-oss-maas`, `local-gpt-oss`, `local-maas`, `local`, `local-wesh-maas`, `local-wesh`, `openai`, `anthropic`, `mistral-codestral`, `ovhcloud-gpt-oss-120b` | — | `policies/model-routing/model-routing-policy.yaml` |

**Available models** (ADR-0419, generated): the union of every model reachable by any task or prompt slot above, at any classification, each with the model id it serves and that model's role - `local-maas` → `qwen3.6-27b-instruct` (quality), `local` → `qwen3.6-27b-instruct` (quality), `local-gpt-oss-maas` → `gpt-oss-20b` (reasoning), `local-gpt-oss` → `gpt-oss-20b` (reasoning), `local-wesh-maas` → `qwen3.5-9b-wesh` (specialized), `local-wesh` → `qwen3.5-9b-wesh` (specialized), `local-qwen35-maas` → `qwen3.5-9b` (default), `local-qwen35` → `qwen3.5-9b` (default), `openai` → `gpt-4o-mini` (general-external), `anthropic` → `claude-3-5-sonnet-latest` (general-external), `mistral-codestral` → `codestral-latest` (code), `ovhcloud-gpt-oss-120b` → `gpt-oss-120b` (reasoning-external).

<!-- END GENERATED AUTHORIZATION MATRIX -->
