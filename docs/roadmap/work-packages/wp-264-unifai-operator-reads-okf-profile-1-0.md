# WP-264: unifai-operator reads OKF profile 1.0 (v0.1.71)

- **State:** Not started
- **ADRs:** [ADR-0615](../../adr/0615-align-the-zuno-okf-profile-with-upstream-okf-0-2-and-freeze-it-as-profile-1-0.md) (clauses 4, 5, 7, 11, 12), [ADR-0564](../../adr/0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md)
- **Depends on:** WP-262 (the frozen schemas)
- **Related:** [WP-267](wp-267-release-and-promote-zuno-demo-agents-v1-0-0.md), [WP-268](wp-268-refuse-legacy-okf-documents-from-2026-12-01.md)
- **Target repository:** `startxfr/UnifAI` (the startx fork, `fork/unifai-operator`). This box cannot push to it, so a
  patch is handed to the fork owner session, which applies it on `devel` with the owner's explicit go.
- **Estimated files touched:** about 25 in the fork: `internal/okf/schema.go`, `internal/okf/schema/`, `internal/okf/bundle.go`, testdata, tests, `hack/sync-okf-schemas.sh`, `docs/okf-agent-bundles.md`, `README.md`

> Execute this brief as a standalone task. The CRD does not change: that keeps an OLM rollback to 0.1.69 possible.

## Why

The operator embeds 13 closed schemas and accepts only `v0.2` and `v0.3`. Its copies have drifted from the agents
repository, and it reads `provenance.maintainer` (ADR-0615 F13). A profile 1.0 bundle would be refused.

## Content

1. Embed the `zuno-okf-profile-1.0-*` schemas and dispatch as in ADR-0615 clause 5, with `v0.2` and `v0.3` still
   accepted.
2. Read `zuno.maintainer` for `status.display`, falling back to `provenance.maintainer`.
3. Add `hack/sync-okf-schemas.sh <agents-ref>`. It copies the profile files and writes `internal/okf/schema/SOURCE`
   (agents commit, sha256 of each file). A test fails on drift. The legacy files stay frozen, and their known
   differences are recorded in `SOURCE`.
4. Testdata: a profile 1.0 tekos fixture. The legacy v0.2 and v0.3 fixtures must still be Valid.
5. `docs/okf-agent-bundles.md`:
   - how the operator pulls, verifies, validates and maps a bundle;
   - the field mapping table, with the fields listed in `status.unmapped`;
   - which profile and schema versions each operator version accepts;
   - the link to the zuno-demo-agents docs.

   Update the operator README's links.
6. Release and pin:
   1. The fork owner applies the patch on `devel`.
   2. The owner runs a canary on `devel-<sha>`.
   3. A manual `cut-release.yml` builds v0.1.71 from the canaried operator digest, with the quay-release approval.
   4. v0.1.71 is copied into the internal Quay (WP-248 rule).
   5. Pin commits: `gitops/charts/unifai/values.yaml` `catalogImage`, `platform/olm/known-good-demo333.yaml` and
      `ansible/clusters/demo333.yml`.

   Steps 4 and 5 each need the owner's go. The pin is based on the 0.1.70 pin of its owner session, and the session
   that edits the unifai `extraEnv` is told first.

## Proof

- `make test` passes (envtest, with an absolute `KUBEBUILDER_ASSETS`). The fork CI passes, including the kind e2e.
- The drift test fails when one byte of an embedded profile schema changes.
- After the pin: every `UnifaiAgentBundle` stays Ready with the same `resolvedDigest`, and the golden path passes.
- The OLM rollback procedure is written down before the pin: delete the CSV and the Subscription, then reinstall with
  `startingCSV` 0.1.69.

## Out of scope

- Refusing legacy documents (WP-268, in the 2026-11-27 weekly release).
