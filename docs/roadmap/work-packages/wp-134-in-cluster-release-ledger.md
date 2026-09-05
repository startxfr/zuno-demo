# WP-134: In-cluster release ledger (promotes ADR-0549)

- **State:** Done (2026-09-05 - live-verified: `make d3 release TAG=v0.2.0`
  built, RHTAS-signed and ledgered all 14 components end to end;
  `pinned-releases.yaml` gained a real entry (18 pins/1 skipped, every
  digest real and `signed: true`); `:latest` digests and every live
  `zuno-ai-run` pod confirmed untouched; `check_release_ledger.py` and
  `make d2 check supply-chain` both green. Found and fixed a real
  pre-existing bug along the way - `run_image_signing_job.yml` never set
  `HOME`, unlike `verify_image_signatures.yml`'s identical existing fix
  for the same cosign TUF-cache-init failure - see ADR-0549's own
  Implementation note for the full trace, including the unrelated
  `:latest` signature breakage it also explained and fixed.)
- **ADRs:** ADR-0549 (Implemented)
- **Depends on:** WP-111 (RHTAS signing, Done - reused unchanged)
- **Blocks:** nothing further; closes ADR-0111's last open control-matrix row
- **Estimated files touched:** ~15

> Execute this brief as a standalone task from the repository root.

## Goal

Close ADR-0111's sole remaining SecNumCloud gap ("deployable chart image
tags are immutable") with a mechanism that depends on nothing outside
this cluster: no GitHub Actions, no Quay, no new registry or CI/CD
operator. Reuse, not reinvent - `tag_local_release.py` (build) and RHTAS
signing (`run_image_signing_job.yml`, ADR-0535/WP-111) already exist and
already work; this WP completes and connects them, and adds an
append-only ledger + a static structural-integrity check as the
enforcement mechanism, replacing `check_no_latest_tags.py`'s former role
in `.github/workflows/lint.yml`.

## ADR references

Primary: [docs/adr/0549-close-the-secnumcloud-supply-chain-gap-with-an-in-cluster-release-ledger.md](../../adr/0549-close-the-secnumcloud-supply-chain-gap-with-an-in-cluster-release-ledger.md)
(read the whole Decision section - it is the authoritative mechanism description).

Related: ADR-0111 (superseded by ADR-0549), ADR-0059 (why `:latest` stays
load-bearing for `main`, why this WP never touches `values.yaml`/
`targetRevision`), ADR-0115 (the GitHub Actions/Quay path this WP does
not replace, gets a dated correction note instead), ADR-0535/WP-111 (the
RHTAS signing mechanism reused unchanged).

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- Read: `platform/supply-chain/tag_local_release.py`, `pin_release.py`,
  `ansible/tasks/run_image_signing_job.yml`,
  `ansible/tasks/verify_image_signatures.yml`, `RELEASING.md`.
- Confirm the current `check_no_latest_tags.py` finding count/list before
  editing anything downstream of it - it may have grown further.

## Repo changes (step by step)

1. **`platform/supply-chain/release_ledger.py`** (new): extract
   `pin_release.py`'s ledger read/write logic (`load_ledger`,
   `append_entry`) unchanged in behavior; `pin_release.py` imports it
   instead of defining its own.
2. **`platform/supply-chain/tag_local_release.py`**: fix `COMPONENTS`/
   `NOT_LOCALLY_BUILDABLE` (`mlops` and `diagram-render` both have real
   BuildConfigs, were wrongly excluded); add `--list-components`,
   `--resolve-digests`, `--emit-verify-refs`, `--record-release
   --refs-file <path>` modes.
