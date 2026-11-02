# WP-187 step 1: what the C1 label on UnifAI RAG results exposes

Measured on demo333 on 2026-11-02 (read-only: Tempo queries, probe pods that were deleted afterwards, and a read of the repository).
No cluster object was changed.

## What carries the data level of a turn

- The ai-gateway routes on the classification **declared by the caller** in `X-Zuno-Data-Classification` (default C1), together with
  `X-Zuno-Local-Only` and the per-task rules of `model-routing.generated.yaml` (`local_only_for`). It never looks at what was retrieved.
- Both external providers' `eligible_for` includes C1 and C2 (`platform/ai-gateway/provider-routing.yaml`, `ovhcloud-gpt-oss-120b`:
  `[C1, C2]`). Only C3 and above are local only. So the C1 versus C2 label makes no difference to routing by itself.
- Guardrail modes are `observe` for C1, C2 and C3 (`gitops/charts/ai-gateway/values.yaml`, `modeByClassification`), so the label changes nothing there either.

## Paths that reach the RAG

| Path | Reaches the RAG through | Level of the turn | Where the C1 label of `rag_query.py` matters |
|---|---|---|---|
| UnifAI agents (tekos, arkos, ...) | UnifAI's own retriever, **not** the mcp-gateway | static: bundle default plus `classificationOverrides` (tekos: C2 for `answer-technical-question` only) | nowhere: the constant is never read |
| OpenShift Lightspeed | the mcp-gateway front door, tool `search_technical_docs` | none: Lightspeed sends no classification; its model is the local MaaS `gpt-oss-20b` (`endpointMode: maas`, not through the ai-gateway) | only as a label in the tool result |
| REST callers | `POST /v1/tools/search_technical_docs/invoke` | declared by the caller | no agent declares this tool: `agent 'tekos' does not declare tool 'search_technical_docs'` (HTTP 403, ADR-0011) |

## Model calls of tekos and arkos, Tempo, 60 hours up to 2026-11-02 14:29Z

| Agent | Classification | Model kind | Calls | When |
|---|---|---|---|---|
| tekos | C2 | **saas** (`ovhcloud-gpt-oss-120b`) | 51 | 2026-10-31 10:00-11:00Z, before tekos 0.4.3 put the local model first |
| tekos | C2 | local | 30 | 2026-10-31 20:00Z, the first-token stresstest |
| tekos | C1 | local | 5 | 2026-10-31 (find-relevant-docs and similar) |
| arkos | C3 | local | 314 | 2026-10-31 (history proof) |

## Reading

1. The label is not the control. Changing `C1` to `C2` in the results would not stop a Confluence page from reaching an external model, because C2
   is eligible for SaaS. What decides is `local_only_for` per task and the order of the preferred providers.
2. Tekos's `answer-technical-question` has no `local_only_for`. It prefers local models only since 0.4.3. Before that, its 51 calls at C2 on 2026-10-31
   morning went to the external provider, in turns that retrieve Confluence first (`retrieveFirst: true`). Whether those calls carried a Confluence chunk was
   not checked; it is likely, since the stresstest asks Confluence-backed questions.
3. Tekos's `find-relevant-docs` and `check-my-drive-docs` declare no override (C1 by default), allow knowledge `knowledge.tech`, and list SaaS providers in their
   `fallback`. A Confluence chunk can reach them at a declared C1. No such call was seen in the window (5 calls at C1, all local).
4. The Lightspeed path cannot leak to an external model through this tool: its model is local. The cost of the C1 label there is an incorrect audit trail.
5. A `classification` field on the source and the chunk (WP-187 as written) only changes what the mcp-gateway returns. It raises no turn on the UnifAI path, because the
   UnifAI runtime does not read it. ADR-0565 clause 3 (a RAG source raises the session level) is a UnifAI feature that nothing implements yet.

## Not measured

Whether a given tekos call at C2 on 2026-10-31 contained a Confluence chunk; the content of the calls is not kept. Lightspeed through its real MCP front door (the
probe used the REST route, which needs a declaring agent).
