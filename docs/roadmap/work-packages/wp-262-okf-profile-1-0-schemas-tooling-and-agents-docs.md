# WP-262: OKF profile 1.0 schemas, tooling and the agents-repo documentation

- **State:** Repo work merged (2026-11-14: zuno-demo-agents PRs #51 and #52 merged into devel; ships in v1.0.0)
- **ADRs:** [ADR-0615](../../adr/0615-align-the-zuno-okf-profile-with-upstream-okf-0-2-and-freeze-it-as-profile-1-0.md) (clauses 1 to 9, 11)
- **Depends on:** none
- **Related:** [WP-263](wp-263-zuno-demo-okf-readers-accept-profile-1-0.md), [WP-264](wp-264-unifai-operator-reads-okf-profile-1-0.md), [WP-265](wp-265-migrate-and-clean-every-okf-bundle-to-profile-1-0.md)
- **Target repository:** `startxfr/zuno-demo-agents` (public, English), by pull request into `devel`
- **Estimated files touched:** about 30: `platform/okf/schema/`, `platform/okf/*.py`, `platform/supply-chain/validate_okf_bundle.py`, `platform/release/okf_release.py`, `conformance/`, `.github/workflows/`, `docs/`

> Execute this brief as a standalone task. Ship the tooling first: no bundle is converted here (that is WP-265).
> Legacy `v0.2` and `v0.3` documents must keep validating.

## Why

The agents repository uses `okf_version` as a Zuno version and labels Zuno fields as OKF core (ADR-0615 F2, F3). Its
tool-note vocabulary is closed (F8). Its narrowing check keys on `== "v0.3"` (F11). And its documentation never explains
the architecture or the upstream specification (F14).

## Content

1. **Schemas.** `build_profile_schemas.py` generates `zuno-okf-profile-1.0-<type>.schema.json` for agent, task,
   prompt, tool, rag, policy, skill, experience-client and index. Each file is self-contained, from the v0.3 schemas
   plus the upstream envelope of ADR-0615 clause 4. A committed `SHA256SUMS` freezes them, and CI fails on any change.
   The new schemas get `$id` URLs under `zuno-demo-agents` and platform-neutral descriptions.
2. **Dispatch.** `validate_okf_schema.py`, `validate_okf_bundle.py` (its three version gates) and
   `conformance/test_ui_display.py` follow the table of clause 5. `check_narrowing.py` uses a level function (clause 6).
3. **Tool vocabulary.** `capability` becomes a pattern. The validator checks it against `policies/tools/tool-policy.yaml`
   and checks `used_by_tasks` in both directions.
4. **New profile 1.0 rules:**
   - one profile per bundle;
   - a prompt for every task;
   - upstream `status` consistent with `zuno.status`;
   - `verified` is a list;
   - `stale_after` past its date gives a warning, never a failure;
   - a platform-neutral lint on published files that refuses `components/`, `evaluations/`, `gitops/`,
     `agent-runtime`, "Agent Runtime" and `MEMORY.md`.
5. **`platform/okf/generate_index.py`** writes and checks each bundle's root `index.md` (upstream §8).
   `okf_release.py` publishes `index.md`, adds the annotation `zuno.okf.profile` and adds `okfProfile` to the corp
   index; `schemaVersion` stays 1.
6. **Conformance cases:**
   - a valid profile 1.0 bundle;
   - a valid mixed bundle;
   - `zuno.profile` missing;
   - `zuno.profile` unsupported;
   - `okf_version` unquoted;
   - a profile 1.0 bundle that widens a corp policy, which must be refused.
7. **Docs** (`docs/`):
   - `architecture.md`: repository, artifacts, consumers, trust chain;
   - `okf-reference.md`, rewritten as the profile 1.0 reference: dispatch table, upstream mapping, deviations table,
     upstream links;
   - `bundle-lifecycle.md`: from writing an agent to it running on a platform, with the legacy-to-profile migration;
   - updates to `README.md`, `RELEASING.md`, `bundle-files.md`, `add-an-agent.md`, `unifaiagentbundle.md` (it links
     to the operator page of WP-264) and `docs/README.md`.

## Proof

- **Release checks.** The six release checks plus `generate_index.py --check` pass on the unconverted tree, with every
  legacy document still valid.
- **Conformance.** Every new conformance case gives the expected result. The narrowing case fails if the level function
  is replaced by `== "v0.3"`.
- **Reproducibility.** Two `okf_release.py build` runs give identical digests.
- **Docs.** Every relative link in `docs/` resolves.

## Lots

| Lot | Content |
|---|---|
| 1 | Schemas, generator, SHA256SUMS, dispatch, narrowing level, conformance cases |
| 2 | Vocabulary, two-way check, profile rules, lint, `generate_index.py`, release tooling, workflows |
| 3 | Documentation |

## Out of scope

- Converting bundles (WP-265).
- Refusing legacy documents (WP-268).
