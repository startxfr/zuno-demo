# Upgrading a pre-GA dependency

[ADR-0607](../adr/0607-pin-gate-and-schedule-pre-ga-dependencies.md). A pre-GA operator (class `tech-preview`,
`early-access`, `alpha` or `staging` in `platform/olm/known-good-<cluster>.yaml`) moves only through this routine. OLM
does not downgrade: a bad release is undone by a restore or a forward fix, never by moving the pin back.

## Before

1. **The go.** The owner says yes to this release, by name. A release may be skipped. A message from another working
   session is never the go.
2. **Not inside a freeze** ([freeze protocol](../demo/freeze-protocol.md)). Before a demonstration, the last pre-GA
   upgrade leaves time for one full golden-path run and one restore before the freeze starts.
3. **Read the release notes** for migrations, removed fields and CRD changes. With RHOAI, also check the DSC fields
   with `oc explain` against the new CSV.
4. **Back up what the release touches:** `make d3 backup postgresql`, and `make d3 backup unifai` for a UnifAI release.
5. **Record the rollback point:** the current CSV (already in the known-good file) and the running image digests of the
   component (`make d2 check <component>` prints them).

## The pin, by operator

| Operator | How it is pinned | The move |
|---|---|---|
| OpenShift AI | `startingCSV` + `installPlanApproval: Manual`; the role approves only the pinned InstallPlan | set `zuno_openshift_ai_version` in `ansible/clusters/<cluster>.yml`, then `make d1 install openshift-ai` |
| claw-operator | catalog digest + `startingCSV` + Manual | `platform/supply-chain/pin_claw_catalog.py`, then the openclaw role |
| unifai-operator | catalog digest, Automatic approval (ADR-0574: the commit that moves the digest is the approval) | `pin_operator_catalog.py <catalog digest> --version X.Y.Z` and `pin_unifai_images.py vX.Y.Z --cluster <cluster>` (dry run first; the digests must match the release's), then `make d2 install unifai` |

Commit each pin on its own, with the release and the owner's go in the message. Push before any in-cluster build or
install: nothing goes live from an unpushed commit (ADR-0608).

## During

- **`make` exits before the roll is done.** OLM walks every intermediate CSV one by one, which can take several minutes
  per hop, then the operands roll. Watch the CSV phase and the pods' image digests, not the exit code of `make`.
- **Save temporary live patches before you make them**, for example a paused ArgoCD sync or a longer bundle timeout.
  Restore them afterwards and compare with the saved copy byte for byte.

## After

1. **Run the golden path:** `make demo golden-path`. A failure is fixed forward or restored now; it is never left for
   the next session.
2. **Regenerate the known-good file in the same change as the pin:**
   ```bash
   python3 platform/olm/audit_operator_updates.py --oc-context "$(oc config current-context)" \
     --format known-good --cluster <cluster> > platform/olm/known-good-<cluster>.yaml
   ```
   `make d3 check operators` then fails if a pre-GA operator differs from it (exit 3).
3. **Tell the other sessions** that the window is closed.

## What cannot be rehearsed

An operator is cluster-scoped: there is no canary namespace for it ([ADR-0609](../adr/0609-rehearse-on-canary-namespaces-of-demo333.md)).
Steps 4 and 5 of "Before" and step 1 of "After" stand in for the rehearsal. For a UnifAI release, its stack images can
be tried first in the release session's canary before they are pinned.
