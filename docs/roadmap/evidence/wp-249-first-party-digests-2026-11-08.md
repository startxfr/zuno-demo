# WP-249 row 4: first-party images pinned to a release and back to `:latest` (2026-11-08)

On 2026-11-12, the user decided to record this existing evidence for row 4 instead of a new run. The cycle ran on
2026-11-08 with the `RENDER_DIGESTS=1` step of the v0.14.5 release, which is the step decision D2 named. No live action
was taken for this record.

## What ran

| Time (CET) | Commit / run | What |
|---|---|---|
| 2026-11-08 17:30 | 06f4794c `chore(release): v0.14.5 ledger entry and first-party digests rendered into the charts (RENDER_DIGESTS=1)` | the ledgered v0.14.5 digests written into the `digest` key of 11 first-party charts (a2a-gateway, ai-gateway, diagram-render, mcp-aap, mcp-confluence, mcp-gateway, mcp-git-forge, mcp-salesforce, mlops, zuno-dify-knowledge, zuno-token-proxy); ArgoCD rolled the Deployments to `repository@sha256:…` with `IfNotPresent` |
| 2026-11-08 17:5x | golden path on devel 460f671a | PASS 14/14 ([demo-day runbook](../../demo/demo-day-2026-11-09.md), row "after v0.14.5 digests + UnifAI 0.1.66 pin") |
| 2026-11-08 21:23 | 3ebe58aa `chore(release): first-party images back to :latest … (render_release_digests.py --clear)` | the 11 charts back to `:latest`; the Deployments rolled again |
| 2026-11-08 21:56 | golden path on devel 6355c092 | PASS 14/14 (same runbook, row "night scope closed (… digests cleared back to :latest …)") |

## What it proves, and its limit

- It proves both moves of the first-party rollback in `docs/demo/rollback.md`: rendering a release's ledgered digests
  into the charts (the move to a pinned version), and `--clear` back to `:latest`. In each direction every first-party
  pod rolled and the golden path passed.
- **Limit:** before the `--clear`, the `:latest` ImageStreamTags in `zuno-ai-build` were retagged to the v0.14.5 digests
  (all 12 compared equal to the ledger), so both directions ran identical bits. The cycle tests the mechanism, not a move
  between two different builds.
- **Rule found since then (2026-11-12):** rendering an older release's digests is only safe for a component whose values
  have not moved since that release. On 2026-11-12, rendering v0.15.0 would have broken the MCP servers, whose shared
  workload token was removed by WP-250 after v0.15.0. A release-wide rollback also restores that release's values: a
  `git revert` of the range, not only the digests.
