# Sequence Flows

Last reviewed: 2026-11-19

Five flows. The first two are the original request flows of the platform. They predate UnifAI (ADR-0561): the
Tekos frontend, BFF and Agent Runtime they name were superseded by UnifAI, and the "Sales MCP" box has no counterpart
under `components/mcp-servers/` today (the Salesforce server is `salesforce`). They are kept for the legs that still
hold: the user's identity travels with the call, the model goes through the ai-gateway, tools go through the
mcp-gateway, and a write is a deterministic, audited state change. The next three flows are the current ones.

## Tekos RAG request

```mermaid
sequenceDiagram
  actor U as User
  participant F as Tekos Frontend
  participant B as Tekos BFF
  participant R as Agent Runtime
  participant G as AI Gateway
  participant K as RAG
  participant M as Model
  U->>F: Ask technical question
  F->>B: Authenticated request
  B->>R: Agent + task + user context
  R->>K: Retrieve permitted knowledge
  K-->>R: Ranked sources
  R->>G: Model request + allowed context
  G->>M: Routed inference
  M-->>G: Stream tokens
  G-->>R: Stream + usage
  R-->>B: Answer + citations
  B-->>F: SSE stream
```

## Controlled sales write

```mermaid
sequenceDiagram
  actor U as User
  participant R as Agent Runtime
  participant M as MCP Gateway
  participant S as Sales MCP
  participant D as PostgreSQL
  U->>R: Request state change
  R->>M: Authorized tool call
  M->>S: Identity + agent + task + operation
  S->>S: Validate policy/state transition
  S->>D: Deterministic update
  D-->>S: Result
  S-->>R: Auditable result
```

## A Tekos turn through UnifAI

Scenario: [UnifAI agents](../demo/scenarios/experiences/unifai-agents.md). Decisions:
[ADR-0561](../adr/0561-adopt-unifai-as-the-agent-platform.md),
[ADR-0562](../adr/0562-authenticate-unifai-against-the-zuno-keycloak-realm.md),
[ADR-0563](../adr/0563-forward-caller-identity-and-zuno-context-headers-from-unifai.md),
[ADR-0568](../adr/0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md).

```mermaid
sequenceDiagram
  autonumber
  actor U as Persona (browser)
  participant UI as unifai-ui
  participant ID as unifai-identity
  participant KC as Keycloak realm zuno
  participant MAS as unifai-multiagent-be<br/>(workflow tekos)
  participant RAG as unifai-rag-server
  participant AIGW as ai-gateway
  participant MCPGW as mcp-gateway
  participant M as Model (MaaS, local)
  U->>UI: Open workspace agent-tekos, ask a question
  UI->>ID: OIDC, client unifai
  ID->>KC: Sign-in, groups claim
  KC-->>ID: Token with the persona's groups
  ID-->>UI: Team workspaces computed from the groups
  UI->>MAS: Run workflow tekos as the user
  MAS->>RAG: Retrieve (knowledge-tekos retriever)
  RAG-->>MAS: Ranked passages
  MAS->>AIGW: /v1, user token forwarded, model auto<br/>X-Zuno-Agent tekos, X-Zuno-Task, X-Zuno-Data-Classification C2, X-Zuno-Run-Id
  AIGW->>M: Routed inference (classification, routing, quota, guardrails)
  M-->>AIGW: Tokens
  AIGW-->>MAS: Completion
  opt The model asks for a tool offered to this caller
    MAS->>MCPGW: /mcp, user token forwarded, X-Zuno-Agent, X-Zuno-Task
    MCPGW-->>MAS: Result (only tools of the caller's groups)
  end
  MAS-->>UI: Answer in the Live workflow panel
  UI-->>U: Answer
```

## An approved A2A delegation

