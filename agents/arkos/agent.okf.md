---
okf_version: v0.2
type: agent
title: Arkos
description: >-
  Architecture assistant for architects. Helps produce Design & Architecture
  Testimonials (DAT) and prepare Odyssey architecture workshops, drawing on
  the same technical RAG/Confluence knowledge base as Tekos plus Google
  Drive/Docs and Mermaid diagram generation.
provenance:
  maintainer: Zuno Demo architecture team
  repository: zuno-demo
verification:
  status: unverified
freshness:
  last_reviewed: "2026-08-05"
sources: []
zuno:
  name: arkos
  status: active
  graph_shape: plan_draft_write
  primary_task: draft-architecture-testimonial
  tasks:
    - draft-architecture-testimonial
    - workshop-presentation
    - structure-demo
    - write-code
  memory:
    # ADR-0215: Arkos is C3/local-only (see model.preferred_classification
    # below), so its history-carrying model calls route to a local model
    # only. Its two reflexional tasks lead gpt-oss-20b and structure-demo
    # leads qwen3.6-27b-instruct, all of which serve 32768, so a generous
    # budget beats the conservative fleet default (app/registry.py's
    # HISTORY_TOKEN_BUDGET, 1800).
    #
    # KNOWN GAP (2026-09-03, measured, documented not fixed): "both serve
    # 32768" was true when written, when there were two local models.
    # There are four now, and qwen3.5-9b - the fleet default, and the LAST
    # entry in every one of this agent's C3 fallback chains below - serves
    # 8192. Confirmed live against the running predictor's /v1/models, not
    # just the chart value.
    #
    # Measured the same day, so the arithmetic is real rather than
    # estimated. Live rag-tech corpus: 68,962 chunks, median 1,247 chars
    # (~312 tokens at the char/4 heuristic), p95 1,796 (~449). Arkos does
    # not declare rag.top_k, so it retrieves the default 5.
    #
    #   draft-architecture-testimonial / workshop-presentation
    #     (allowed_knowledge: knowledge.tech + knowledge.project)
    #     6000 history + ~420 system prompt + up to 1200 project context
    #     (PROJECT_CONTEXT_TOKEN_BUDGET) + 5 chunks
    #     = ~9,180 tokens at median chunk size, ~9,865 at p95.
    #     Both OVERFLOW 8192 before a single output token.
    #
    #   structure-demo / write-code (allowed_knowledge: [])
    #     6000 + ~214 + 1200 = ~7,414. Fits, leaving ~780 for generation.
    #
    # So the exposure is the two RAG-bearing tasks, not all four, and
    # nothing clamps it: build_history_messages caps history against this
    # budget alone, with no awareness of the selected model's window, so
    # an oversized prompt reaches vLLM and 400s. It is the LAST candidate
    # in the chain, so this only bites when gpt-oss-20b, the 27B and wesh
    # have all already failed - the exact scenario the fallback exists
    # for, which is what makes it worth recording rather than shrugging at.
    #
    # Left unfixed deliberately, and it is not a number problem: any value
    # that survives the 8192 fallback (~2,800) would gut the 32768 nominal
    # path this agent actually runs on. The real fix is clamping the
    # assembled prompt against the selected model's own max_model_len,
    # which is a code change and its own decision.
    history:
      enabled: true
      max_turns: 6
      token_budget: 6000
  model:
    preferred_classification: C3
    notes: >-
      Placeholder pending v1 build; C3 anticipated because sovereign-marked
      DAT workflows are local-model-only per MEMORY.md section 5.
  access:
    # ADR-0040: agent entitlement group, orthogonal to the `consultant`
    # business role that governs tool/data permissions inside Arkos
    # (ADR-0349: architects are the consultant tier - the
    # confluence-archi-* skill subgroups live under /consultant - so
    # Arkos's audience moved from board to consultant; `board` means
    # Direction only).
    groups:
      - agent_arkos
  ui:
    displayName: Arkos
    tileDescription: Architecture DAT and workshop assistant.
    color: "#8F4700"
    icon: drafting-compass
---

# Arkos

