# Release sequence on demo333

The order of operations for a release that moves the agents, the UnifAI operator or both, with what each step needs and how to roll it back. It
complements [the OKF workflow](../agents/okf-workflow.md) (what an agents release contains) with the live steps. Every step that changes the cluster
needs the go of the person who owns it; a peer session's relayed "go" is not one.

## A. Prepare the agents release (`zuno-demo-agents`, no cluster effect)

1. On `devel`, bump the root `VERSION` and the `VERSION` of each changed agent by hand, then run `python3 platform/release/okf_release.py check-versions` (in the `zuno-demo-agents` checkout).
2. Open the pull request `devel` to `main`. Merging it is the release: `publish.yml` signs the artifacts keyless. The tags (`vX.Y.Z` and one per agent) are
   cut by the release owner. When `devel` has no commit that `main` lacks, there is nothing to release.

## B. UnifAI operator (when the release needs a new operator)

3. The operator owner publishes it (canary, tag, quay release) and sends the digests (operator, bundle, catalog, rag image), cross-checked with `cosign`.
   Pin nothing before they arrive.
4. In `zuno-demo`, from a worktree on `origin/devel` with `ansible/confidential.yml` linked in: `python3 platform/supply-chain/pin_operator_catalog.py` with the digests,
   then `make d2 install unifai`. Tell the other sessions first. Rollback: pin the previous catalog.
5. Rerun the delegation scenario of the evaluations (Arkos scenario 21, with `TEMPO_URL` set) and check that the workers of the Arkos plan have no path to the
   finalizer.

## C. Admit the agents release and repin the bundles

6. `make d3 admit agents RELEASE=vX.Y.Z UPDATE_LOCK=1`, then `python3 platform/okf/generate_stack_config.py`. Commit `platform/okf/agents.lock`,
   `platform/okf/stack-config.generated.yaml` and `gitops/charts/ai-gateway/files/model-routing.generated.yaml` on `devel` (explicit SHAs, never a sweep of
   other sessions' files). The promotion workflow `okf-promote` ("workflow from: devel") does the same through a pull request.
7. `make d2 install unifai` repins the bundles. The role returns before the bundles change: ArgoCD syncs minutes later, so wait until the digests and the
   `Ready` conditions show the new release. Rollback: repin the previous digests and keep `spec.delegation` and `ceilings.delegationTargets` in the Arkos CR (removing
   them makes the operator refuse the bundle).

## D. Source classification (WP-187), right after the operator pin

8. Set the Confluence sources to C2 and the Red Hat web sources to C1 in `ansible/clusters/demo333.yml`; the next sync re-embeds their pages, so announce it
   to the other sessions first. The mcp-gateway returns the level of the chunk's source and C2 when a chunk has none.

## E. Proofs and records

9. Acceptance scenarios of the changed agents as `eval-consultant-01`, the delegation scenario, the gateway refusal checks, the cost of a delegating turn
   (the ai-gateway counters `zuno_model_tokens_total` and `zuno_model_calls_total`, labelled by `user`), then the evidence files.
10. Set the work packages to Done and the ADRs to Implemented, after the live proof only.

## F. Deliver the repository

11. Open the pull request `devel` to `main` of `zuno-demo`. Recompute its content when you decide, since other sessions keep pushing to `devel`. The
    four ArgoCD Applications that follow `main` (openshift-ai d0/d1, rhtas d0/d1) only resync when the change touches `gitops/` or `ansible/`.

## Test windows

Rolls of the ai-gateway and the mcp-gateway disturb tests running through them. Agree a window with the session that owns the gateways before a live run
(they roll with each build), run tests only inside it, and say when it is over.
