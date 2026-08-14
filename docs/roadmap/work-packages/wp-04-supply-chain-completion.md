# WP-04: Supply-chain completion (three stages)

- **State:** Not started
- **ADRs:** ADR-0115 (Partially implemented -> Implemented)
- **Depends on:** WP-00 (done)
- **Blocks:** WP-05; also gates the "immutable tags from day one" rule for every later chart
- **Estimated files touched:** stage 1 ~5; stage 3 ~10

> Execute this brief as a standalone task from the repository root. Stages 1
> and 3 are model-executable; stage 2 is the operator's real release run.
> Stage 3 must not start before stage 2 has produced real registry artifacts.

## Goal

Close ADR-0115's five remaining gaps. The ADR itself states gaps 2, 3, 4, 6
all reduce to gap 7: one real, credentialed GitHub Actions + Quay release.
Stage 1 prepares everything that can be authored in advance; stage 2 is the
operator release; stage 3 pins the repo to the real artifacts it produced.

## ADR references

Primary: [docs/adr/0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md](../../adr/0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md)
(read the whole "Implementation state" section — it is the authoritative gap list).

Completion criteria (verbatim from the ADR):

> - ADR-0324 removes stale/non-buildable entries and the build inventory has a mandatory path-validation gate;
> - every deployable first-party image is published with a SHA/semantic immutable reference and chart values no longer contain `latest`;
> - `check_no_latest_tags.py` is blocking in CI;
> - release GitOps manifests use a reviewed tag/commit and preferably image digests;
> - first-party Dockerfile base images are version/digest pinned according to the release policy;
> - signature verification is exercised as part of trusted promotion/deployment;
> - at least one real release proves source -> build -> SBOM -> scan -> signature -> immutable GitOps reference -> deployment traceability.

The first and fifth bullets are already closed (gaps 1 and 5 in the ADR).

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- `python3 platform/supply-chain/check_no_latest_tags.py` currently FAILS
  listing 8 fields across 7 charts (`agent-runtime`, `ai-gateway`,
  `mcp-gateway`, `mcp-sales-db`, `rag-service`, `tekos` `image.tag`;
  `rag-ingestion` `images.ingestion.tag` + `images.compiler.tag`) — confirm
  the current list before editing; it may have grown (e.g. `mcp-confluence`
  from WP-02).
- Read: `RELEASING.md`, `.github/workflows/build-publish.yml`,
  `.github/workflows/lint.yml`.

## Stage 1 — repo changes executable now

1. **Signature-verification gate:** add
   `platform/supply-chain/verify_signatures.py` (or extend the existing
   check family) that, given a chart values file, runs
   `cosign verify` against the expected GitHub OIDC identity for every
   first-party image reference, and document in `RELEASING.md` where in the
   promotion flow it must run. In CI it can only be a dry-run until stage 2;
   wire it into `lint.yml` with `continue-on-error: true` and a comment
   `# flips to blocking with ADR-0115 stage 3`.
2. **Release-pinning helper:** add
   `platform/supply-chain/pin_release.py` that takes a release tag/digest
   manifest (produced by stage 2) and rewrites the chart values tag fields
   listed by `check_no_latest_tags.py` — so stage 3 is mechanical.
3. **RELEASING.md:** update the runbook with the exact stage 2 → stage 3
   sequence, including the digest manifest format `pin_release.py` expects.

## Stage 2 — operator release (not executable by the model)

1. Operator: configure real Quay + GitHub Actions credentials/secrets.
2. Operator: run `.github/workflows/build-publish.yml` end to end on a
   reviewed revision: build, SHA tags, SBOM, Trivy scan, keyless Cosign
   signing, SBOM attestation — discharging the ADR's final completion bullet.
3. Operator: hand back the release manifest (image → immutable tag + digest,
   plus the reviewed Git tag) for stage 3.

## Stage 3 — repo changes after the release exists

1. Run `platform/supply-chain/pin_release.py` with the operator's manifest;
   verify `python3 platform/supply-chain/check_no_latest_tags.py` now passes.
2. Flip `continue-on-error: true` → remove it (blocking) for
   `check_no_latest_tags.py` **and** the stage-1 signature verification in
   `.github/workflows/lint.yml`.
3. Retarget production-like `gitops/apps/*` Applications from
   `targetRevision: main` to the reviewed release tag (list every file you
   change in the PR description).
4. From this point on, **every new chart in later WPs ships with an
   immutable tag from day one** — record this rule in `RELEASING.md`.

## What NOT to touch

- Decision text of any existing ADR (the ADR-0115 gap list is the sanctioned
  mutable section — update it with dated strikethrough notes, mirroring how
  gaps 1 and 5 were closed).
- The uncommitted ADR-0344 change set if still present in `git status`.
- Do not write placeholder/fake tags — the ADR explicitly forbids it ("the
  honest fix is a real release, not a placeholder SHA").

## Acceptance checks

Stage 1: `python3 -m py_compile platform/supply-chain/*.py`;
`python3 platform/docs/check_docs.py` PASS; lint.yml still green.
Stage 3: `python3 platform/supply-chain/check_no_latest_tags.py` exit 0;
`grep -rn "targetRevision: main" gitops/apps/` returns only apps deliberately
left on main (list them in the PR); `python3 platform/docs/check_docs.py` PASS.

## Status updates (then re-run check_docs.py)

- After stage 1 merge: update the ADR-0115 gap list in place (dated note on
  gap 6 preparation); status stays `Partially implemented`; tracker →
  `Operator pending`.
- After stage 3 merge: ADR-0115 body `- **Status:**` →
  `Implemented - see \`.github/workflows/build-publish.yml\`, \`platform/supply-chain/\`.`
  and strike through gaps 2, 3, 4, 6, 7 with dated notes; index row →
  `Implemented`; tracker → `Done`; MEMORY.md dated bullet.

## Out of scope / deferred

- OKF bundle signing (WP-05 / ADR-0106 — depends on stage 1's cosign tooling).
- Admission-controller signature enforcement in-cluster (operator hardening,
  may be recorded as an ADR-0111/WP-11 control).
