# WP-140: ADR-0517 demo333 redeploy execution

- **State:** Done (2026-09-08 - full redeploy executed and all acceptance
  gates green on `demo333`)
- **ADRs:** ADR-0517
- **Depends on:** WP-130, WP-131, WP-132 (portability prep, all Done)
- **Related:** ADR-0546, ADR-0547
- **Target:** v0.8

## Goal

Execute the actual from-scratch redeploy ADR-0517 exists to prove is
possible: provision `demo333`, run `make day0/day1/day2 install` and
`make d3 sign/backup/restore` using only the existing entry points, and
pass `make d0/d1/d2/d3 check` plus `make d3 test all` at a rate comparable
to `demo222`. WP-130/131/132 made the automation cluster-agnostic by
construction; this WP is the proof run itself.

## Outcome

Provisioned in `eu-central-1` after a region pivot from `eu-west-1` (the
`g7e` GPU instance type does not exist there). Full redeploy completed
2026-09-06 through 2026-09-08 across four working sessions (one overnight
cluster stop between Day 1 and Day 2). Final state: `make d0/d1/d2/d3 check`
all pass, `make d3 test all` 15/15, `make d3 sign/backup/restore
postgresql` all green. `demo222` was left untouched throughout - no
`oc`/Vault/S3/Route53 mutation against it during the run, and S3 bucket
isolation (region/tags/no cross-policy) re-verified clean at closure.

**40 manual interventions logged and closed** during the run, none left as
an unresolved `kubectl`/`oc` patch. The full findings log (Symptom →
Resolution, one entry per intervention, with commit references) lives in
[ADR-0517's own Implementation notes](../../adr/0517-redeploy-the-full-platform-from-scratch-on-a-new-demo333-cluster.md#implementation-notes)
rather than duplicated here, per the ADR's own Decision clause 3. In
summary, the interventions split roughly into three classes:

1. **Genuine environment-specific literals** WP-118's static audit had
   already found and fixed the *mechanism* for (LimitRange sizing, health
   checks, sync-wave ordering, a stale `confidential.yml` copy) - these are
   the kind of thing the audit anticipated, just not exhaustively
   enumerable without a real run.
2. **First-real-run-under-AAP gaps**: RBAC (`zuno-aap-installer`/
   `zuno-cluster-reader` missing apiGroups or Secret grants),
   NetworkPolicy (`allowApiServerWebhooks`, cross-namespace direct-to-
   primary allowlists), and orphaned code paths (`rhtas_config` never
   wired into any playbook since it was written) - every one of these is a
   path `demo222` never exercised through this repo's current AAP-launch
   automation, so nothing short of a genuine from-scratch run under AAP
   could have surfaced them. This is the single largest class by count.
3. **Code bugs proper**: the `resolve_backup_s3_creds.yml` chain (three
   separate bugs across its fallback path), a couple of Jinja/YAML slips,
   an inert annotation-based nudge mechanism.

## Why this matters beyond `demo333` itself

Every RBAC/NetworkPolicy/wiring gap closed here also protects the *next*
fresh-cluster deploy - and, per ADR-0547's own thesis, these were exactly
the class of defect a static audit structurally cannot see (a cluster-only
grant that was simply never requested is invisible to `grep`). WP-140
is therefore also the first real evidence that ADR-0547's parameterization
holds under a full AAP-driven run, not just a design read.

## Status updates

- **2026-09-08 — Done.** All acceptance gates green, findings log complete
  in ADR-0517, `demo222` isolation re-verified. Per the five-copy rule:
  ADR-0517 body, `docs/adr/README.md`, this brief and its tracker row, and
  `MEMORY.md` move together with this closure.
