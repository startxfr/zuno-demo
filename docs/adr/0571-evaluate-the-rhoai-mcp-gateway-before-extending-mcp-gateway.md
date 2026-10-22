# ADR-0571: Evaluate the RHOAI MCP gateway before extending mcp-gateway

- **Status:** Implemented
- **Target:** v0.11
- **Date:** 2026-10-17
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md), [ADR-0036](0036-enforce-the-complete-mcp-authorization-intersection-in-the-gateway.md), [ADR-0043](0043-use-standard-mcp-protocol-behind-the-zuno-mcp-gateway.md), [ADR-0116](0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md), [ADR-0208](0208-standardize-enterprise-tool-authentication-and-delegation.md), [ADR-0524](0524-integrate-openshift-lightspeed-with-the-zuno-ai-platform.md), [ADR-0561](0561-adopt-unifai-as-the-agent-platform.md), [ADR-0563](0563-forward-caller-identity-and-zuno-context-headers-from-unifai.md), [ADR-0568](0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md)

## Context

The zuno mcp-gateway (`components/mcp-gateway`, about 2,100 lines of Python)
is the platform's only tool-policy enforcement point (ADR-0036). It
evaluates ADR-0011's five factors on every call: agent declaration and task
rights from the OKF bundles (`X-Zuno-Agent`, `X-Zuno-Task`), the tool's
presence in `policies/tools/tool-policy.yaml`, the declared
`X-Zuno-Data-Classification` against the tool's `min_classification`, and the
caller's JWT `groups` against `allowed_groups`. It resolves logical
capabilities through `platform/bindings/tools/tool-bindings.yaml`
(ADR-0116), speaks standard MCP streamable-HTTP to its downstream servers
(ADR-0043), forwards the caller's JWT and a workload token
(`X-Zuno-Gateway-Token`) to them, and carries an `auth_mode` per binding
(ADR-0208; `app/delegation.py` denies `delegated-user` calls without a
delegated credential). It also returns `external_model_policy.allow_context`
so the caller can force local-only inference (ADR-0035). Several tools are
in-process handlers rather than MCP servers: `rag_query`, `image_gen`,
`diagram_gen`, `web_search`, `gmail`, `drive`, `email_report`
(`app/handlers/`).

Its north side is primarily REST (`POST /v1/tools/{name}/invoke`), which no
standard MCP client speaks. ADR-0524 already added a standard MCP
streamable-HTTP front door (`POST /mcp`, `app/mcp_frontdoor.py`) for
OpenShift Lightspeed. That front door is deliberately narrow: it replaces
factors 1-2 with a deployment-time, read-only capability allowlist
(`lightspeed.frontdoorCapabilities` in `gitops/charts/mcp-gateway/values.yaml`,
five capabilities today), because a standard MCP client has no OKF bundle.

ADR-0561 makes UnifAI the agent platform. UnifAI agents reach tools through
an MCP client (SSE and streamable-HTTP, with OAuth) and cannot call the REST
contract. They could call `/mcp`, but only under Lightspeed's read-only
allowlist, without agent or task identity, so the full intersection would
not apply to them.

Two ways forward exist. Red Hat's Kuadrant community develops an MCP gateway
that aggregates MCP servers behind Envoy and authorizes with Kuadrant
policies; zuno already runs Connectivity Link (`rhcl-operator`,
`gitops/charts/connectivity-link`) and RHOAI 3.5. **Whether a supported MCP
gateway ships with the Connectivity Link or RHOAI versions installed on
`demo222` or `demo333`, and in what lifecycle state, is UNVERIFIED.** Nothing
in this repository installs, references or has measured one, and the
`demo222` catalogs are already known to publish fewer packages than their
predecessors (ADR-0558). The alternative is to extend zuno's own gateway.

## Decision

**Evaluate first, then take exactly one of two paths.** No code is written
on either path before the evaluation is recorded (WP-152).

### Evaluation criteria

A product gateway is adopted only if it meets **all** mandatory criteria on
the clusters zuno actually runs, measured live, not read from
documentation:

1. **Availability (mandatory).** The package is served by a Red Hat catalog
   on both clusters (`oc get packagemanifests --context <cluster>`), its
   lifecycle state is recorded (GA, Technology Preview, Developer Preview),
   and it installs through the existing operator pattern (ADR-0048,
   ADR-0558). A community-only build fails this criterion.
2. **Aggregation (mandatory).** One MCP streamable-HTTP endpoint aggregates
   several downstream MCP servers, and `tools/list` returns only the tools
   the caller may call.
3. **Authorization (mandatory).** Per-tool decisions can express all five
   ADR-0011 factors, fail closed: Keycloak `groups` from a validated realm
   `zuno` token; agent and task identity from the `X-Zuno-Agent` and
   `X-Zuno-Task` headers ADR-0563 forwards, checked against data generated
   from the OKF bundles; classification against `min_classification`. A
   gateway that authorizes on groups alone fails.