ADR-0326 (WP-31): Arkos's real OKF task bundle, graph shape and deployment
surface merged with `status: placeholder` until the operator confirmed
Arkos was ready to go live (WP-31's own Status-updates section; ADR-0326's
"moves placeholder -> active only after the full common completion
pattern passes"). WP-11 (2026-08-21) flips `status` to `active` at the
operator's explicit direction: the portal now renders Arkos's tile as
enabled and Agent Runtime's generic dispatch serves
`/v1/agents/arkos/chat` instead of 404ing it. The two remaining
`platform/templates/agent/PROMOTION.md` steps (a formal 20-scenario human
review sign-off and a live `run_acceptance_gate.py` run) had not
completed as separate checkpoints at flip time - see
`evaluations/arkos/README.md` for that gate's status. No dedicated
namespace is reserved (ADR-0329, supersedes ADR-0023): Arkos's
frontend/BFF deploy into the shared `zuno-ai-run` namespace, same as
Tekos.

`zuno.graph_shape: plan_draft_write` (ADR-0342) names Agent Runtime's
LangGraph workflow module for Arkos's chat turns - plan, retrieve
(`knowledge.tech` + `knowledge.project`), draft, write (Drive, currently
undeclared - see each task's own file) - structurally distinct from
Tekos's `retrieve_reason_respond` shape,
proving the graph-shape mechanism WP-30 built generalizes past one
hardcoded workflow. Arkos has no agent-level `zuno.allowed_knowledge`
field either (ADR-0203), for the same reason Tekos doesn't: its knowledge
ceiling is the union of its one task's own `zuno.allowed_knowledge` -
today `[knowledge.tech, knowledge.project]`.

Access group is `agent_arkos` (ADR-0040 entitlement dimension, orthogonal
to the `consultant` business role that governs tool/data permissions
inside Arkos once active - see `policies/tools/tool-policy.yaml`'s
`drive.document.*`/`confluence.page.*` entries, both of which list
`consultant`). ADR-0349 moved Arkos's audience from board to the
consultant architect tier (the `confluence-archi-*` skill subgroups live
under `/consultant`; `board` means Direction only) - DATs are still
*reviewed* at board level as a business process, but the role gating an
already-entitled Arkos session is `consultant`, matching every other
agent's ADR-0040 dimension split.

<!-- BEGIN GENERATED AUTHORIZATION MATRIX (ADR-0503) - do not edit; regenerate with: python3 platform/okf/generate_authorization_matrix.py -->

## Authorization matrix

Generated per ADR-0503 from this bundle's frontmatter, `policies/tools/tool-policy.yaml`, `policies/knowledge/knowledge-policy.yaml`, `platform/ai-gateway/provider-routing.yaml` and `policies/model-routing/model-routing-policy.yaml` — the enforced intersection (ADR-0011/ADR-0203) restated for review, never read at runtime. Entitlement (ADR-0040): `agent_arkos`; model classification ceiling (ADR-0021): `C3`; status: `active`.

| Task (FOR WHAT) | Resource (WHAT) | Kind | Capability / server | Min class | Business roles (WHO) | Ext-model context | Quota | Policy source |
|---|---|---|---|---|---|---|---|---|
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `confluence.page.read` | tool | `confluence.page.read` @ confluence | C2 | consultant, board, cdp, lightspeed_readonly | blocked | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `confluence.page.read` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `confluence.page.search` | tool | `confluence.page.search` @ confluence | C2 | consultant, board, cdp, lightspeed_readonly | blocked | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `search_confluence` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `git.repository.read` | tool | `git.repository.read` @ git-forge | C2 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `git.repository.read` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `git.repository.list` | tool | `git.repository.list` @ git-forge | C2 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `git.repository.list` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `git.repository.private.read` | tool | `git.repository.private.read` @ git-forge | C2 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `git.repository.private.read` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `git.repository.private.list` | tool | `git.repository.private.list` @ git-forge | C2 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `git.repository.private.list` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `git.file.write` | tool | `git.file.write` @ git-forge | C2 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `git.file.write` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `git.repository.create` | tool | `git.repository.create` @ git-forge | C2 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `git.repository.create` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `diagram.generation.create` | tool | `diagram.generation.create` @ diagram-gen | C1 | consultant, adv, sales, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `generate_diagram` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `aap.platform.audit` | tool | `aap.platform.audit` @ aap | C2 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `aap.platform.audit` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `knowledge.tech` | knowledge | — | — | consultant, board, cdp | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.tech` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `knowledge.project` | knowledge | — | — | consultant, board, sales, adv, finance, cdp | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.project` |
| `workshop-presentation` (prompt: `prompts/workshop-presentation.md`) | `confluence.page.read` | tool | `confluence.page.read` @ confluence | C2 | consultant, board, cdp, lightspeed_readonly | blocked | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `confluence.page.read` |
| `workshop-presentation` (prompt: `prompts/workshop-presentation.md`) | `confluence.page.search` | tool | `confluence.page.search` @ confluence | C2 | consultant, board, cdp, lightspeed_readonly | blocked | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `search_confluence` |
| `workshop-presentation` (prompt: `prompts/workshop-presentation.md`) | `git.repository.read` | tool | `git.repository.read` @ git-forge | C2 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `git.repository.read` |
| `workshop-presentation` (prompt: `prompts/workshop-presentation.md`) | `git.repository.list` | tool | `git.repository.list` @ git-forge | C2 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `git.repository.list` |
| `workshop-presentation` (prompt: `prompts/workshop-presentation.md`) | `git.repository.private.read` | tool | `git.repository.private.read` @ git-forge | C2 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `git.repository.private.read` |
| `workshop-presentation` (prompt: `prompts/workshop-presentation.md`) | `git.repository.private.list` | tool | `git.repository.private.list` @ git-forge | C2 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `git.repository.private.list` |
| `workshop-presentation` (prompt: `prompts/workshop-presentation.md`) | `git.file.write` | tool | `git.file.write` @ git-forge | C2 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `git.file.write` |
| `workshop-presentation` (prompt: `prompts/workshop-presentation.md`) | `git.repository.create` | tool | `git.repository.create` @ git-forge | C2 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `git.repository.create` |
| `workshop-presentation` (prompt: `prompts/workshop-presentation.md`) | `diagram.generation.create` | tool | `diagram.generation.create` @ diagram-gen | C1 | consultant, adv, sales, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `generate_diagram` |
| `workshop-presentation` (prompt: `prompts/workshop-presentation.md`) | `aap.platform.audit` | tool | `aap.platform.audit` @ aap | C2 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `aap.platform.audit` |
| `workshop-presentation` (prompt: `prompts/workshop-presentation.md`) | `knowledge.tech` | knowledge | — | — | consultant, board, cdp | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.tech` |
| `workshop-presentation` (prompt: `prompts/workshop-presentation.md`) | `knowledge.project` | knowledge | — | — | consultant, board, sales, adv, finance, cdp | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.project` |

### Model routing

Effective per-task model chain (ADR-0021/ADR-0303/ADR-0412), resolved from `platform/ai-gateway/provider-routing.yaml`'s classification eligibility reordered by this `(agent, task)`'s `policies/model-routing/model-routing-policy.yaml` preference — the first entry is the reference model, the rest are fallback alternatives, in try order. The reference model is annotated with the model id it actually serves and that model's architectural role (`default`, `quality`, `reasoning`, `specialized`, `reasoning-external`, `code`, `general-external`); `provider-routing.yaml`'s `role` key is the authority for both, and every model reachable through the fallback chain is named in the **Available models** rollup below the table.

| Task | Classification ceiling | Reference model | Fallback chain | Adapter | Policy source |
|---|---|---|---|---|---|
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) → `reflect` | `C2` | `ovhcloud-gpt-oss-120b` → `gpt-oss-120b` (reasoning-external) | `local-gpt-oss-maas`, `local-gpt-oss`, `local-maas`, `local`, `local-wesh-maas`, `local-wesh`, `local-qwen35-maas`, `local-qwen35`, `openai`, `anthropic`, `mistral-codestral` | — | `policies/model-routing/model-routing-policy.yaml` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `C3` | `local-gpt-oss-maas` → `gpt-oss-20b` (reasoning) | `local-gpt-oss`, `local-maas`, `local`, `local-wesh-maas`, `local-wesh`, `local-qwen35-maas`, `local-qwen35` | — | `policies/model-routing/model-routing-policy.yaml` |
| `workshop-presentation` (prompt: `prompts/workshop-presentation.md`) → `reflect` | `C2` | `ovhcloud-gpt-oss-120b` → `gpt-oss-120b` (reasoning-external) | `local-gpt-oss-maas`, `local-gpt-oss`, `local-maas`, `local`, `local-wesh-maas`, `local-wesh`, `local-qwen35-maas`, `local-qwen35`, `openai`, `anthropic`, `mistral-codestral` | — | `policies/model-routing/model-routing-policy.yaml` |
| `workshop-presentation` (prompt: `prompts/workshop-presentation.md`) | `C3` | `local-gpt-oss-maas` → `gpt-oss-20b` (reasoning) | `local-gpt-oss`, `local-maas`, `local`, `local-wesh-maas`, `local-wesh`, `local-qwen35-maas`, `local-qwen35` | — | `policies/model-routing/model-routing-policy.yaml` |
| `structure-demo` (prompt: `prompts/structure-demo.md`) | `C3` | `local-maas` → `qwen3.6-27b-instruct` (quality) | `local`, `local-gpt-oss-maas`, `local-gpt-oss`, `local-wesh-maas`, `local-wesh`, `local-qwen35-maas`, `local-qwen35` | — | `policies/model-routing/model-routing-policy.yaml` |
| `write-code` | `C3` | (none eligible) | — | — | `policies/model-routing/model-routing-policy.yaml` |

**Available models** (ADR-0419, generated): the union of every model reachable by any task or prompt slot above, at any classification, each with the model id it serves and that model's role - `local-maas` → `qwen3.6-27b-instruct` (quality), `local` → `qwen3.6-27b-instruct` (quality), `local-gpt-oss-maas` → `gpt-oss-20b` (reasoning), `local-gpt-oss` → `gpt-oss-20b` (reasoning), `local-wesh-maas` → `qwen3.5-9b-wesh` (specialized), `local-wesh` → `qwen3.5-9b-wesh` (specialized), `local-qwen35-maas` → `qwen3.5-9b` (default), `local-qwen35` → `qwen3.5-9b` (default), `openai` → `gpt-4o-mini` (general-external), `anthropic` → `claude-3-5-sonnet-latest` (general-external), `mistral-codestral` → `codestral-latest` (code), `ovhcloud-gpt-oss-120b` → `gpt-oss-120b` (reasoning-external).

<!-- END GENERATED AUTHORIZATION MATRIX -->
