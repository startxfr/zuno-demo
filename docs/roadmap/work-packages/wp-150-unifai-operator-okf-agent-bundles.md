# WP-150: unifai-operator consumes signed OKF agent bundles

- **State:** Not started
- **ADRs:** [ADR-0564](../../adr/0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md), [ADR-0565](../../adr/0565-derive-data-classification-from-okf-and-only-allow-raising-it.md)
- **Depends on:** [WP-146](wp-146-unifai-identity-and-context-header-forwarding.md)
- **Related:** [ADR-0342](../../adr/0342-support-multiple-agent-graph-shapes-in-agent-runtime.md), [ADR-0308](../../adr/0308-expand-agent-lifecycle-management-through-the-aiagent-operator.md), [ADR-0327](../../adr/0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md), [ADR-0509](../../adr/0509-deliver-okf-content-as-mounted-versioned-artifacts.md), [ADR-0510](../../adr/0510-make-the-aiagent-operator-watch-the-zuno-okf-repository.md), [ADR-0021](../../adr/0021-route-models-according-to-c1-c2-c3-classification.md), [ADR-0035](../../adr/0035-prevent-restricted-internal-context-from-reaching-external-models.md), [ADR-0544](../../adr/0544-bound-every-model-call-at-both-ends.md)
- **Target:** v0.11
- **Estimated files touched:** ~25 in `startx-unifai` (new CRD types, controller, `internal/okf/` parser and blueprint mapping, envtest, examples); ~5 in `zuno-demo` (OCI publication in the Day-3 sign chain, a Makefile help line, the signer public key reference).

> OKF stays the source of truth for what an agent is. This WP replaces the
> aiagent-operator's role with a new kind in unifai-operator, and keeps all
> OKF knowledge in one isolated Go package so that the upstream-facing part
> of the operator never learns about it.

## Goal

A `UnifaiAgentBundle` CR naming an OCI artifact by digest makes the operator
pull it, verify its signature, parse `agent.okf.md` and its `tasks/`,
`prompts/`, `tools/`, `rag/`, `policies/`, and emit owned `UnifaiAgent`,
`UnifaiWorkflow` and `UnifaiTemplate` objects, with each task's default
classification injected and only ever raised.

## Steps

Operator work in `/home/cl/ClaudeCode/startx-unifai/fork/unifai-operator`
(fork-only, branch `devel`).

1. **Read before writing.** `api/v1alpha1/{resource_types.go,workflow_types.go,common_types.go}`,
   `internal/controller/{resource_controller.go,workflow_controller.go,template_controller.go,common.go,setup.go}`,
   `internal/unifai/{client.go,refs.go}`. In zuno-demo:
   `agents/tekos/agent.okf.md` (frontmatter `model.preferred_classification`,
   tasks list), `agents/tekos/tasks/*.md`, `platform/okf/schema/`,
   `components/agent-runtime/app/` graph factory (shapes from ADR-0342;
   see `components/agent-runtime/tests/test_graph_factory.py`).

2. **CRD `UnifaiAgentBundle`.** New file `api/v1alpha1/agentbundle_types.go`:
   spec `source.oci.ref` (must contain `@sha256:`; reject tags with a CEL
   rule), `verify` (one of `cosign.publicKeySecretRef` or
   `vaultTransit{address,keyName,authSecretRef}`), optional
   `classificationOverrides` (per task). Status: resolved digest, verified
   (bool + signer), emitted children, conditions. Register it in
   `internal/controller/setup.go`; `make generate manifests`.

3. **`internal/okf/` package (zuno-specific, isolated).** Parser for the
   bundle layout (frontmatter + task files), validation against the OKF
   schema rules you need (keep a copy of the schema version in testdata, do
   not import zuno-demo), and a mapping from each ADR-0342 graph shape to an
   embedded UnifAI blueprint template (Go `embed`). No other package may
   import OKF types except the new controller.

4. **Controller `agentbundle_controller.go`.** Pull with an OCI library
   (oras-go), verify (cosign verify-blob semantics against the key, or a
   Vault Transit verify call), parse, then create/update owned children with
   owner references; delete children that disappear from the bundle. Never
   reconcile an unverified bundle: set a `Verified=False` condition and stop.

5. **Classification (ADR-0565).** Default per agent/task comes from OKF.
   An override (CR field, or a session value at runtime via the WP-146
   `{classification}` placeholder) may only move to a more restrictive level
   (C1 < C2 < C3, C3 = local-only per ADR-0021); the controller rejects a
   lowering with a validation condition, and the emitted workflow inputs and
   LLM `default_headers` carry the effective value as
   `X-Zuno-Data-Classification`.

6. **Tests.** envtest suite in `internal/controller/` (follow
   `suite_test.go`, `objects_test.go`, `fakemas_test.go`): a signed bundle
   reconciles children; a tampered bundle yields `Verified=False` and no
   children; a lowering override is rejected; removing a task deletes its
   workflow. Unit tests for `internal/okf/` with a copy of `agents/tekos/` as
   testdata. Add `examples/agent/agentbundle-tekos.yaml`.

7. **zuno-demo publication.** Extend the Day-3 sign chain
   (`ansible/playbooks/day3_sign.yml`, `make d3 sign agents`) with an OCI
   push of each signed bundle (oras) to a zuno quay.io repository and record
   the resulting digest. Do this after signing, never instead of it (the
   ADR-0544 rebuild-then-sign trap: a bundle rebuilt without `make d3 sign
   agents` fails verification late). Update the help line in `Makefile`.

8. **Operator release.** `make test` (envtest) first, bump `VERSION` in
   `fork/unifai-operator/Makefile`, and coordinate with the startx-unifai
   session before running the release chain from the fork's `MEMORY.md`:
   OLM on demo333 rolls the new operator out to both `unifai-devel` and
   `unifai-olm`, and the new CRD must not disturb them.

## Acceptance

envtest and unit suites green; `examples/agent/agentbundle-tekos.yaml` passes
`kubectl apply --dry-run=server` against an envtest API server; the sign
chain change runs offline with a local key. The live run on demo333 is in
[WP-154](wp-154-tekos-pilot-on-demo333.md).

## Open questions

- Vault Transit verification needs the operator to reach Vault; is a cosign
  public key exported from Transit (`agents/zuno-platform-signer.pub`)
  enough, so the operator never talks to Vault? Prefer that if it holds.
- ADR-0509/0510 assumed the aiagent-operator consumes OKF from a repo; this
  WP replaces that with OCI artifacts. The zuno-okf repository extraction
  stream (ADR-0506) is unaffected but must publish OCI artifacts too.
- Not every OKF field has a UnifAI equivalent (e.g. tool policy
  intersections enforced by mcp-gateway). List the unmapped fields in the
  bundle status rather than dropping them silently.
