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
- Legacy tool names (`search_confluence`, `read_gmail`, ...) are explicit
  `aliases` during migration; new agent contracts use canonical IDs.

The file ships inside the mcp-gateway image (repo-root build context, see
`components/mcp-gateway/Dockerfile`) and is re-read via the gateway's
`/admin/reload-policy` endpoint.

## Authentication mode (ADR-0208)

Every entry declares a required `auth_mode` field, one of:

- **`delegated-user`** — the call must run with the CALLING user's own
  delegated credential for that backend (ADR-0014: per-user delegated
  OAuth2, never domain-wide service-account impersonation). No delegated
  credential available (including a revoked permission) is a deterministic
  denial — this mode never falls back to a shared/service credential.
  Google Workspace capabilities (`drive.*`, `gmail.*`) use this mode; a
  future `calendar.*`/`meet.*` binding would too.
- **`service-identity`** — the call runs with a shared backend credential
  (a workload token, a technical API key, ...), never a per-user one. The
  gateway's own policy-intersection decision (`policy.evaluate()`) has
  already evaluated the specific calling subject before this credential is
  ever used — there is no separate per-call gate beyond that. Every
  streamable-HTTP binding here (`confluence.page.*`) and the
  remaining in-process ones (`web.page.search`, `email.report.send`) use
  this mode.
- **`provider-delegated`** — reserved for a future on-behalf-of delegation
  flow (a provider acting for the platform rather than a specific end
  user). Schema-only today: no binding declares it, and the gateway
  refuses to invoke one that does (501) until a real implementation lands.

Mode is explicit, never inferred from the capability/tool name — a binding
missing `auth_mode`, or declaring an unrecognized value, fails to load
(`components/mcp-gateway/app/bindings.py`'s fail-closed `_validate`).
Enforcement (which credential flow a mode actually requires before the
downstream call) lives in `components/mcp-gateway/app/main.py`'s
`invoke_tool`; the delegated-user credential itself is resolved by
`components/mcp-gateway/app/delegation.py`, currently a documented seam
(no live Google Workspace tenant is reachable from this environment — see
that module's docstring for what a real integration replaces).

## Backend endpoint defaults (ADR-0119)

An optional top-level `backends:` map lets every streamable-http entry of
one backend share a default `{env, default, path}` instead of repeating it
per capability — useful once a backend has several capabilities. A
per-entry `endpoint:` still always wins when present; nothing written
before this feature needs to change:

```yaml
backends:
  some-backend:
    env: SOME_BACKEND_MCP_URL
    default: "http://some-backend-mcp.zuno-ai-run.svc:8000"
    path: /mcp

bindings:
  - capability: some-backend.thing.read
    backend: some-backend
    transport: streamable-http
    provider_tool: read_thing
    auth_mode: service-identity
    # no endpoint: here - inherits the `some-backend` default above
```

A streamable-http entry with neither its own `endpoint:` nor a matching
`backends:` default fails to load, same fail-closed rule as any other
malformed entry.
