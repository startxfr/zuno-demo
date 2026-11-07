# WP-245: Blender prompt set, golden-path probe and installable add-on

- **State:** Done
- **ADRs:** [ADR-0610](../../adr/0610-generate-blender-objects-as-bpy-scripts-from-a-local-model-through-the-ai-gateway.md)
- **Depends on:** [WP-244](wp-244-blender-workstation-experience-client.md)
- **Related:** [ADR-0605](../../adr/0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md),
  [ADR-0606](../../adr/0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md)
- **Target:** v0.17
- **Estimated files touched:** ~15: `evaluations/blender/`, the golden-path probe and its tests, two new test files,
  the CI workflow, the Keycloak eval personas, the demonstration script, ADR-0610, this brief and the tracker

> Why: ADR-0610 clauses 8 and 9 were open after WP-244, and Blender joined the 2026-11-09 demonstration (user
> decision, 2026-11-07): the stage needs measured prompts, the golden path a Blender moment, and the presenter an
> add-on to install from disk.

## Goal

A non-interactive token path that the workstation entry accepts, a required `blender` golden-path moment, a measured
prompt set whose stage-ready prompts the demonstration uses, and the add-on shipped as a file with its tests.

## Steps

1. **Token path (option A, agreed with zuno-demo-3c).** `evaluations/blender/device_login.py` runs the device flow of
   the public client `blender` as a persona with no human: device authorization, Keycloak's login form, its grant page
   (form actions resolved against the page URL), token polling with its own timeout, then `revoke()` ends the session.
   Nothing secret is printed or put in an exception. New evaluation persona `eval-ai-dev-01` with explicit groups
   (`/ocp-ai-dev`, `/zuno-evaluation`; `evalPersonas` entries accept `groups` instead of `copyOf`). Rejected: a
   confidential password-grant client at the edge (widens it) and reusing `zuno-evaluations` (the C3 floor of client
   `blender` would not be tested).
2. **Add-on as a file.** `evaluations/blender/zuno_3d_generator.py` (one **Cluster domain** field, overrides under
   **Advanced**), `bpy_stub.py` to load it outside Blender, `test_in_blender.py` to replay scripts through **Run** in
   headless Blender with optional Cycles renders, `README.md`.
3. **Golden-path moment `blender`** in `evaluations/golden_path_probe.py` (zuno-demo-59's conditions): optional while
   the HTTPRoute `ai-gateway-workstation` is absent or its lookup cannot be confirmed, required once it has a verdict;
   edge 401/404, device sign-in of `eval-ai-dev-01` (a persona that cannot sign in yet is a named, non-failing
   state), `/v1/models`, one streamed generation (90 s at most) that passes the static check, the C3 floor line and a
   `gpt-oss-20b` call in the ai-gateway log, session revoked.
4. **Prompt-set measurement** `evaluations/blender/measure_prompts.py` + `prompts.json` (12 prompts, 2 repeats each),
   results in `evaluations/blender/results/`.
5. **Tests in CI:** `evaluations/tests/test_blender_addon.py`, `evaluations/tests/test_blender_measure.py`, the
   `Blender` class of `test_golden_path_probe.py`.

## Acceptance checks

- `python3 evaluations/golden_path_probe.py --only blender` passes on demo333.
- The measurement's stage-ready prompts are the ones `docs/demo/blender-3d.md` puts on stage.
- The add-on installs from disk and its operators register in Blender 4.2.3 (headless check).

## Rollback

The probe moment and the measurement are workstation tools; removing `"blender"` from `PROBES` disables the moment.
The persona `eval-ai-dev-01` is removed from `evalPersonas` and deleted in the Keycloak console (the Job never deletes).

## Progress

- 2026-11-07: persona `eval-ai-dev-01` created live by the eval personas Job (`/ocp-ai-dev /zuno-evaluation`).
  First live run of the moment failed on a relative grant-form action (fixed: resolved against the page URL), then
  PASS in 10.1 s. Measurement v1 16/24 (5 stage-ready), v2 system prompt 23/24 (11 stage-ready); the probe prompt is
  the mug (2/2 with both prompts), PASS in 12.9 s. Blender joined the 2026-11-09 demonstration (user decision via
  zuno-demo-59): the moment is required once the entry exists.
