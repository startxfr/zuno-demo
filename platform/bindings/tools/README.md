# Tool backend bindings (ADR-0116)

`tool-bindings.yaml` is the platform backend-binding registry: it resolves a
logical tool capability (`<domain>.<resource>.<verb>`, the stable contract
OKF tasks and `policies/tools/tool-policy.yaml` reference) to the physical
backend that serves it (MCP server, transport, endpoint, native tool name).

Rules (from ADR-0116):

- Bindings are **platform-controlled configuration** - never supplied by an
  agent or caller. OKF bundles contain logical capability IDs only; MCP
  server names, Kubernetes Services, URLs and provider tool names live here.
- The MCP Gateway authorizes (`policy.evaluate()`, the full ADR-0011
  intersection) **before** resolving or invoking a binding.
- Unknown capabilities and missing bindings **fail closed**: deterministic
  denial, no backend contacted. Startup/readiness validation requires every
  policy-listed capability to resolve to exactly one binding
  (`components/mcp-gateway/app/bindings.py`).
- Changing the physical server behind a capability is a change to this file
  (plus deployment config) only - agent definitions and runtime code stay
  untouched.
- Legacy tool names (`search_confluence`, `get_customer`, ...) are explicit
  `aliases` during migration; new agent contracts use canonical IDs.

The file ships inside the mcp-gateway image (repo-root build context, see
`components/mcp-gateway/Dockerfile`) and is re-read via the gateway's
`/admin/reload-policy` endpoint.
