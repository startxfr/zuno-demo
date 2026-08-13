# Platform: supply chain

Software supply chain policy (ADR-0115: "Use immutable and verifiable
software supply chain artifacts").

`check_no_latest_tags.py` is the policy-as-code check that ADR's
Operational considerations ask for ("Add CI checks rejecting `latest` for
deployable component images"): walks every `gitops/charts/*/values.yaml`
looking for an image `tag` set to the literal `latest` (or left empty).
No live cluster or registry needed - pure static YAML inspection, same
style as `platform/security/check_workload_hardening.py`.

```bash
python3 platform/supply-chain/check_no_latest_tags.py
```

**This currently fails, honestly.** 6 charts (`agent-runtime`,
`ai-gateway`, `mcp-gateway`, `mcp-sales-db`, `rag-service`, `tekos`) still
use `tag: latest`, because the CI pipeline that would publish real
immutable tags for them to reference
(`.github/workflows/build-publish.yml`) has never actually run - this
sandbox has no live Quay credentials or a real GitHub Actions environment
to run it in. The check is written to be genuinely CI-usable the moment
that pipeline runs for real and these values get bumped to the tags it
publishes - see `docs/adr/0051-*.md`'s Implementation state for the full
reasoning, and `.github/README.md` for what the workflow itself does.

Wired into `.github/workflows/lint.yml` alongside the other repository
policy-as-code checks (`platform/security/check_workload_hardening.py`,
`platform/api/lint_openapi.py`) - see that workflow.

## check_build_matrix.py

`check_build_matrix.py` is the policy-as-code check ADR-0324 ("Reconcile
the CI build inventory with the repository component lifecycle") asks
for: validates `.github/workflows/build-publish.yml`'s build matrix
against the repository's actual `components/**/Dockerfile` inventory. No
live cluster or registry needed - pure static check, safe to run on every
PR before any build/publish/SBOM/scan/sign step starts.

```bash
python3 platform/supply-chain/check_build_matrix.py
```

Fails if a matrix entry's `dockerfile`/`context` path is missing, its
`name` collides with another entry, or it no longer corresponds to a
tracked first-party Dockerfile (the `postgresql-pgvector` bug this ADR
fixes - Postgres is now a Crunchy PGO-managed operand, not a first-party
built image). Also fails if a first-party `components/**/Dockerfile`
exists with no matrix entry at all.

Wired into `.github/workflows/lint.yml`'s `policy-as-code` job as a hard
gate (not `continue-on-error`, unlike `check_no_latest_tags.py` above -
this check has no known-failing gap to carry).
