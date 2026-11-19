# WP-308: Replay the demo scenarios as stress drivers

- **State:** Repo work in review (2026-11-19, committed in the `wp306-coder` worktree on branch `wp308-coder`, not pushed); the egress and NetworkPolicy openings and the live proof are the reviewer's, each with the owner's go and a notice to zuno-demo-cluster
- **ADRs:** [ADR-0624](../../adr/0624-drive-the-day3-stresstest-from-scenario-drivers-and-named-profiles.md)
- **Depends on:** [WP-305](wp-305-build-the-stress-runner-core-and-profiles.md), [WP-307](wp-307-launch-the-stress-campaign-as-an-indexed-job.md), [WP-306](wp-306-give-the-stress-runs-their-own-identity-and-budget.md)
- **Related:** WP-309, WP-310, WP-311
- **Target:** v0.17
- **Estimated files touched:** ~16: three driver files, the profiles, the campaign launch task, the namespaces and token-proxy charts, two Ansible roles, the tests

## Goal

The golden-path moments of the demos that can be replayed over in-cluster HTTP run from the stress Job, as stress personas, each as a driver named after its demo (`ansible/demos/<id>`): the same calls and the same verdicts as `evaluations/golden_path_probe.py`, without `oc`.

## Steps

1. **UnifAI and the traces** (`evaluations/stress/driver_unifai.py`, family `unifai` and `guardrails`):
   - `unifai-agents`: one Tekos turn through the UnifAI UI route as the worker's stress persona (`unifai_target.UnifaiTarget`, mounted flat in the Job), the session deleted afterwards;
   - `observability-trace`: the same turn, then the run's trace is found in Tempo (`tempo_run_trace`, judged by `judge_trace`);
   - `guardrails`: the DAN prompt through the ai-gateway with `X-Zuno-Run-Id`, then the `guardrails_observe` span of that run id is read in Tempo and must say `zuno.outcome=detected` (the golden probe greps the gateway logs through `oc`, which a Job cannot). A missing span fails with a message that says the evaluation did not run on that path.
2. **Experiences** (`driver_experiences.py`, family `experiences`): `open-webui`, `open-webui-zuno-code` and `open-webui-zuno-wesh` (Keycloak form sign-in, models list, one chat; the session token is cached ten minutes per persona), `dify` and `kagent` (one answer through each token proxy, which swaps in its client's token; `<NAME>_PROXY_URL` and `<NAME>_PROXY_URL_KEY` override the URL and the inbound key when `inboundAuth` is on).
3. **Network paths** (`driver_network.py`): `blender-3d` and `claude-code-sovereign` replay the two clients' device sign-in (`evaluations/blender/device_login.py`, no human) then `/v1/models` and a chat on the ai-gateway workstation entry, and a `/v1/messages` call on the Praxis workstation entry. A 404 on the models list means the entry is off: the row says `skipped` and passes. `quotas` burns the persona's `stresstest` budget until the first 429 (mutating: the profiles skip it unless `allow_mutating`).
4. **Profiles**: `smoke` adds `unifai` and `guardrails` (nothing they need is missing from the platform) and a 240 s timeout for the UnifAI turns; `standard` and `aggressive` add `experiences`, throttled to one request at a time (they are the real user paths and spend the shared experience budgets, Praxis's for Claude Code) with a 240 s timeout.
5. **Plumbing**: the Job ConfigMap carries `unifai_target.py` and `device_login.py`; the Job gets `CLUSTER_BASE_DOMAIN`, `UNIFAI_URL` and `UNIFAI_VERIFY_TLS`.
6. **Two network openings, off or inert until rolled** (the experience drivers report the connection error until then, which is the honest answer):
   - `namespaces`: the zuno-ai-run EgressFirewall allows the Routes `open-webui`, `ai-gateway` and `praxis`. Each is a widening of the kind the UnifAI Route entry already is: the template's own comment notes that one `*.apps` name admits the router's address. Owner's go;
   - `zuno-token-proxy`: `stressClients.enabled` (default false, render unchanged) admits pods labelled `app.kubernetes.io/name=acceptance-gate` of zuno-ai-run on the proxy port, by namespace and label. The Ansible switch is `zuno_stress_clients_enabled` (dify and kagent roles).

## Not replayed, and why

- **OpenClaw**: the path is the operator's egress proxy inside each persona's pod, which injects the `openclaw-<persona>` token. There is nothing to call from outside; calling the ai-gateway with a persona token would test another path.
- **Lightspeed**: the OLS app server wants an OpenShift user or ServiceAccount token it accepts. The Job's ServiceAccount has not been granted that, and its ingress is unchecked.
- **delegation-approval** (Arkos asks Tekos, the approval is rejected) and **unifai-live-rag** (uploads and deletes library files of a persona): both go through UnifAI's approval and library APIs (`evaluations/arkos/approval_proof.py`, `evaluations/unifai_rag_library.py`) and change a persona's state. They are for WP-310 as mutating drivers, with a dedicated persona.
- **world-model**: no GPU node. The Blender and Claude Code drivers need the workstation entries enabled (both default off).

## Acceptance

Offline, done: `python3 evaluations/tests/test_stress_drivers.py` (27 cases: every driver's request, verdict and row, against `httpx.MockTransport` and fakes for UnifAI, Keycloak, Open WebUI, Tempo and the device flow), `test_stress_runner.py` (42) and `test_stress_campaign_plan.py` (7) still pass, `helm template` of the namespaces and token-proxy charts renders as before by default and with the new entries when switched on, `python3 platform/docs/check_docs.py`.

Live, with the owner's go (each roll announced to zuno-demo-cluster first):

1. `make d3 stresstest PROFILE=smoke`: the `unifai` and `guardrails` rows appear next to the tools and models ones. If `guardrails` fails with "no guardrails_observe span", the evaluation does not run on the direct ai-gateway path for that agent: read its mode in `platform/okf` before changing the driver.
2. The namespaces roll (egress), then `make d3 stresstest PROFILE=standard FAMILIES=experiences DRIVERS=open-webui`.
3. `zuno_stress_clients_enabled: true` and `make d2 install dify kagent`, then the `dify` and `kagent` drivers.
4. The workstation entries (`workstationEntry.enabled`, `praxisWorkstationEntry`) before `blender-3d` and `claude-code-sovereign` mean anything; until then they skip or fail on the connection.

## Open points

- The UnifAI drivers sign in as the worker's persona. A load pool persona (`stress-load-NN`, WP-306) puts the turn under the `loadtest` class once the quota policy defines it; until then they sit in `evaluation`.
- Every experience driver spends a shared experience budget; `max_tokens` counts only what a driver reports, and the UnifAI turns report none. The profiles' iteration counts, not the token cap, bound them.
