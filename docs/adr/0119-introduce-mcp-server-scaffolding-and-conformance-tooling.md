# ADR-0119: Introduce MCP server scaffolding and conformance tooling

- **Status:** Implemented - see `platform/scaffolding/new_mcp_server.py`, `platform/supply-chain/check_mcp_server_conformance.py`.
- **Target:** v0.1
- **Date:** 2026-08-19
- **Decision owners:** Zuno Demo architecture team

## Context

`components/mcp-servers/confluence`, `salesforce` and `sales-db` are
already near-identical copies of one another (their own docstrings say
so: "templated from confluence"/"templated from sales-db"). Registering a
new MCP server today means touching six places by hand: the component
directory itself, `platform/bindings/tools/tool-bindings.yaml`,
`policies/tools/tool-policy.yaml`, a Helm chart under `gitops/charts/`, an
ArgoCD Application pair under `gitops/apps/`, and the CI/build wiring
(`.github/workflows/build-publish.yml`, `ansible/roles/mcp_build/`,
`.github/workflows/lint.yml`, `platform/security/
check_workload_hardening.py`). Nothing about that is architecturally
wrong - ADR-0116 already decouples logical capability from physical
backend - but at catalog scale (many integrations planned informally
beyond today's three) the manual-registration friction and the risk of a
silently divergent copy (missing gateway-token middleware, a chart never
added to the hardening check) become the real bottleneck, not the
architecture. This isn't hypothetical: the audit this ADR's own tooling
ran while landing found `mcp-salesforce` already missing from
`check_workload_hardening.py`'s NetworkPolicy coverage list and from
`lint.yml`'s test job, months after `salesforce`'s own tests were
written - exactly the class of gap `check_workload_hardening.py`'s
existing comments already warned about for `confluence`.

## Decision

Add scaffolding and conformance tooling without introducing a shared
Python library between independently deployed containers (each component
keeps its own `.venv`/`requirements.txt` - a shared runtime dependency
would fight that isolation, not help it):

1. **`platform/scaffolding/new_mcp_server.py`** (`make new-mcp-server
   NAME=<name>`) generates `components/mcp-servers/<name>/` (server,
   requirements, Dockerfile, README, protocol test), `gitops/charts/mcp-<name>/`
   and `gitops/apps/mcp-<name>/` from the confluence-shaped template
   (gateway-token middleware, `/healthz`, `TransportSecuritySettings`,
   non-root Dockerfile) with one placeholder tool and a single default
   credential. A server needing more than one credential or a different
   auth mode is hand-edited afterward - this produces a correct starting
   point, not a no-edit final artifact.
2. **`platform/supply-chain/check_mcp_server_conformance.py`**, wired as a
   blocking step in `lint.yml`, discovers every `components/mcp-servers/*/server.py`
   and verifies the mandatory shape (gateway-token middleware, `/healthz`,
   DNS-rebinding protection, an `mcp==` pin, a Dockerfile using the `ARG
   BASE_IMAGE` CVE-patch pattern) and that the server is registered
   everywhere an existing per-component check requires it by name
   (`check_workload_hardening.py`'s chart lists, `lint.yml`'s python test
   job) - the exact two gaps its first real run found for `salesforce`,
   fixed in this same change.
3. **Discovery-driven build matrix**: `.github/workflows/build-publish.yml`
   gained a `discover-mcp-servers` job (globs `components/mcp-servers/*/Dockerfile`)
   feeding a `build-publish-sign-mcp-servers` matrix job, replacing three
   hand-listed entries in the main build matrix - a new MCP server needs
   no CI registration step at all. `ansible/roles/mcp_build/tasks/build.yml`
   got the equivalent `ansible.builtin.find`-driven loop.
   `platform/supply-chain/check_build_matrix.py` was updated to exclude
   `components/mcp-servers/*/Dockerfile` from its static-matrix-orphan
   check and instead verify the discovery job still actually targets that
   directory, so the exclusion can't quietly become a real silent gap.
4. **`backends:` endpoint defaults** in `platform/bindings/tools/tool-bindings.yaml`
   (loaded by `components/mcp-gateway/app/bindings.py`): an optional
   top-level map from backend name to a default `{env, default, path}`,
   used only when a capability entry omits its own `endpoint:`. A
   per-entry `endpoint:` still always wins; every binding written before
   this change is untouched.

## Consequences

The next server (git-forge, ADR-0120) is the first real consumer of all
four - same role Confluence played for ADR-0116's binding registry. Each
later server gains the generated scaffold, the conformance guardrail, and
zero-touch CI build registration; the marginal cost of the 4th, 5th... Nth
integration drops instead of staying constant.

## Security considerations

`check_mcp_server_conformance.py` must stay a blocking CI gate, not
informational - an uncaught missing gateway-token middleware is a silent
ADR-0037 regression, which is exactly the failure mode this tooling
exists to catch before merge rather than after an incident.

## Operational considerations

`check_mcp_server_conformance.py` deliberately does not check
`platform/bindings/tools/tool-bindings.yaml`/`policies/tools/tool-policy.yaml`
registration - a freshly scaffolded server with zero wired capabilities is
a legitimate, expected intermediate state, not a conformance failure.

## Migration / evolution

The informal "~15 integrations eventually" catalog goal that motivated
this ADR is deliberately not given a roadmap version or ADR band here -
the repo's real roadmap (`docs/roadmap/versions.md`) currently ends at
v0.4 plus the separate OKF stream, and `docs/adr/README.md`'s 2026-08-18
banding note already reserves the next free band for "a future platform
v0.5 stream" without committing to its scope yet. Revisit banding once
that catalog's actual scope is clearer; this ADR only ships the tooling,
not a version commitment.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered and Review evidence.

## Related ADRs

- [ADR-0010](0010-introduce-a-central-mcp-gateway.md)
- [ADR-0037](0037-protect-mcp-servers-with-network-and-workload-identity-boundaries.md)
- [ADR-0043](0043-use-standard-mcp-protocol-behind-the-zuno-mcp-gateway.md)
- [ADR-0111](0111-strengthen-secnumcloud-oriented-security-controls.md)
- [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md)
- [ADR-0116](0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md)
- [ADR-0117](0117-implement-confluence-as-the-first-real-external-mcp-integration.md)
- [ADR-0120](0120-implement-a-multi-provider-git-forge-mcp-server-for-github-and-gitlab.md)
- [ADR-0324](0324-reconcile-the-ci-build-inventory-with-the-repository-component-lifecycle.md)
