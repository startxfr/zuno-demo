# WP-160: Admit the corp OKF release in zuno-demo

- **State:** Done (2026-10-23)
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

## Progress (2026-10-23)

Built, not yet run against a release (none is published: the first,
v0.1.1, waits for its merge in zuno-demo-agents):

- `platform/okf/sigstore/trusted_root.json` (the public Sigstore root, from
  TUF) and `identity.yaml` (issuer, release and dev subjects, attestation
  type, corp repository, Rekor and CT log).
- `platform/supply-chain/admit_okf_bundle.py`: `verify`, `extract`,
  `validate`, `diff`, `latest`, `admit`, with 14 unit tests. Verification is
  offline: cosign 2.4 has no `--trusted-root`, so the script derives the
  Fulcio chain, Rekor key and CT key from `trusted_root.json` and runs
  `cosign verify --offline` with an empty HOME (no TUF cache). Proven on the
  published devel artifacts: accepted with the dev identity, refused with
  the release one; extract + validate pass; a ghost model and an unbound
  tool are refused.
- `platform/okf/agents.lock` (empty until the first admission),
  `make d3 admit agents [RELEASE=vX.Y.Z UPDATE_LOCK=1]`.
- `.github/workflows/okf-promote.yml` (schedule + manual) and the
  `okf-release` job of `lint.yml`.

Open: the user allows GitHub Actions to create pull requests on
zuno-demo; the scheduled run only fires from the default branch (`main`);
first promotion once v0.1.1 is published.


## Goal

`zuno-demo` pins one corp digest, verifies it offline by identity, validates
it against its own contract, and receives every new release as a reviewed
pull request it opened itself.

## Admissions and promotions (2026-10-23)

- **v0.1.1, first admission.** zuno-demo-agents v0.1.0 was tagged but
  never published (nine tags in one push create no push event). `make d3
  admit agents RELEASE=v0.1.1 UPDATE_LOCK=1` verified offline the corp
  artifact and its eight agents against the release identity (publish.yml
  on refs/tags/v0.1.1) and the contract-tests attestations, validated them
  servable and pinned them (925f271b).
- **v0.2.0, first end-to-end promotion.** `okf-promote.yml`, run by hand on
  demo222, verified the release, opened PR #2 (`okf-promote/v0.2.0`) moving
  `agents.lock` and regenerating `stack-config.generated.yaml`, with a
  summary listing the two corp policies v0.2.0 adds; merged. The eight agent
  digests are identical across v0.1.1 and v0.2.0 (reproducible builds).
- **Default branch.** GitHub lists only workflows present on the default
  branch, so a copy of `okf-promote.yml` without `schedule` was merged into
  main (PR #1). The schedule is back once demo222 reaches main: the
  workflow now checks out and promotes a deployment branch (the `base`
  input, else the `OKF_PROMOTE_BASE` variable, else demo222), never main,
  which no cluster tracks.

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
