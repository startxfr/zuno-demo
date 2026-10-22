# WP-160: Admit the corp OKF release in zuno-demo

- **State:** Not started
- **ADRs:** [ADR-0580](../../adr/0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md), [ADR-0578](../../adr/0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md)
- **Depends on:** [WP-159](wp-159-publish-and-sign-okf-releases-from-zuno-demo-agents.md)
- **Related:** [ADR-0576](../../adr/0576-extract-agent-definitions-and-corp-policies-into-the-zuno-demo-agents-repository.md), [WP-161](wp-161-fetch-okf-content-at-pod-start.md), [WP-164](wp-164-generate-stack-configuration-from-the-corp-release.md)
- **Target:** v0.12
- **Estimated files touched:** ~12 in `zuno-demo` — `platform/okf/agents.lock`, `platform/okf/sigstore/{trusted_root.json,identity.yaml}`, `platform/supply-chain/admit_okf_bundle.py` and tests, `.github/workflows/okf-promote.yml`, `Makefile`, `ansible/playbooks/day3_admit.yml`, `lint.yml`.

> The lock is the only place an agents version is named. Everything else
> reads it.

## Note (2026-10-22)

ADR-0580 is amended: `okf-promote.yml` polls the `okf-corp` release tags on
a schedule and on demand instead of reacting to a dispatch, and admission
also checks that every reachable model name of the release's model catalog
is bound in `provider-routing.yaml`. Step 1 drops `identity.yaml`'s
dependency on a dispatch; the rest stands.

## Goal

`zuno-demo` pins one corp digest, verifies it offline by identity, validates
it against its own contract, and receives every new release as a reviewed
pull request it opened itself.

## Steps

1. **Trust material.** Commit `platform/okf/sigstore/trusted_root.json`
   (fetched through TUF by a new `make d3 refresh okf-trust-root` target)
   and `identity.yaml` (issuer and subject regexp of ADR-0578 clause 2).

2. **`admit_okf_bundle.py`.** Subcommands `verify` (corp + each agent,
   signatures and both attestations, offline), `validate` (against
   `platform/okf/platform-contract.json` and ADR-0579 clause 5's narrowing
   rule), `extract <dir>` and `diff <old> <new>` (the semantic diff of
   ADR-0580 clause 2 step 4). Reuse the pull/layer code of
   `publish_okf_bundle.py` and the cosign subprocess pattern of
   `sign_okf_bundle.py`. Tests with a locally signed fixture and a forged
   identity.

3. **`agents.lock` and `make d3 admit agents`.** Wire the verb through
   `ansible/playbooks/day3_admit.yml` (AAP job first, playbook fallback, as
   the Makefile does for `d3 sign agents`). Keep `make d3 sign agents`
   working until WP-165.

4. **`okf-promote.yml`.** On `repository_dispatch: okf-release` and
   `workflow_dispatch`: verify, validate, update the lock, run the generator
   if WP-164 has landed, open a PR labelled `okf-promotion` with the semantic
   diff as body. `lint.yml` runs `admit_okf_bundle.py verify` on the locked
   digest so a hand-edited lock cannot merge unverified.

5. **Switch the frozen-mirror check** (WP-158 step 6) to compare against the
   extracted admitted release.

## Acceptance

A release tagged in `zuno-demo-agents` produces a PR on `zuno-demo` within
minutes, with a readable semantic diff; `make d3 admit agents` passes on the
locked digest and fails on an unsigned digest, on a digest signed from
another repository and on a release that references a tool absent from the
contract; `check_docs.py` green.

## Open questions

- `make` verb naming: `admit` is a new verb in the `d3` tier; check
  `check_docs.py`'s Makefile/role consistency rule and the AAP workflow DAGs
  (`aap-config`) before adding it.
