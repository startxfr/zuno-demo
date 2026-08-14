# WP-07: rag-ingestion catalog and source completion

- **State:** Repo work merged (2026-08-14 - `components/rag-ingestion/tooling/verify_catalog.py` HTTP-verification tool + tests added; every non-Satellite `redhat[]` entry now carries an explicit `# CONFIRM` marker; Confluence `spaces`/`directories` placeholders marked `# operator-supplied` in `values.yaml` and `values.schema.json` (no real space key invented); `install.yml`'s KFP recurring-run `rescue:` block now names its three UNVERIFIED assumptions individually. ADR-0330 stays Partially implemented - operator follow-up below unchanged.)
- **ADRs:** ADR-0330 (Partially implemented -> Implemented)
- **Depends on:** WP-00 (done)
- **Blocks:** WP-22
- **Estimated files touched:** ~4

> Execute this brief as a standalone task from the repository root. ADR-0330
> is already Partially implemented — most work is done. This WP finishes the
> repo-side preparation and hands a precise verification list to the operator.

## Goal

Close ADR-0330's remaining items: replace demo-placeholder Confluence space
keys/directories with operator-supplied real values (parameterized, not
hard-coded), give every `CONFIRM`-marked `redhat[]` catalog entry a
mechanical verification procedure, and get the KFP recurring-run and DSPA
status assumptions verified on a live cluster.

## ADR references

Primary: [docs/adr/0330-integrate-the-rag-ingestion-pipeline-as-a-day1-component.md](../../adr/0330-integrate-the-rag-ingestion-pipeline-as-a-day1-component.md)
(read the whole "Follow-up implementation (2026-08-12)" section).

Remaining work recorded by the ADR:
- real Confluence space keys and page-tree `directories` (demo placeholders
  remain in `gitops/charts/rag-ingestion/values.yaml`);
- HTTP-verified confirmation of every `CONFIRM`-marked `redhat[]` entry
  (`docs.redhat.com` returned HTTP 403 to the authoring environment);
- the KFP recurring-run activation in
  `ansible/roles/rag_ingestion/tasks/install.yml` is flagged unverified
  against a live cluster (Route-naming assumption, "latest version is
  index 0" assumption, recurring-run payload shape);
- the `DataSciencePipelinesApplication` CR status-condition shape used by
  `make d1 check rag-ingestion` is flagged inline as unconfirmed.

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- Read: `gitops/charts/rag-ingestion/values.yaml` (find the `CONFIRM`
  markers and Confluence placeholders), `gitops/charts/rag-ingestion/values.schema.json`,
  `ansible/roles/rag_ingestion/tasks/install.yml` (the flagged assumptions),
  `components/rag-ingestion/src/rag_ingestion.py` (fetch-redhat stage — how
  `redhat[]` URLs are consumed).

## Repo changes (step by step)

1. **Verification tooling:** add
   `components/rag-ingestion/tooling/verify_catalog.py` that iterates
   `redhat[]` entries in `gitops/charts/rag-ingestion/values.yaml`, performs
   an HTTP HEAD/GET per URL, and reports `OK / REDIRECT(final-url) / FAIL`.
   Output format designed so the operator can paste results back and a model
   can mechanically update the values file (drop `CONFIRM` markers on OK,
   fix redirects, remove/replace FAILs).
2. **Confluence parameters:** confirm the space keys / `directories` values
   are cleanly parameterized in `values.yaml` + `values.schema.json` with an
   explicit `# operator-supplied: replace demo placeholders` comment; do NOT
   invent real space keys.
3. **Assumption surfacing:** in `ansible/roles/rag_ingestion/tasks/install.yml`,
   ensure each of the three flagged KFP assumptions logs an explicit,
   greppable warning when the rescue path triggers (so cluster runs produce
   actionable evidence). Follow the role's existing block/rescue style.

## What NOT to touch

- Decision text of ADR-0330 outside its sanctioned status/follow-up sections.
- The uncommitted ADR-0344 change set if still present in `git status`.
- The eight ingestion CLI stages' logic (done and tested — this WP does not
  refactor them).
- `images.ingestion.tag` / `images.compiler.tag` (WP-04 owns tag pinning).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m py_compile components/rag-ingestion/tooling/verify_catalog.py`
- `python3 -m pytest components/rag-ingestion/ -q` (existing fixture tests still pass)
- `helm lint gitops/charts/rag-ingestion`
- `ansible-playbook ansible/playbooks/day1_install.yml --syntax-check`
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up (not executable by the model)

1. Operator: run `python3 components/rag-ingestion/tooling/verify_catalog.py`
   from a network that can reach `docs.redhat.com`; hand results back for the
   mechanical values update (post-operator follow-up below).
2. Operator: supply the real Confluence space keys and `directories` for the
   four technologies (satellite, openshift, openshift-ai, keycloak) in the
   environment-specific values.
3. Operator: `make d1 install rag-ingestion` + `make d1 check rag-ingestion`
   on a live cluster; confirm or correct the KFP recurring-run Route/version/
   payload assumptions and the DSPA status-condition shape, then report the
   corrections needed (if any) as a follow-up change.

## Post-operator repo follow-up

- Apply the catalog verification results: drop `CONFIRM` markers, fix
  redirected URLs, remove dead entries.
- Apply any KFP/DSPA assumption corrections the cluster run surfaced.

## Status updates (then re-run check_docs.py)

- After repo merge: ADR-0330 stays `Partially implemented`; add a dated note
  to its follow-up section naming the new tooling; tracker →
  `Operator pending`; this file's State.
- After operator steps + follow-up merge: ADR-0330 body status →
  `Implemented - see \`components/rag-ingestion/\`, \`gitops/charts/rag-ingestion/\`.`;
  index row `Implemented`; tracker → `Done`; MEMORY.md dated bullet.

## Out of scope / deferred

- New source adapters (Salesforce/Aramis/SQL-dump) — WP-22 / ADR-0204.
- Per-domain cadence scheduling — WP-22 / ADR-0105.
- Confluence ACL synchronization — WP-25 / ADR-0110.