Scenario: [A2A delegation with approval](../demo/scenarios/governance/a2a-delegation-approval.md). Decisions:
[ADR-0401](../adr/0401-introduce-agent-delegation-limited-to-targets-an-agent-declares.md),
[ADR-0403](../adr/0403-propagate-the-users-identity-and-the-delegation-chain-across-a2a-calls.md),
[ADR-0406](../adr/0406-limit-agent-delegation-by-depth-cycle-and-budget.md),
[ADR-0409](../adr/0409-introduce-human-approval-for-delegated-operations-resumable-from-persisted-checkpoints.md),
[ADR-0585](../adr/0585-serve-zuno-agents-over-a2a-from-a-gateway-answering-with-the-callers-identity.md).

```mermaid
sequenceDiagram
  autonumber
  actor U as consultant-02
  participant UI as UnifAI UI
  participant W as UnifAI worker<br/>(Arkos)
  participant A2A as a2a-gateway<br/>/agents/tekos/
  participant AIGW as ai-gateway
  participant MCPGW as mcp-gateway
  participant AAP as mcp-aap, then AAP
  U->>UI: Prompt on workflow arkos
  UI->>W: Run Arkos as the user
  W->>A2A: message/send, user's token<br/>X-Zuno-Delegated-By, X-Zuno-Delegation-Depth 1
  Note over A2A: verify_chain: declared target, active, entitled,<br/>depth within limit, no cycle
  A2A->>MCPGW: tools/list, user's token + signed X-Zuno-Agent-Chain
  A2A->>AIGW: Tekos model call with the tools
  AIGW-->>A2A: Tool call aap.cluster.audit (write)
  A2A-->>W: input-required, zuno.approval
  W-->>UI: approval_required
  UI-->>U: Approval card
  alt Approve within 300 s
    U->>UI: approve
    UI->>W: answer
    W->>A2A: Same task, decision approve
    A2A->>MCPGW: tools/call aap.cluster.audit
    MCPGW->>AAP: cluster_audit (tool policy checked)
    AAP-->>A2A: Job id and link
    A2A-->>W: completed
    W-->>UI: Arkos answer with the job link
  else Reject or no answer for 300 s
    A2A-->>W: Not approved, nothing ran
  end
```

## A signed release to a pod

Scenario: [OKF signed agent release](../demo/scenarios/foundation/okf-signed-agent-release.md). Decisions:
[ADR-0576](../adr/0576-extract-agent-definitions-and-corp-policies-into-the-zuno-demo-agents-repository.md),
[ADR-0578](../adr/0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md),
[ADR-0580](../adr/0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md),
[ADR-0564](../adr/0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md).

```mermaid
sequenceDiagram
  autonumber
  actor Dev as Agents maintainer
  participant AR as zuno-demo-agents<br/>(GitHub)
  participant SIG as Sigstore<br/>(GitHub OIDC, Fulcio, Rekor)
  participant QIO as quay.io/zuno
  participant PR as zuno-demo<br/>okf-promote.yml
  participant Q as internal Quay
  participant F as okf-fetch<br/>(init container)
  participant GW as mcp-gateway,<br/>a2a-gateway
  participant OP as unifai-operator
  Dev->>AR: Pull request on main (review, lint, test)
  AR->>AR: Release tag vX.Y.Z, publish.yml re-runs the checks
  AR->>QIO: Push one artifact per agent + okf-corp index
  AR->>SIG: Keyless signature, checks attestation
  PR->>QIO: Find the newest release
  PR->>PR: Verify offline, update agents.lock, open a pull request
  Dev->>PR: Merge = promotion (one digest in platform/okf/agents.lock)
  PR->>Q: make d3 admit agents: copy by digest with signatures
  GW->>F: Pod starts
  F->>Q: Pull okf-corp by digest (mirror first)
  F->>F: cosign verify offline against the committed trust root and identity
  alt Valid signature
    F-->>GW: VERIFIED, bundle readable under /okf
  else No valid signature
    F-->>GW: exit 1, pod stays in Init
  end
  OP->>QIO: Read each UnifaiAgentBundle source at its digest
  OP->>OP: Verify keyless signature, check ceilings, emit objects
```

For a fuller, scenario-based walkthrough of the same pipeline (AI Gateway, OKF, RAG, MCP, model routing and tracing) with per-agent diagrams, see [Agent Request Workflow](../agents/request-workflow.md).
