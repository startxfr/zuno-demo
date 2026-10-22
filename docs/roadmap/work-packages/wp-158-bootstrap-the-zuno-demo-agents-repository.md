# WP-158: Bootstrap the zuno-demo-agents repository

- **State:** Not started
- **ADRs:** [ADR-0576](../../adr/0576-extract-agent-definitions-and-corp-policies-into-the-zuno-demo-agents-repository.md)
- **Depends on:** none
- **Related:** [ADR-0504](../../adr/0504-define-the-agent-tests-directory-structure-and-promotion-gate.md), [ADR-0513](../../adr/0513-give-okf-rag-tools-and-policies-directories-a-real-schema.md), [WP-159](wp-159-publish-and-sign-okf-releases-from-zuno-demo-agents.md), [WP-165](wp-165-cut-over-and-remove-agents-from-zuno-demo.md)
- **Target:** v0.12
- **Estimated files touched:** the new repository (history of `agents/`, five policy files, six schemas, five scripts); ~6 in `zuno-demo` (`platform/okf/export_platform_contract.py`, the frozen-mirror check, `lint.yml`).

> Mirror first, cut over last. From this WP's merge until WP-165,
> `zuno-demo-agents` is where agents are edited and `zuno-demo`'s copy is a
> frozen mirror checked by CI. Never edit the same content in both.

## Goal

`startxfr/zuno-demo-agents` exists, public, with the history of every moved
path, branch and tag protection, CODEOWNERS, and a self-contained CI that is
green without any checkout of `zuno-demo`. `zuno-demo` exports the
`platform-contract.json` the new CI validates against.

## Steps

1. **User actions first (blocking).** Ask the user to create
   `startxfr/zuno-demo-agents` (public), protect `main` (required review,
   no force push), protect tags `v*` and `*-v*` (maintainers only), and
   create the quay.io namespace `zuno` repositories `okf-corp` and
   `okf-<agent>` (public) with a robot account. Do not run `gh repo create`
   or push without that confirmation.

2. **Contract export in `zuno-demo`.** Write
   `platform/okf/export_platform_contract.py` producing
   `platform/okf/platform-contract.json`: model roles from
   `platform/ai-gateway/provider-routing.yaml` (with `eligible_for`), tool
   capabilities from `platform/bindings/tools/tool-bindings.yaml`, knowledge
   domains served, classification levels from
   `policies/data-classification/classification.yaml`. Add `--check` to
   `lint.yml`.

3. **History-preserving extraction.** In a scratch clone, `git filter-repo`
   keeping the paths listed in ADR-0576 clause 1. Drop
   `agents/*/deployment/`, `agents/*/keycloak-fragment.json` and
   `agents/zuno-platform-signer.pub` (ADR-0576 clause 3). Add
   `platform-contract.json` (pinned copy), `CODEOWNERS`
   (`policies/` and `agents/*/agent.okf.md` to agent and policy owners),
   `README.md` and `LICENSE` (same as `zuno-demo`).

4. **Make the tooling self-contained.** `generate_authorization_matrix.py`
   reads model roles from the contract instead of `provider-routing.yaml`;
   `validate_okf_bundle.py` resolves tools and domains against the moved
   policies plus the contract. Remove any `REPO_ROOT` assumption that
   reaches outside the new tree.

5. **CI (`.github/workflows/ci.yml`).** Schema validation, bundle
   validation, `run_agent_contract_tests.py`, `generate_authorization_matrix.py
   --check --all`, `validate_quota_policy.py`, gitleaks. Pin action versions
   by digest.

6. **Frozen mirror in `zuno-demo`.** A `lint.yml` step compares `agents/`
   and the moved policy files with the tip of `zuno-demo-agents` `main` (until
   WP-160 lands, then with the admitted release) and fails on divergence.

## Acceptance

The new repository's CI is green on `main`; `git log --follow` on a moved
file shows its pre-extraction history; `zuno-demo`'s `lint.yml` runs the
contract export check and the mirror check; `python3
platform/docs/check_docs.py` is green.

## Open questions

- Are `evaluations/` scenarios needed by the contract suites? If a suite
  imports from `evaluations/`, copy the fixture rather than move the
  directory (ADR-0576 keeps `evaluations/` in `zuno-demo`).
- Which people own CODEOWNERS entries beyond the user?
