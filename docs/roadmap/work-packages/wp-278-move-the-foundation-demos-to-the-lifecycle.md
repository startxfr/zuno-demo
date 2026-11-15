# WP-278: Move the foundation demos to the lifecycle

- **State:** Operator pending
- **ADRs:** [ADR-0616](../../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md)
- **Depends on:** [WP-273](wp-273-pilot-the-guardrails-demo-on-the-lifecycle.md) and [WP-274](wp-274-pilot-the-unifai-live-rag-demo-on-the-lifecycle.md), and the owner's go at the gate of 2026-11-16
- **Related:** [WP-271](wp-271-scaffold-every-demo-directory-and-the-catalogue-check.md), [WP-281](wp-281-rehearse-every-demo-and-workshop-end-to-end.md)
- **Target:** v0.16
- **Estimated files touched:** ~70: seven pages under `docs/demo/scenarios/foundation/` and their directories

> Why: the foundation demos show the platform's own operations, so several of their steps run `make` verbs on stage; the allowlist and the local execution of ADR-0616 clauses 5 and 12 are proven here.

## Goal

Every demo of this brief is prepared and played through `make demo`, in both versions, with its page saying what is
left to the presenter after each action and step.

## Steps

For each demo below, in the order given:

1. Page: replace `## Before you start` by `## Presenter lifecycle` with its six `###` sections. Move every checklist
   item into the section where the presenter needs it (sign-ins and warm-ups under Start, the probe under Check), and
   write "Nothing to do." where the file leaves nothing to the presenter. Keep the steps' tables unchanged unless a row
   names a command the file now runs for the presenter; then say so in the Do cell.
2. Files under `ansible/demos/<id>/`: fill `status.yml` and `check.yml` from the reads of the page's status banner;
   fill `start.yml` and `stop.yml` when the page asks for a preparation or a clean-up that a script can do; declare
   every changing unit in `demo.yml`; check every step file against its row (reads run, the rest in `not_run`).
3. Rehearse: `make demo rehearse <id> 5` and `make demo rehearse <id> 15`. A demo whose manifest declares a changing
   unit is rehearsed only after the owner's named go for that demo, with `DEMO_CONFIRM=<id>`. Space out the demos that
   run probes, so persona budgets do not reach 429.
4. Attach each rehearsal report to the Result of this brief, and fix the page or the files until it ends with
   `RESULT: PASS` or with failures the page explains.

## The demos

- `aap-audited-operations`: Start launches one read-only check job the same day (changing unit: it creates an AAP job and its pod), as the AAP freeze protocol asks; Check = the AAP CR, its route, the templates, `aap-mcp`.
- `gitops-day0-3`: the steps run `make help` (0:00), `make d0 check argocd` (3:00), `make d3 check operators` (9:00), `make d3 check drift` (10:30) and `make demo` (14:15), through their local playbooks; Check = the Argo CD Applications.
- `image-signing-admission`: `make d2 check supply-chain` writes a Job, so it is a changing unit, not a step read; Check = the Securesign, the policy controller, the ClusterImagePolicies, Quay.
- `observability-trace`: Check = probes `unifai-tekos`, `trace`.
- `okf-signed-agent-release`: the 6:00 row runs `make d3 admit agents` (allowed read, `UPDATE_LOCK` unset); the workstation tools (cosign, oras) are checked by Status.
- `service-mesh-kiali`: Start runs `make demo golden-path` to create traffic for the Kiali graph; Check = Istio, the PeerAuthentications, Kiali.
- `vault-pki`: Check = the Vault pod labels, the ExternalSecrets, the ClusterIssuers and Certificates (no Secret is read).

## Acceptance

- The catalogue test passes with every demo of this brief counted as moved.
- Each demo has a 5-minute and a 15-minute rehearsal report ending with `RESULT: PASS`, or failures the page explains.
- Every "Nothing to do." and "Nothing to run." is deliberate.