3. **`platform/supply-chain/check_release_ledger.py`** (new): validates
   `pinned-releases.yaml`'s structural integrity (real digest, `signed:
   true`, consistent tag per entry). Passes on an empty/absent ledger.
4. **`ansible/tasks/run_image_signing_job.yml`**: add optional
   `sign_image_tag` (default `latest`, backward compatible).
5. **`ansible/roles/supply_chain/tasks/check.yml`**: add the
   `check_release_ledger.py` task after the existing signature-verification
   include.
6. **`ansible/playbooks/day3_release.yml`** (new): build (step 2's
   `--apply`) -> sign (loop over `run_image_signing_job.yml`) -> resolve
   digests -> independent verify pass -> record (step 2's
   `--record-release`) -> self-check (`check_release_ledger.py`).
7. **`Makefile`**: new `release` Day 3 verb, `DAY3_RELEASE_COMPONENTS :=
   supply-chain`, `TAG=<tag>` required (no default, unlike `AGENT=` for
   `run`).
8. **`ansible/roles/aap_config/defaults/main.yml`** +
   **`gitops/charts/aap-config/values.yaml`**: new `zuno-day3-release`
   Job Template (gated, `zuno-aap-installer` credential, EE-routed - it
   shells out to `oc`/`python3` directly), mirroring `zuno-day3-run`.
9. **`.github/workflows/lint.yml`**: remove the `check_no_latest_tags.py`
   step - zero GitHub Actions dependency for this compliance story.
10. **`platform/supply-chain/check_no_latest_tags.py`**: dated note only
    (kept, unchanged logic, no longer wired anywhere - see its own note
    for why).
11. **`RELEASING.md`**: document the third path (named in-cluster
    releases) alongside the existing two.
12. **`platform/supply-chain/README.md`** /
    **`ansible/roles/supply_chain/README.md`**: describe the new flow.
13. **`docs/security/secnumcloud-controls.md`**: row 23 (signing
    mechanism text was stale, still said Vault Transit - fix to RHTAS/
    WP-111); row 24 (`enforced-in-cluster`, new mechanism description).
14. **`docs/adr/0111-...md`**, **`docs/adr/0115-...md`**,
    **`docs/roadmap/work-packages/wp-04-...md`**,
    **`docs/roadmap/work-packages/wp-11-...md`**,
    **`docs/adr/README.md`**, **`docs/roadmap/versions.md`**: dated
    notes/index updates pointing at ADR-0549/WP-134.

## What NOT to touch

- Any `gitops/charts/*/values.yaml` `tag:` field, any
  `gitops/apps/*/targetRevision` - `main` stays on `:latest`/`main`
  permanently, by design (ADR-0059, ADR-0549's Decision).
- Decision text of any existing ADR/WP - dated notes only.
- `pin_release.py`'s behavior (only its ledger-writing internals move to
  `release_ledger.py`) - it stays available for ADR-0353's still-unwritten
  external-registry scenario.
- `rag-ingestion`'s `images.compiler.tag` - stays a permanent, documented
  `skipped` entry; do not build it a BuildConfig as part of this WP.

## Acceptance checks

Repo-only: `python3 -m py_compile platform/supply-chain/*.py`;
`python3 platform/supply-chain/check_release_ledger.py` PASS against the
existing ledger; `python3 platform/docs/check_docs.py` PASS; `helm lint`
on any touched chart; `ansible-playbook --syntax-check
ansible/playbooks/day3_release.yml`.

## Operator / human follow-up (done, 2026-09-05)

1. ~~Operator: `git tag <tag> && git push origin <tag>`, then `make d3
   release TAG=<tag>` against the live cluster.~~ Done:
   `v0.2.0` tagged/pushed, `make d3 release TAG=v0.2.0` run (two prior
   attempts failed - a real pre-existing HOME bug, then a Jinja syntax
   slip in this WP's own fix - both fixed before the successful run;
   see ADR-0549's Implementation note).
2. ~~Verify...~~ Done: all 14 `ImageStreamTag`s exist at `:v0.2.0`;
   `:latest` digests and every live `zuno-ai-run` pod confirmed
   untouched; ledger entry has 18 real, `signed: true` pins (1
   documented skip); `check_release_ledger.py` PASS on it specifically;
   `make d2 check supply-chain` green (also required re-signing the 14
   `:latest` images, whose signatures had independently broken during
   the same pre-fix bug window - see the ADR's note).
3. ~~Once verified: ADR-0549 Status -> Implemented...~~ Done: ADR-0549
   `Implemented`; ADR-0111 already `Superseded by ADR-0549` (Retired
   table); this WP's tracker -> `Done`; MEMORY.md dated bullet below.

## Out of scope / deferred

- Activating the Sigstore Policy Controller admission gate
  (`gitops/charts/rhtas-config/`, dormant since ADR-0535) - a natural
  future consumer of this ledger's digests, deliberately left to a later
  ADR.
- Building a BuildConfig for `rag-pipeline-compiler`
  (`rag-ingestion`'s `images.compiler.tag`) - stays a documented,
  permanent gap; whether the image is genuinely dead code is a separate,
  unstarted follow-up.
- ADR-0353 (external-registry/Quay cutover, not yet written) - unrelated
  to this WP; `pin_release.py` stays available, unchanged, for that day.
