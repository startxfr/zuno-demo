# WP-059: Wire Tekos and Arkos to git-forge, public/private split

- **State:** Done (2026-08-20)
- **ADRs:** ADR-0121 (To be implemented -> Implemented)
- **Depends on:** WP-058 (merged)
- **Blocks:** none
- **Estimated files touched:** ~13

> Execute this brief as a standalone task from the repository root. Read the
> referenced ADR sections before editing. If the repository state contradicts
> a step, stop and report instead of improvising.

## Goal

Give Tekos read-only access to public GitHub/GitLab repositories, and give
Arkos create/read/write access with commits restricted to public repos and
private reads restricted to GitLab only - the first two real consumers of
`components/mcp-servers/git-forge` (ADR-0120).

## ADR references

Primary: [docs/adr/0121-restrict-git-forge-write-and-private-access-by-visibility.md](../../adr/0121-restrict-git-forge-write-and-private-access-by-visibility.md)

Acceptance criteria: two new GitLab-only capabilities
(`git.repository.private.read`/`.list`) exist and refuse `provider="github"`;
`read_repository_content`/`list_repositories`/`write_file` refuse or filter
private content on either provider, unconditionally; Tekos's task declares
only the two public read/list capabilities; Arkos's task declares all six
(public read/list, private read/list, write, create); generated
authorization matrices and Arkos's deployment snapshot match.

## Preconditions (verify before starting)

- WP-058 merged: `test -f components/mcp-servers/git-forge/server.py`.
- `python3 platform/docs/check_docs.py` exits with only the pre-existing
  ADR-0212/ADR-0214 drift (see WP-057/058).
- Read fully before editing: `components/mcp-servers/git-forge/server.py`,
  `agents/tekos/tasks/answer-technical-question.md`,
  `agents/arkos/tasks/draft-architecture-testimonial.md`,
  `platform/okf/schema/zuno-okf-task-v0.2.schema.json`,
  `gitops/charts/arkos/values.yaml`.

## Repo changes (step by step)

1. **`components/mcp-servers/git-forge/server.py`**: add
   `read_private_repository_content`/`list_private_repositories` (GitLab-only,
   refuse `provider="github"`); tighten `read_repository_content`/
   `list_repositories`/`write_file` to refuse or filter private content on
   both providers, unconditionally (server-enforced, same style as
   `delete_repository`'s refusal).
2. **Tests**: extend `tests/test_mcp_protocol.py` with the two new tools'
   round-trips, GitHub-refusal tests for both, and private-content-refused
   tests for the three tightened tools on both providers.
3. **Bindings + policy**: two new entries in
   `platform/bindings/tools/tool-bindings.yaml` (`backend: git-forge`,
   inheriting the existing `backends:` default) and
   `policies/tools/tool-policy.yaml` (same `allowed_groups`/
   `min_classification` as the existing six).
4. **OKF wiring**: add capabilities to `agents/tekos/tasks/
   answer-technical-question.md` and `agents/arkos/tasks/
   draft-architecture-testimonial.md`'s `allowed_tools`; mirror Arkos's list
   in `gitops/charts/arkos/values.yaml`'s `toolCapabilities:`; add the six
   newly-used IDs to both OKF schema enums
   (`zuno-okf-{task,tool}-v0.2.schema.json`).
5. **Regenerate**: `python3 platform/okf/generate_authorization_matrix.py
   tekos arkos` and `python3 platform/okf/generate_deployment_snapshot.py`
   (the latter touches every agent with a deployment snapshot - revert any
   file outside `agents/arkos/deployment/` it regenerates unless that drift
   is independently real and in scope, per step 6).
6. **Do NOT fix unrelated drift found along the way**: this run also
   regenerated `agents/{advantage,comage,finage}/deployment/manifest-summary.md`
   (pre-existing image-tag drift, unrelated to git-forge) - reverted, left
   untouched, same as WP-057/058's ADR-0212/ADR-0214 note.

## What NOT to touch

- Decision text of any existing ADR.
- `agents/{advantage,comage,finage}/deployment/manifest-summary.md` (see
  step 6 above).
- Any file another concurrent session is actively editing - re-check
  `git status` before staging.

## Acceptance checks (run from repo root; all must pass)

- `cd components/mcp-servers/git-forge && .venv/bin/python3 -m py_compile server.py tests/test_mcp_protocol.py && .venv/bin/python3 tests/test_mcp_protocol.py`
  (25 tests, all pass)
- `cd components/mcp-gateway && .venv/bin/python3 tests/test_bindings.py`
- `python3 platform/supply-chain/validate_okf_bundle.py agents/tekos agents/arkos` → `RESULT: PASS`
- `python3 platform/okf/generate_authorization_matrix.py --check --all` → `RESULT: PASS`
- `python3 platform/okf/generate_deployment_snapshot.py --check` → only the
  pre-existing advantage/comage/finage drift noted above, nothing new
- `helm lint gitops/charts/arkos`
- `python3 platform/docs/check_docs.py` → only the pre-existing ADR-0212/
  ADR-0214 drift

## Operator / human follow-up

None specific to this WP. Live end-to-end verification against real
GitHub/GitLab (both agents actually calling through the gateway) rides on
WP-058's own still-open operator step (PAT provisioning) - this WP only
makes the capabilities reachable by declaration; it doesn't re-verify the
live call path WP-058 already covers.

## Status updates (then re-run check_docs.py)

- `docs/adr/0121-restrict-git-forge-write-and-private-access-by-visibility.md`:
  already `Implemented` in this change (repo-provable).
- `docs/adr/README.md`: ADR-0121 row → `Implemented` (already done).
- `docs/roadmap/v0.1-v0.3-implementation-roadmap.md`: WP-059 tracker row →
  `Done`.
- `MEMORY.md`: one dated bullet describing the Tekos/Arkos wiring and the
  public/private split as implemented state.

## Out of scope / deferred

- A third agent adopting `git.*` capabilities.
- Any change to `create_repository`'s visibility handling (unrestricted by
  design, per ADR-0121).
- Fixing the pre-existing advantage/comage/finage deployment-snapshot
  drift (unrelated).
