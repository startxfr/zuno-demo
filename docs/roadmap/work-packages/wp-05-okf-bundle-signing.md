# WP-05: OKF bundle signing and validation (promotes ADR-0106)

- **State:** Done (2026-08-22/25 - the operator follow-up this line described was closed by WP-069; superseded by the tracker's own correction. Original note: 2026-08-21 — WP-04 stage 2's real release (run 32273454405) produced real signatures for all 8 agent bundles, but flipping `ZUNO_REQUIRE_SIGNED_BUNDLES` on is blocked by a real distribution gap: the CI job uploads signatures only as an ephemeral GitHub Actions artifact, never copied into the runtime image or mounted into the pod (`ZUNO_OKF_SIGNATURES_DIR` has no writer anywhere in `gitops/`/`ansible/`) - see ADR-0106's 2026-08-21 note. A follow-up WP must build that distribution path before this can safely close; flipping the flag today would crash-loop every agent-runtime pod. 2026-08-14 — repo work merged: sign_okf_bundle.py, validate_okf_bundle.py, agent-runtime registry enforcement + Dockerfile cosign install, CI wiring, ansible check task, full test coverage.)
- **ADRs:** ADR-0106 (Proposed -> To be implemented -> Partially implemented -> Implemented)
- **Depends on:** WP-04 stage 1 (merged)
- **Blocks:** —
- **Estimated files touched:** ~8

> Execute this brief as a standalone task from the repository root. Read the
> referenced ADR sections before editing. If the repository state contradicts
> a step, stop and report instead of improvising.

## Goal

Promote stub ADR-0106 to a full record, then implement signing + validation
for OKF agent bundles (`agents/*/`): bundles are signed in CI, and both the
Day 1 check path and the Agent Runtime registry refuse unsigned or invalid
bundles.

## ADR references

Stub origin (`docs/roadmap/adr-decisions-v0.1.md`): verify signatures and
schema/policy validity before promoting agent definitions.

Related: ADR-0038 (OKF bundle format), ADR-0039 (runtime executes the OKF
contract), ADR-0022 (GitOps-managed definitions), ADR-0115/WP-04 (cosign
tooling precedent). Acceptance criteria: Standard clauses
(docs/adr/README.md#standard-clauses) — includes security-negative tests since
this adds a trust boundary.

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- WP-04 stage 1 merged: `ls platform/supply-chain/` shows the cosign
  verification tooling.
- Read: `agents/tekos/agent.okf.md` and the rest of `agents/tekos/`,
  `ansible/roles/agents/tasks/` (the Day 1 check path),
  `components/agent-runtime/app/` (locate the bundle/agent registry loading),
  `.github/workflows/lint.yml`.

## Step 0 — ADR promotion

1. Create `docs/adr/0106-enforce-okf-bundle-signing-and-validation.md`:

   ```markdown
   # ADR-0106: Enforce OKF bundle signing and validation

   - **Status:** To be implemented
   - **Target:** v0.1
   - **Date:** <today's date>
   - **Decision owners:** Zuno Demo architecture team

   ## Decision

   Promote this decision from a one-line v0.1-roadmap entry
   (`../adr-decisions-v0.1.md`) to a full record, since WP-04's supply-chain
   tooling makes it concretely implementable.

   Sign every OKF agent bundle (the per-agent content under `agents/<agent>/`)
   in CI with keyless Cosign over a canonical bundle digest, and validate
   before any promotion or load: (1) signature and signer identity,
   (2) OKF schema validity, (3) policy validity - declared tools and
   knowledge references must resolve against the platform policy files.
   Both the Day 1 agents check (`ansible/roles/agents`) and the Agent
   Runtime registry startup refuse a bundle that fails any of the three
   checks (fail closed). Signing keys/identity follow ADR-0115's keyless
   GitHub OIDC convention; no key material enters Git.

   See [Standard clauses](README.md#standard-clauses) for Alternatives
   considered, Consequences, Security/Operational considerations,
   Acceptance criteria and Review evidence.

   ## Related ADRs

   - [ADR-0022](../../adr/0022-use-gitops-managed-declarative-agent-tasks-and-policies.md)
   - [ADR-0038](../../adr/0038-use-standards-compliant-okf-v0-2-markdown-bundles.md)
   - [ADR-0039](../../adr/0039-make-agent-runtime-execute-the-okf-agent-contract.md)
   - [ADR-0115](../../adr/0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md)
   ```

2. In `docs/roadmap/adr-decisions-v0.1.md`: KEEP the heading
   `### ADR-0106: Enforce OKF bundle signing and validation`; replace its
   one-line body with:
   `Promoted to a full decision record: see [ADR-0106](../../adr/0106-enforce-okf-bundle-signing-and-validation.md) (WP-05 implementation).`
3. In `docs/adr/README.md`: change the ADR-0106 row link from the
   `../adr-decisions-v0.1.md#adr-0106-...` anchor to
   `0106-enforce-okf-bundle-signing-and-validation.md`; status cell
   `Proposed` → `To be implemented`.
4. `python3 platform/docs/check_docs.py` must exit 0 before continuing.

## Repo changes (step by step)

1. **Canonical digest + signing script:**
   `platform/supply-chain/sign_okf_bundle.py` — computes a deterministic
   digest over an `agents/<agent>/` tree (sorted file list + content hashes)
   and signs/verifies it with cosign (reuse WP-04 stage-1 helpers). Verify
   mode must not require signing credentials.
2. **CI:** add a job step in `.github/workflows/build-publish.yml` signing
   every agent bundle on release, and a verification step in
   `.github/workflows/lint.yml` (`continue-on-error: true` until the first
   real signed bundle exists — same convention as WP-04 stage 1).
3. **Schema/policy validation:** extend the same script (or a sibling
   `validate_okf_bundle.py`) to check OKF structure and that every declared
   tool/knowledge reference resolves against `policies/tools/tool-policy.yaml`
   (and `policies/knowledge/` once WP-20 lands — feature-detect, don't fail
   if absent).
4. **Day 1 check:** wire verification into `ansible/roles/agents`' check
   tasks following that role's existing task style.
5. **Runtime:** in the Agent Runtime registry load path found in
   preconditions, refuse bundles failing validation when a
   `ZUNO_REQUIRE_SIGNED_BUNDLES` setting is enabled (default off until the
   first real signed bundle exists; flipped in post-operator follow-up).
6. **Tests:** tampered bundle → refused; unsigned bundle with enforcement on
   → refused; valid bundle → loads. Security-negative tests are mandatory.

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set.
- Bundle *content* under `agents/` (signing wraps it; it does not modify it).
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04 owns both).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m py_compile platform/supply-chain/sign_okf_bundle.py`
- `python3 -m pytest components/agent-runtime/tests/ -q`
- `ansible-playbook ansible/playbooks/day1_check.yml --syntax-check`
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up (not executable by the model)

1. Operator: after WP-04 stage 2 credentials exist, run the signing job so
   every agent bundle has a real signature.
2. Operator: flip `ZUNO_REQUIRE_SIGNED_BUNDLES` on and make the lint
   verification step blocking; run `make d2 check agents`.

## Status updates (then re-run check_docs.py)

- After repo merge: ADR-0106 body status →
  `Partially implemented (signing/validation tooling and enforcement paths merged; first real signed bundle pending)`;
  index row to match; tracker → `Operator pending`; this file's State.
- After operator steps: ADR-0106 →
  `Implemented - see \`platform/supply-chain/sign_okf_bundle.py\`.`; index row
  `Implemented`; tracker → `Done`; MEMORY.md dated bullet.

## Out of scope / deferred

- Model/adapter artifact signing (WP-34 registry conventions).
- Admission-time enforcement in-cluster (ADR-0111/WP-11 control candidate).
