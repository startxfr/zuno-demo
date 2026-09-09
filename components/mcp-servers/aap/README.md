# aap MCP server

Exposes Ansible Automation Platform audits to agents (ADR-0355 / WP-074).
Scaffolded with `make new-mcp-server NAME=aap` (ADR-0119); the shape below
is the standard one - real `mcp` SDK server at `/mcp`, gateway-token
middleware (ADR-0037), `/healthz` that never touches the backend.

## Capabilities

| Capability | Tool | What it does |
|---|---|---|
| `aap.platform.audit` | `platform_audit` | Read-only. Controller/instance health, the `zuno-demo` Project's last Git sync, recent `zuno-day0-check` runs. Issues GET requests only. |
| `aap.cluster.audit` | `cluster_audit` | Launches the `zuno-day0-check` Job Template and returns immediately with the job id - does not wait for it to finish (2026-09-09: OpenShift Lightspeed's console plugin times out well before a real run completes). Call `platform_audit` afterwards to see whether it passed. |

Every job in either response carries a `url` (a link to that run in the AAP
Controller UI, via `AAP_CONTROLLER_UI_URL` below), and the most recent one
also carries a `log_tail` (its last ~5 non-blank output lines, fetched from
`job_events` rather than the full stdout blob). Both are `None`/absent when
`AAP_CONTROLLER_UI_URL` isn't configured or the job has no output yet.

`cluster_audit` is this repository's first agent-reachable capability that
runs automation rather than reading state. **It takes no arguments.** The
template comes from the module-level `JOB_TEMPLATE_NAME`, so no caller -
agent, gateway, or prompt-injected instruction - can point it at a
different Job Template, and the launch POST carries an empty body (the
template sets `ask_variables_on_launch: false`). That is the
server-construction half of ADR-0355's defence in depth; the other halves
are the AAP-side token and the agent OKF declarations.

## Configuration

| Env var | Source | Notes |
|---|---|---|
| `AAP_API_TOKEN` | ExternalSecret from Vault `zuno/aap/mcp-token` | The least-privilege `zuno-mcp` user's token. Never `zuno/aap/admin`, never WP-073's `zuno/aap/controller-token` (that one is admin). |
| `AAP_BASE_URL` | same secret, key `url` | The AAP **Gateway** Service, `http://aap.zuno-aap.svc`. Never `aap-controller-service`: on AAP 2.5+ it answers 401 to a gateway-minted token. |
| `AAP_CONTROLLER_UI_URL` | chart value `clusterBaseDomain` (`https://aap.<domain>`) | The Gateway's public Route - deliberately separate from `AAP_BASE_URL` above, which is internal-only and meaningless in a browser. Empty means no `url` field is surfaced, never a guessed hostname. |
| `MCP_GATEWAY_WORKLOAD_TOKEN` | `mcp-gateway-workload-token` Secret | ADR-0037. |
| `AAP_HTTP_TIMEOUT_SECONDS` | default `20` | Per-request timeout. |

The credential is minted by the Day 1 `aap_config` role, not the `vault`
role: an AAP token cannot be self-generated, it has to come back from a
live Gateway. So this server cannot become Ready before
`make d1 install aap-config` has run.

## Tests

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python tests/test_mcp_protocol.py
```

AAP is mocked at the transport boundary, so no cluster is needed. The
live, cross-component half - proving an unauthorized group is denied by
the gateway's policy layer rather than by AAP-side RBAC - lives in
`evaluations/tekos/security_checks.py` and
`evaluations/arkos/security_checks.py`.
