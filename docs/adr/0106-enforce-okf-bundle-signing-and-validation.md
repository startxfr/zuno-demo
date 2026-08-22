# ADR-0106: Enforce OKF bundle signing and validation

- **Status:** Partially implemented - signing mechanism superseded by ADR-0420 (2026-08-22, WP-069): `sign_okf_bundle.py` now signs via the in-cluster Vault Transit key instead of keyless GitHub-OIDC/Fulcio/Rekor, and the distribution gap the 2026-08-21 note below describes is closed - the signing Job writes straight to Vault KV, consumed by `gitops/charts/agent-runtime/templates/externalsecret-okf-signatures.yaml`. `ZUNO_REQUIRE_SIGNED_BUNDLES` stays off until an operator runs the signing Job for real and confirms all 8 agents verify - see WP-069's own Operator follow-up.
- **Target:** v0.1
- **Date:** 2026-08-14
- **Decision owners:** Zuno Demo architecture team

## Implementation note (2026-08-22)

WP-069 (ADR-0420) closes the distribution gap the 2026-08-21 note below
describes, but by changing the mechanism rather than building the GitHub-
Actions-artifact distribution path that note called for. Signing now runs
in-cluster (`ansible/tasks/run_okf_signing_job.yml`, the
`supply-chain-signer` image, WP-068's Vault Transit key) and writes
directly to Vault KV (`zuno/okf-signatures`), consumed by a new
`ExternalSecret` in the agent-runtime chart - no GitHub Actions artifact,
no manual "download and commit" step. The signature format changed too:
`{name}.sig` plus one shared `cosign.pub`, not a per-agent `.pem`
certificate (Transit signs with a fixed key, not an ephemeral Fulcio cert).
`ZUNO_REQUIRE_SIGNED_BUNDLES` remains `false` pending the operator running
the signing Job for real and confirming all 8 agents verify (WP-069's
Operator follow-up) - the same discipline the note below already
established, now enforceable because the distribution path is automatic.

## Implementation note (2026-08-21)

WP-04 stage 2's real release run produced real `cosign sign-blob` output
for every one of the 8 `sign-okf-bundles` matrix jobs (tekos, comage,
advantage, finage, arkos, naveo, soursage, cognos) - the "first real
signed bundle" precondition this ADR was waiting on is met.

Attempted the second operator step (flip `ZUNO_REQUIRE_SIGNED_BUNDLES` on)
and found it is not yet safe to do: `components/agent-runtime/app/
registry.py`'s `_verify_signature()` reads `{name}.sig`/`{name}.pem` from
`ZUNO_OKF_SIGNATURES_DIR` (default `/app/okf-signatures`, fail-closed -
`OkfError` if missing), but nothing in this repo ever puts a signature
there. `.github/workflows/build-publish.yml`'s `sign-okf-bundles` job
uploads each agent's signature as a **GitHub Actions build artifact**
(`upload-artifact@v4`) - ephemeral CI storage with no downstream
consumer - and `components/agent-runtime/Dockerfile` only sets the
`ZUNO_OKF_SIGNATURES_DIR` env var default; it never `COPY`s a signature
into the image. No ConfigMap/Secret/init-container mounts them into the
running pod either (confirmed: no reference to `okf-signatures` anywhere
under `gitops/` or `ansible/`). Flipping the flag today would make every
agent-runtime pod fail closed at startup with no signature to verify
against - a self-inflicted outage, not this ADR's completion.

This is genuinely missing repo work, not an operator action: a real
distribution path (e.g. a `download-artifact` + `docker cp`/second build
stage embedding the matching release's signatures into the image, or a
signed-bundle-publishing step writing them to a location the chart can
mount) has to exist before `ZUNO_REQUIRE_SIGNED_BUNDLES` can be turned on
anywhere. Left `false` and this ADR `Partially implemented` pending that
follow-up WP.

## Decision

Promote this decision from a one-line v0.1-roadmap entry
(`0100-v0.1-roadmap.md`) to a full record, since WP-04's supply-chain
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

- [ADR-0022](0022-use-gitops-managed-declarative-agent-tasks-and-policies.md)
- [ADR-0038](0038-use-standards-compliant-okf-v0-2-markdown-bundles.md)
- [ADR-0039](0039-make-agent-runtime-execute-the-okf-agent-contract.md)
- [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md)
