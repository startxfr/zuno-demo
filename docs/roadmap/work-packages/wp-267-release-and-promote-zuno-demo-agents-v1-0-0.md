# WP-267: Release and promote zuno-demo-agents v1.0.0, platform integration page

- **State:** Done (2026-11-14: release PR #54, v1.0.0 published 07:59 UTC (corp d2e1ae52); copied into the internal Quay; promoted at ed681c6f with the owner's go; `make d2 install mcp` and `unifai`, ai-gateway and mlops rebuilt and signed; golden path 13/13 before and after)
- **ADRs:** [ADR-0615](../../adr/0615-align-the-zuno-okf-profile-with-upstream-okf-0-2-and-freeze-it-as-profile-1-0.md) (clauses 11, 12), [ADR-0580](../../adr/0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md), [ADR-0612](../../adr/0612-serve-every-zuno-image-from-an-internal-red-hat-quay-backed-by-an-s3-bucket.md)
- **Depends on:** WP-263, WP-264, WP-265 (WP-266 or its cut line)
- **Related:** [WP-268](wp-268-refuse-legacy-okf-documents-with-operator-line-0-2.md)
- **Target repository:** this one, plus the release pull request in `startxfr/zuno-demo-agents`
- **Estimated files touched:** `platform/okf/agents.lock` and the generated files (through the promotion pull request); a new `docs/platform/agents-release-integration.md`; `docs/agents/okf-workflow.md`

> Execute this brief as a standalone task. Every step that touches demo333 waits for the owner's go.

## Content

1. **Release.** In zuno-demo-agents, set root `VERSION` to `1.0.0`, then open the pull request from `devel` to `main`.
   The owner approves it. `release.yml` tags `v1.0.0` and `publish.yml` signs it. The release carries the pending
   annotation fix `78b2472`; tell its session before the cut.
2. **Promotion**, each step with the owner's go:
   1. Run `okf-promote.yml` (`workflow_dispatch`, release `v1.0.0`, base `devel`).
   2. Check that the pull request holds the lock and the generated files, then merge it.
   3. Mirror the release with `OKF_MIRROR_TO=<quay route>/zuno make d3 admit agents`.
   4. Run `make d2 install mcp` and `make d2 install unifai`.
   5. Rebuild ai-gateway and mlops, which bake the release.
3. **Docs.** A new `docs/platform/agents-release-integration.md`:
   - what the platform pins, and how a release is promoted, admitted, mirrored and consumed (the okf-fetch init
     containers, the operator through `UnifaiAgentBundle`, the ai-gateway and mlops builds, evaluations and the
     Ansible checks);
   - the generated files;
   - rollback.

   `docs/agents/okf-workflow.md` becomes a pointer to it.

## Proof

- **Before the lock moves.** `cosign verify` passes on the v1.0.0 corp digest (identity `publish.yml@refs/tags/v`).
- **On demo333 after the roll:**
  - both okf-fetch logs say VERIFIED from the mirror;
  - `/okf` holds the `index.md` files;
  - every `UnifaiAgentBundle` is Ready on its new digest, and `status.display` shows the maintainer;
  - the golden path passes;
  - a smoke turn of tekos, arkos and comage passes.
- **Rollback.** v0.14.4 is still in the internal Quay after `prune`.

## Out of scope

- Refusing legacy documents (WP-268).
