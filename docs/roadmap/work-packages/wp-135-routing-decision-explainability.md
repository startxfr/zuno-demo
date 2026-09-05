# WP-135: Surface the real model-routing decision in the Zuno frontend

- **State:** Done (2026-09-05 - repo-side mechanism complete: ai-gateway publishes the real per-request routing decision to a short-TTL Redis side-channel (`app/routing_decisions.py`) and exposes it via `GET /v1/routing-decisions/{request_id}`; agent-runtime fetches it once per turn and assembles the full contract (`app/main.py::_build_routing_metadata`); agent-bff forwards it through both `runtime.ChatResponse`/`apiChatResponse` and `openapi.json`; the frontend renders it as a collapsed "Show routing details" panel. Unit/contract test coverage lands in all four components. All six "Required demo cases" live-verified 2026-09-05 during WP-136's rehearsal 1/2, driven from the real frontend in the presenter's own browser against a live cluster: (1) Arkos C1->OVHcloud `gpt-oss-120b` external; (2) Arkos C2->local `gpt-oss-20b`; (3) Tekos `write-code`->`codestral-latest`/`mistral-codestral`; (4) Comage normal->`qwen3.5-9b-wesh`/`local-wesh-maas`; (5) Comage during the live WP-105 failover drill (AAP workflow job #709, Inject phase)->fallback `qwen3.5-9b`/`local-qwen35-maas` with `fallback_used=true, fallback_from=local-wesh-maas`; (6) Comage after Restore->back to `qwen3.5-9b-wesh`/`local-wesh-maas`, `fallback_used=false`. Every panel field matched AI Gateway routing-decision evidence pulled directly from the cluster (LangGraph checkpoint state, `oc get build`/`oc logs`) in every case.)
- **ADRs:** ADR-0550
- **Depends on:** WP-137 for the final DAT fields; existing AI Gateway routing/telemetry
- **Estimated effort:** 1–1.5 days
- **Difficulty:** Medium

## Goal

Make the webinar audience able to see **why** Zuno chose a model without opening logs or reconstructing the policy manually.

The UI must expose server-produced routing metadata for each response.

## Existing gap

The AI Gateway already knows the serving provider/model, but the existing stack historically drops some routing fields before they reach Agent Runtime/BFF/frontend. ADR-0536 explicitly had to prove fallback by metrics because `zuno_provider` was not propagated through the user-facing chain.

This WP closes that observability/explainability seam for interactive use.

## Contract

For each final assistant response, propagate a technical metadata object equivalent to:

```json
{
  "agent": "arkos",
  "task": "draft-architecture-testimonial",
  "project_id": "...",
  "project_classification": "C2",
  "effective_classification": "C2",
  "selected_model": "gpt-oss-20b",
  "selected_provider": "local-gpt-oss-maas",
  "execution_location": "local",
  "fallback_used": false,
  "fallback_from": null,
  "local_only_required": true,
  "routing_reason": "DAT C2 requires local inference"
}
```

Names may follow the repository's existing response-schema conventions; the requirement is semantic, not a forced JSON shape.

## Repo changes

### 1. AI Gateway response metadata

Ensure the final successful candidate and fallback information is represented in the gateway response/event stream:

- selected provider;
- served model;
- whether an earlier candidate failed;
- first failed candidate when useful;
- effective classification received by the gateway;
- task and agent identifiers already present in Zuno headers/context.

Do not expose provider credentials, internal URLs, tokens or sensitive exception bodies.

### 2. Agent Runtime propagation

Carry the routing metadata alongside the generated response without recomputing the decision.

The runtime may add authoritative project/effective-classification fields it already owns, but must not independently decide what provider "should" have been selected.

### 3. BFF contract

Forward the metadata through the existing authenticated API/streaming contract.

Update OpenAPI/Swagger schemas and tests.

### 4. Frontend panel

Add a compact PatternFly technical disclosure, for example:

```text
Routing details
  Task                 DAT
  Project              webinar-confidential
  Classification       C2
  Model                gpt-oss-20b
  Provider             Local / OpenShift AI
  Fallback             No
  Reason               C2 DAT requires local inference
```

For the failover scenario:

```text
Model                qwen3.5-9b
Fallback             Yes
Fallback from        qwen3.5-9b-wesh
```

The panel should be collapsed by default for normal chat usability.

It may be guarded by a technical/demo feature flag or role if desired.

## Required demo cases

Verify the panel for:

1. Arkos DAT C1 -> OVHcloud `gpt-oss-120b`, external;
2. Arkos DAT C2 -> local `gpt-oss-20b`;
3. Tekos `write-code` -> Codestral;
4. Comage normal -> `qwen3.5-9b-wesh`;
5. Comage during WP-105 failure -> fallback `qwen3.5-9b`, with fallback indication;
6. Comage after restore -> Wesh preferred again.

## Security requirements

- No secrets or provider API endpoints in user-visible metadata.
- Do not leak hidden prompt text or restricted source names merely to explain routing.
- If `routing_reason` is free text, generate it from controlled reason codes/templates, not raw provider exception strings.
- The decision panel is informational only; it must not provide a client-side override that bypasses policy.

## Out of scope

- Rebuilding routing policy in JavaScript.
- A full observability dashboard.
- Cost/budget UI.
- Dynamic provider selection by the end user.
- Changing the actual provider preference chains.

## Completion criteria

WP-135 is done when all five webinar scenario types can be driven from the real frontend and the displayed routing metadata matches AI Gateway/telemetry evidence.

## Operator / human follow-up (not executable by the model without explicit go-ahead)

1. Repo-side is complete: ai-gateway's routing-decisions side-channel and endpoint, agent-runtime's fetch/assembly, agent-bff's contract forwarding (Go structs + `openapi.json`), and the frontend's collapsed panel are all merged, each with its own unit/contract tests green (`components/ai-gateway/tests/test_routing_decision*.py`, `components/agent-runtime/tests/test_routing_metadata.py`/`test_model_router_routing_decision.py`, `components/agent-bff`'s `go test ./...`, `agent-frontend`'s `tsc --noEmit`).
2. A real, known limitation to account for while rehearsing: the routing panel is only populated for the direct model-call paths (`reason`/`code`/`demo` in Tekos, `draft`/`reflect`/`code`/`demo` in Arkos) - a reply that goes through an image/diagram/git-forge tool-call or the narrated-visual retry branch will show an empty/placeholder panel, since those shared helper functions (`app/graph/nodes.py`'s `_resolve_image_generation_call`/`_resolve_diagram_generation_call`/`_resolve_git_forge_calls`/`_retry_narrated_visual_tool_call`) were not extended to set `task_name`. None of the five webinar scenarios exercise these branches.
3. **Done 2026-09-05**: all six "Required demo cases" driven from the real frontend in the presenter's own browser against a live cluster, including the live WP-105 failover drill (cases 5/6, AAP workflow job #709) - see the State line above. The panel's collapsed/expanded behavior was exercised live throughout (not merely a synthetic Playwright check), satisfying the real-browser requirement without needing a Node >=18 environment.
4. This WP's tracker is now `Done`; contributes toward ADR-0550 `Status` -> `Implemented` once WP-136 is verified too (WP-137 already verified alongside this same rehearsal).
