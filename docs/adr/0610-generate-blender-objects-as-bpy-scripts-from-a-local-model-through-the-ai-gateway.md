# ADR-0610: Generate Blender objects as bpy scripts from a local model through the ai-gateway

- **Status:** Accepted
- **Target:** v0.17
- **Date:** 2026-11-07
- **Decision owners:** Zuno Demo architecture team, with the DevOps / infrastructure and 3D content creation teams
- **Extends:** [ADR-0587](0587-admit-additional-user-experiences-over-the-one-governed-backend.md) (an experience client
  that runs on a workstation, with no namespace of its own)
- **Related:** [ADR-0596](0596-let-experience-clients-pick-a-declared-code-model-routed-to-codestral-first.md),
  [ADR-0565](0565-derive-data-classification-from-okf-and-only-allow-raising-it.md),
  [ADR-0593](0593-key-the-per-user-quota-and-telemetry-by-persona-across-experiences.md),
  [ADR-0592](0592-declare-experience-clients-in-the-agents-release-apart-from-agents.md),
  [ADR-0511](0511-define-okf-quota-policy-enforced-via-kuadrant.md),
  [ADR-0211](0211-publicly-trusted-wildcard-tls-via-lets-encrypt-and-route53.md),
  [ADR-0602](0602-harden-the-platform-trust-boundaries-before-a-customer-runs-it.md),
  [ADR-0603](0603-close-the-medium-severity-security-gaps-found-in-the-2026-11-06-review.md),
  [ADR-0606](0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md)

Scope: a proof of concept and a technical demonstration. Demonstration script:
[docs/demo/blender-3d.md](../demo/blender-3d.md).

## Context

3D content creators want AI help to generate objects, geometry and scenes directly in Blender on their workstations.
Corporate data governance, security rules and intellectual property forbid sending design prompts, geometry or
corporate assets to public cloud AI endpoints.

The platform already runs Red Hat OpenShift AI with GPU-backed vLLM serving of open-weight models, and every user
experience reaches those models through one governed chain: the ai-gateway (routing, guardrails, quotas, telemetry,
classification) in front of MaaS. What is missing is a way for a desktop application, outside the cluster, to use
that chain without carrying its own model key.

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | `gpt-oss-20b` and `qwen3.5-9b` are already served; no new runtime or GPU is needed. | `gitops/charts/models/templates/llminferenceservice-gptoss.yaml` (namespace `zuno-ai-run`, 131072-token window); `platform/ai-gateway/provider-routing.yaml` (`local-gpt-oss-maas`, role `reasoning`; `qwen3.5-9b`, role `default`, the terminal fallback of ADR-0531). |
| F2 | `gpt-oss-20b` is the platform's fastest local model; `qwen3.5-9b` is not fast here. | `gpt-oss-20b` 61.1 to 85.9 tok/s (`docs/roadmap/work-packages/wp-086-spread-models-and-platform-hygiene.md`); `qwen3.5-9b` about 22.5 tok/s, warm runs, direct to the predictor, measured live on 2026-09-03. |
| F3 | The ai-gateway has no entry outside the cluster. | `gitops/charts/ai-gateway/templates/` has no Route or HTTPRoute; its NetworkPolicy is a precise ingress allow-list (`templates/networkpolicy.yaml`). |
| F4 | ADR-0587's admission contract assumes an in-cluster client. | ADR-0587 clause 1: own namespace labelled `zuno.io/experience-client`, own Keycloak client, `zuno` JWT, no model key, no MaaS token. |
| F5 | The platform already fronts in-cluster backends with Kuadrant, issuer and audience pinned. | `gitops/charts/connectivity-link/templates/quota-demo-gateway.yaml` and `quota-demo-route.yaml`: Gateway API Gateway, HTTPRoute, AuthPolicy, RateLimitPolicy, fronted by a reencrypt Route on the router's `*.apps` wildcard (ADR-0511, ADR-0555, ADR-0602 clause 6). |
| F6 | An experience client can already select a declared task by model name. | ADR-0596: `modelTaskAliases` in `gitops/charts/ai-gateway/values.yaml` (`zuno-code=code:Zuno Code`); the task's routing policy picks the provider. |
| F7 | A per-client classification floor can force every call of a client to local models. | ADR-0565 clause 5, `classification.clientFloors` in `gitops/charts/ai-gateway/values.yaml`; SaaS providers are eligible at C1 and C2 only (ADR-0596 clause 4). |
| F8 | Turning certificate verification off is a finding being removed, not a pattern to add. | ADR-0603 M3 (certificate verification off for credentialed calls). |

## Decision

**A Blender add-on asks a local model, through the ai-gateway and under the user's own identity, for a Blender Python
(`bpy`) script, shows it to the user and runs it only on their click; no prompt, script or asset leaves the platform.**

