# WP-135: Surface the real model-routing decision in the Zuno frontend

- **State:** Not started
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