4. **Delegation (mandatory).** The caller's JWT is forwarded or exchanged
   toward downstream servers, a workload identity proof can be added, and a
   per-binding authentication mode (`service-identity`, `delegated-user`)
   can be honoured with a deterministic denial when a delegated credential
   is missing (ADR-0208).
5. **Local-only signal (mandatory).** A tool result can carry the
   equivalent of `external_model_policy.allow_context: false` to the
   caller; without it ADR-0035 is unenforceable downstream.
6. **Policy as GitOps data (mandatory).** Tool policy and bindings are
   declared or generated from `tool-policy.yaml` and `tool-bindings.yaml`
   under ArgoCD, with no hand-edited live state.
7. **Lightspeed continuity (mandatory).** The ADR-0524 front door,
   including its read-only allowlist, can be served by the same gateway.
8. **Observability (desirable).** OTel spans per call with tool, outcome and
   denial reason, inheriting `traceparent` (ADR-0566).
9. **Cost (desirable).** No GPU, and a resource footprint compatible with
   the quotas of both clusters.

### Path A: the product gateway passes

The mcp-gateway is replaced. Each in-process handler becomes a small MCP
server behind the product gateway (image, diagram, web search, Gmail, Drive,
email report). `rag_query` is removed rather than ported, because UnifAI
agents retrieve through UnifAI's retrievers (ADR-0568); the
`knowledge.tech.search` capability Lightspeed uses is rebound to UnifAI
retrieval by binding data, as ADR-0568 requires.

### Path B: the product gateway fails any mandatory criterion

The mcp-gateway is kept and its existing `/mcp` front door gains a second
policy mode for agent callers. A call carrying a validated JWT plus
`X-Zuno-Agent` and `X-Zuno-Task` is evaluated against the full five-factor
intersection through the same `evaluate()` path as the REST contract;
`tools/list` is computed from that intersection; the caller's JWT is
forwarded downstream as today. Lightspeed's allowlist mode is unchanged and
remains the only exception to factors 1-2. No second authorization code
path is introduced: the front door stays a protocol adapter, as its module
docstring requires.

On both paths ADR-0011 and ADR-0036 stand: the intersection and a single
mandatory enforcement point survive, whichever product enforces them.

## Planned supersession

Conditional on the evaluation outcome, recorded at cutover (WP-156):

- **Path B:** none. This record extends ADR-0043 and ADR-0524 clause 3.
- **Path A:** ADR-0043 **in full** (its decision to keep the Zuno MCP Gateway
  as the enforcement layer is replaced; its standard-MCP clause migrates
  into the product gateway); ADR-0116 **in part** (the gateway-side routing
  through `app/bindings.py` goes; logical capability identifiers and the
  binding registry as platform data stay); ADR-0524 **in part** (clause 3's
  hosting of the front door in `components/mcp-gateway` goes; the read-only
  allowlist and clause 4 stay).

## Consequences

The decision costs one evaluation before any MCP work for UnifAI. If the
product gateway passes, about 2,100 lines of gateway code and seven handlers
leave the zuno repository, and the platform demonstrates a Red Hat component
in place of custom code. If it fails, the extension is small, because the
front door, the intersection and the downstream MCP client already exist.

Either way, UnifAI agents depend on ADR-0563: without forwarded identity and
agent/task headers neither path can authorize them, and they are limited to
whatever an anonymous allowlist would grant, which this decision rejects.

## Security considerations

Criterion 3 is where a product gateway is most likely to fall short: group
checks are common, agent and task rights are zuno-specific. Adopting a
gateway that drops factors 1-2 for agent callers would widen every agent to
every tool its users' groups allow, which ADR-0036 forbids.

On path B, the new mode must not let a caller choose its own agent or task
identity unchecked. The headers are trusted only together with a validated
JWT, and the agent named must be one the user's groups entitle (ADR-0040).
How UnifAI asserts the agent identity for a Temporal-executed run is the open
question ADR-0563 already names.

Downstream MCP servers keep verifying `X-Zuno-Gateway-Token` and their
NetworkPolicy boundary, so the UnifAI namespace can never call them
directly.

## Operational considerations

The evaluation runs read-only first (`packagemanifests`, CSV lifecycle
annotations, documentation of the installed version) on both clusters; any
install happens on `demo333` only. `demo333` is powered off at the time of
writing and the user is asked to power it on. Every `oc` command passes
`--context`, since the shared kubeconfig's current context points at
`demo222`.

The outcome, with the measured result of each criterion, is recorded in
WP-152 and in a dated note on this record before either path starts.

## Evaluation outcome (2026-10-22)

The platform gateway is the Red Hat Connectivity Link `mcp-gateway` operator
v0.7.1 (upstream Kuadrant/mcp-gateway), a Technology Preview on `demo333`. It
federates MCP servers behind one endpoint, authorizes per tool by JWT claim
through Kuadrant AuthPolicy and forwards the user's token. It does not carry
ADR-0011's agent declaration and task rights, which would have to be
re-implemented as custom policy twice (listing and calling) over an
unauthenticated header. The user chose path B: `/mcp` applies the full
intersection to callers that declare an agent, and the platform gateway is
re-evaluated when it reaches GA. Details and evidence: WP-152.