```text
[ Workstation: Blender add-on ]
        |  1. OAuth 2.0 device sign-in (Keycloak realm zuno, client "blender")
        |  2. HTTPS, verified TLS, Bearer <user's zuno JWT>
        v
[ Kuadrant entry: HTTPRoute + AuthPolicy (issuer, audience, azp) + RateLimitPolicy ]
        |
        v
[ ai-gateway: model "zuno-3d" -> task "bpy", floor C3, quota, guardrails, telemetry ]
        |
        v
[ MaaS -> KServe vLLM: gpt-oss-20b, fallback qwen3.5-9b (zuno-ai-run) ]
```

1. **Text to script, not text to mesh.** The model returns an executable `bpy` script; Blender builds native objects
   with parameters, modifiers, materials and node trees that the artist can edit. No mesh-generation model (TripoSR,
   InstantMesh) is served, and the request and the answer are small JSON text payloads.
2. **A declared model mapped to a declared task (ADR-0596 shape).** `blender` is declared as an experience client in
   the agents release (ADR-0592) with one task, `bpy`, and no tools. The ai-gateway maps the model name `zuno-3d`
   ("Zuno 3D") to that task through `modelTaskAliases`. The task's routing puts `gpt-oss-20b` (role `reasoning`)
   first and `qwen3.5-9b` (role `default`) after it, and names no SaaS provider. The add-on sends
   `temperature: 0.2` and its own versioned system prompt.
3. **Local only, enforced by the classification floor.** `clientFloors` gets `blender: C3`, so every call from the
   client is classified C3 and only local providers are eligible, whatever the routing table gains later. This is
   what "sovereign" means here, and it can be checked in the configuration and on every `model_call` span.
4. **A workstation experience client (extends ADR-0587).** ADR-0587's contract applies, minus the namespace, which a
   desktop application does not have:
   - a public Keycloak client `blender` in realm `zuno`, with the OAuth 2.0 device authorization grant only: no
     password grant and no client secret on a workstation;
   - the `maas-gateway-audience` mapper, so the token carries the `zuno-admin-api` audience the ai-gateway requires
     (ADR-0602);
   - the access token and the refresh token are held in Blender's process memory only, never written to the `.blend`
     file or to the preferences;
   - `blender` is listed in the ai-gateway's `experienceClients` (the `client` label of ADR-0587 clause 2). It is not a
     trusted platform client and not a persona-claim client: the token is the person's own, so quota and telemetry
     are keyed by that person (ADR-0593);
   - it reaches no MCP tool.
5. **One external entry, limited to two paths.** The ai-gateway gets a hostname on the Kuadrant pattern of F5: an
   HTTPRoute admitting only `POST /v1/chat/completions` and `GET /v1/models`, an AuthPolicy that pins the issuer and
   the audience (ADR-0602 clause 6) and admits only the declared workstation clients by `azp` (today `blender`), and
   a per-user RateLimitPolicy. The ai-gateway's own JWT check stays in force behind it. How the Kuadrant gateway
   reaches the meshed ai-gateway is settled by the work package and recorded here as a dated update.
