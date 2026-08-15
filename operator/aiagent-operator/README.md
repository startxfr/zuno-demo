# AIAgent Operator

ADR-0327/WP-37: the `zuno.zuno.ai/v1alpha1 AIAgent` CRD contract - a
[Kubebuilder](https://book.kubebuilder.io/) v4 (Go + controller-runtime)
scaffold, the first framework dependency of its kind in this repo (see
`components/agent-bff/`'s deliberately stdlib-only Go for the contrast -
an accepted tradeoff, not an inconsistency). This stage records the
contract only: `api/v1alpha1/aiagent_types.go`, the generated CRD
(`config/crd/bases/`), three sample CRs derived from the real Tekos/Arkos/
Comage charts (`config/samples/`), and a static validation harness
(`validate_contract.py`). No controller/reconciler code exists yet - that
is WP-38, on top of this same scaffold.

See [CONTRACT.md](CONTRACT.md) for the ownership boundary, the "operator
must NOT" list, the status condition types and the incremental migration
path. See `docs/adr/0327-...md` for the full Decision.

## Layout

- `api/v1alpha1/` - `AIAgentSpec`/`AIAgentStatus` Go types (hand-authored)
  plus generated deepcopy code.
- `config/crd/bases/` - the CRD generated from the Go types via
  `make manifests` (`controller-gen`).
- `config/samples/` - one `AIAgent` per real agent, hand-derived
  field-by-field from `gitops/charts/<agent>/values.yaml` and
  `agents/<agent>/agent.okf.md`.
- `config/{default,manager,rbac,prometheus,network-policy}/` - Kubebuilder
  standard kustomize scaffold, not yet wired to a running manager.
- `validate_contract.py` - schema, reject-rule, self-test and chart/OKF
  drift checks; wired into the repo root's `.github/workflows/lint.yml`
  (blocking). Run it directly:

  ```bash
  python3 operator/aiagent-operator/validate_contract.py
  ```

- `cmd/main.go`, `Makefile`, `Dockerfile`, `test/` - Kubebuilder's own
  scaffold for the controller/manager binary WP-38 builds out. This
  component's own `Makefile` is separate from the repo root `Makefile`'s
  `DAY1_*` verbs and gains no entry there until WP-38 produces an image to
  build.

## Regenerating

After editing `api/v1alpha1/aiagent_types.go`:

```bash
cd operator/aiagent-operator
make generate   # deepcopy
make manifests  # config/crd/bases/
python3 validate_contract.py
```
