# WP-263: zuno-demo OKF readers accept profile 1.0

- **State:** Done (2026-11-14: readers c75e8e4d and 0166cd5c rolled; after the v1.0.0 promotion both okf-fetch VERIFIED, ai-gateway and mlops rebuilt and signed, `make d2 check agents` OVERALL PASS, golden path 13/13)
- **ADRs:** [ADR-0615](../../adr/0615-align-the-zuno-okf-profile-with-upstream-okf-0-2-and-freeze-it-as-profile-1-0.md) (clauses 5, 6, 12), [ADR-0508](../../adr/0508-isolate-okf-parsing-behind-per-component-adaptation-hooks.md)
- **Depends on:** WP-262 (the conformance cases)
- **Related:** [WP-267](wp-267-release-and-promote-zuno-demo-agents-v1-0-0.md)
- **Target repository:** this one
- **Estimated files touched:** about 15: the reader hooks, `okf_narrowing.py`, `ansible/roles/agents/tasks/check.yml`, their tests

> Execute this brief as a standalone task. It must ship and be rebuilt BEFORE `platform/okf/agents.lock` moves to a
> profile 1.0 release. It must not touch `gitops/charts/` (devel auto-syncs on demo333).

## Why

Each of the ten reader hooks accepts exactly `v0.2` and `v0.3` (ADR-0615 F12). mcp-gateway refuses the whole release
when one document fails, which clears every agent. The narrowing gate keys on `== "v0.3"` and would skip profile 1.0
bundles in silence (F11).

## Content

1. **The dispatch table of ADR-0615 clause 5**, implemented in each hook, each keeping its own copy (ADR-0508 clause 4):
   - `platform/supply-chain/admit_okf_bundle.py` (`checked_frontmatter`);
   - `components/mcp-gateway/app/agent_declarations.py`;
   - `components/a2a-gateway/app/agent_declarations.py`;
   - `components/mlops/src/mlops.py` (`_task_system_prompt`);
   - `evaluations/common/okf_release.py`;
   - `platform/docs/check_docs.py` (`_okf_frontmatter`);
   - `ansible/roles/agents/tasks/check.yml`.
2. **`okf_narrowing.py`**: a level function, so that the v0.3 rules apply to profile 1.0.
3. **A cross-hook test** proving that every copy accepts and refuses the same set (from the conformance cases).
4. **Rebuilds**, on the owner's go, with the previous ImageStream tag kept as `:pre-wp263`:
   - mcp-gateway and a2a-gateway (`make d2 build mcp`);
   - mlops (`make d2 build mlops`);
   - ai-gateway (`make d1 build ai-gateway`);
   - supply-chain-signer (`make d1 build supply-chain-signer`).

## Proof

- Every component's unit tests and `evaluations/tests` pass. The conformance tests pass with `ZUNO_OKF_CONFORMANCE_DIR`
  pointed at the WP-262 cases. `check_okf_read_boundary.py` and `check_docs.py` pass.
- `admit_okf_bundle.py admit --dev` passes on a converted `devel-<sha12>` artifact (after WP-265). The diff of
  `generate_stack_config.py --release-dir` holds only the expected changes.
- After the rebuild, with the lock still on v0.14.4: the golden path passes (ADR-0605) and `make d2 check agents`
  passes.

## Out of scope

- Moving the lock (WP-267).
- Refusing legacy documents (WP-268).