6. **Show, check, then run.** The add-on writes the returned script into a Blender text block, strips Markdown fences,
   parses it with Python's `ast` and refuses it when it imports anything outside `bpy`, `bmesh`, `mathutils`, `math`
   and `random`, calls `exec`, `eval`, `compile`, `open` or `__import__`, touches a dunder attribute, or reaches
   `bpy.ops.wm`, `bpy.ops.script`, `bpy.ops.preferences`, `bpy.utils` or `bpy.app.handlers`. The script runs only
   when the user clicks **Run**, from the text block (so the user's edits count), as one undo step. The check
   catches a confused model; it is not a sandbox.
7. **TLS is always verified.** The add-on verifies the server certificate against the system store and the `certifi`
   bundle that ships with Blender. Where the `*.apps` routes serve the Let's Encrypt wildcard (ADR-0211), nothing
   else is needed; on a cluster with a private CA, an add-on setting points at that CA file. There is no setting that
   turns verification off.
8. **The model choice is measured before it is shown.** A fixed set of prompts is run against both models. A result
   counts as a success when the script parses, passes the check of clause 6, and runs without error in
   `blender --background` while creating at least one object. The success rates and latencies are recorded here as a
   dated update, and the demonstration uses only prompts from the set that succeed with `gpt-oss-20b`.
9. **Definition of done (ADR-0606 clause 1).** A work package with a tracker row; a golden-path probe (device
   sign-in, a `zuno-3d` completion, a script that passes the check); a written rollback (remove the HTTPRoute,
   AuthPolicy, RateLimitPolicy and Route, and the Keycloak client; the add-on is a local file); the demonstration
   script [docs/demo/blender-3d.md](../demo/blender-3d.md); and `blender` in `experienceClients`.

### Model assessment at decision time

The first two rows are expectations to be confirmed by clause 8; the third is measured (F2).

| Criteria | `gpt-oss-20b` (selected) | `qwen3.5-9b` (fallback) |
|---|---|---|
| Architecture | Mixture of experts, 20.9B parameters, MXFP4 | Dense, 9B parameters |
| `bpy` syntax accuracy | Expected high: follows the "code only" instruction | Expected moderate: occasional invented API calls |
| Spatial reasoning | Expected better on vector and matrix transforms | Basic primitive placement |
| Throughput on this platform | 61 to 86 tok/s | about 22.5 tok/s |

## Alternatives considered

- **A text-to-3D mesh model (TripoSR, InstantMesh).** Produces static, non-editable polygon meshes, moves binary
  `.glb`/`.obj` payloads, and needs a new served model and a GPU slice. Rejected: editability is the point.
- **A static MaaS or gateway API key in the add-on.** Simpler, and the shape of the Claude Code path (WP-220). Rejected:
  a long-lived secret on a workstation, no per-person identity in quota and telemetry, and a model key in a client is
  what ADR-0587 forbids.
- **Calling MaaS or vLLM directly.** Skips the ai-gateway's routing fallback, classification floor, guardrails and
  telemetry. Rejected.
- **A dedicated ServingRuntime and namespace for `gpt-oss-20b`.** Duplicates a model that is already served (F1) and
  would use an unpinned image. Rejected.
- **Skipping certificate verification for private CAs.** Rejected (F8); clause 7 covers private CAs with a CA file.
- **Running the generated script automatically.** Rejected: the click on **Run** is the only human checkpoint before
  model-written code runs with the user's privileges.
- **Target v0.16.** Rejected: under ADR-0606 clause 2 the world model (ADR-0604) already takes one of v0.16's two
  experience slots, and v0.16 is the hardening band.

## Consequences

- 3D creators get editable Blender objects from a prompt, and the demonstration shows sovereignty through the same
  chain as the other experiences: `client="blender"` on the dashboards, a C3 floor and a local provider on every span.
- The ai-gateway gets its first entry outside the cluster. It is a new trust boundary, reviewed in the work package
  against ADR-0602.
- `gpt-oss-20b` is a reasoning model: a script of one to two thousand tokens takes about 15 to 40 seconds, so the
  add-on calls the gateway off Blender's main thread and keeps the interface responsive.
- The add-on is a file in this repository, installed by hand on each workstation; it is not an image and is not
  digest-pinned. A workstation takes it from a tagged release.

## Security considerations

- **Identity:** a new public Keycloak client with the device grant only; tokens live in process memory; the audience
  and `azp` are checked at the edge and again by the ai-gateway.
- **Network reach:** a new external hostname, limited to two paths, rate-limited per user. No MCP tool is reachable
  from it.
- **Code execution:** model-written Python runs inside Blender with the user's privileges. Mitigations: a local model
  behind the governed chain, the user's own identity, the static check and the explicit click of clause 6. The
  residual risk is accepted for a demonstration. A production use would run the script in a separate headless
  Blender process with no network and no access to the user's files.
- **Supply chain:** no new image; the add-on is reviewed as code in this repository.

## Operational considerations

- The Keycloak client is created by the same reconcile path as the other experience clients; the realm import alone
  does not reach a live realm.
- The probe of clause 9 runs with the other golden-path probes before a demonstration (ADR-0605).
- Usage is visible in the existing dashboards filtered on `client="blender"`, and in Tempo by the `model_call` span.
- Every cluster change goes through the repository (ADR-0608); nothing in the demonstration script applies objects by
  hand.

## Work packages

None opened yet. The work package is opened when the v0.17 band starts, with its number reserved under ADR-0606
clause 5.

## Update 2026-11-07 (WP-244): implementation choices

Executed ahead of the v0.17 band by user decision (weekend rush before the 2026-11-09 demonstration). What WP-244
builds, clause by clause, where it differs from the wording above:

- **Clause 2.** No model alias: the add-on names the task with `X-Zuno-Agent: blender` and `X-Zuno-Task: bpy`, the
  headers every caller uses, so `modelTaskAliases` and the fail-closed list are unchanged. The task is declared in the
  agents release (`experience-clients/blender/tasks/bpy.md`, `models.preferred: [reasoning, default]`, zuno-demo-agents
  b8ac031); until that release is promoted, the corp order answers.
- **Clause 3.** `zuno_ai_gateway_classification_client_floors: {blender: C3}`, keyed on the token's `azp`. `blender` is
  an experience client, never an agent, so every call of the client is a call that names no known agent and gets this
  floor; the stack generator writes floors for agents only. The task also forbids every external model role, so the
  generated routing excludes the SaaS providers as well.
- **Clause 5.** The entry is `gitops/charts/connectivity-link/templates/workstation-entry.yaml` (the ai-gateway's
  Application may not write to `openshift-ingress`): reencrypt Route, HTTPRoute on `zuno-agent-gateway` with the two
  paths and a 300 s timeout, AuthPolicy with issuer, audience, `azp` and an admitted group (demo333: `ocp-ai-dev`,
  persona ai-dev-01: a public device client lets every realm user mint a token, so the group narrows who may use the
  entry; an existing group, because group membership is not managed from this repository), and a RateLimitPolicy of
  60 requests per user per 5 minutes. The ai-gateway's port 8080 already accepts callers outside the mesh
  (PeerAuthentication `ai-gateway-from-unmeshed-clients`), and its own audience check is live (`JWT_AUDIENCE_REQUIRED`).
- **Clause 7.** demo333's routes serve the Let's Encrypt wildcard, so the add-on needs no CA file there.
