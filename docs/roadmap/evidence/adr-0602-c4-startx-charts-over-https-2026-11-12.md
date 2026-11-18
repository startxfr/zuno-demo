# ADR-0602 C4: the startx charts read over HTTPS on demo333 (2026-11-12)

Live switch with the user's explicit go, by session zuno-avancement. The window ran from 04:23 to 04:35 UTC, and
zuno-main and zuno-demo held their live work during it.

## Source side (helm-repository, 2026-11-11)

The helm-repository session published, with the user's approval in that session, its stable, noschema and
release-21 indexes with HTTPS URLs (its commit d883b367f3, `HELM_REPO_BASEURL` set to the S3 REST endpoint).
On the live indexes, stable has 1,542 of 1,542 archive URLs on https and none on http. The archive releases 14 to 20
keep http URLs; zuno does not read them. The startx archives carry their own subcharts (for example,
cluster-certmanager carries its 2), so no nested fetch goes over http.

## Why Chart.yaml names the URL instead of `alias:startx`

A `Chart.lock` digest encodes the URL that the alias resolves to. Both half-switched states were reproduced locally,
and each fails with "the lock file (Chart.lock) is out of sync with the dependencies file":
- an https lock while the `startx` repository is http;
- an http lock while the `startx` repository is https.

With the URL written in `Chart.yaml`, the build works whatever name the repository is registered under, which is how
ArgoCD registers an https dependency.

## Steps

| UTC | Step | Result |
|---|---|---|
| 04:23 | baseline | 116 Applications: 114 Synced/Healthy, and the two known OutOfSync ones (`startx-cluster-auth`, `startx-cluster-infra-config`, not from this change) |
| 04:23-04:24 | push a31f91da, then `make d0 install argocd` | exit 0; both AppProjects admit the http and the https URL |
| 04:25 | push f265b9be | 25 charts name the https URL; locks regenerated (same versions) |
| 04:25-04:28 | hard refresh of the 48 Applications built from those charts | 103 Applications on f265b9be, no ComparisonError, 114 Synced/Healthy |
| 04:28-04:30 | `make d0 install argocd` | exit 0; both AppProjects admit only the https URL; the `startx-helm-repo` Secret and the console `HelmChartRepository` are on https |
| 04:30-04:33 | hard refresh again | the same states as the baseline, Application by Application |
| 04:33-04:34 | `make demo golden-path` | RESULT PASS: 14 moments passed, and the world model is shown as roadmap |

## Checked before the push, as CI does

- `helm dependency build` of every chart with dependencies: no failure.
- `check_app_projects.py --strict-dependencies`: 2,887 passed.
- `check_workload_hardening.py`: PASS.
- `check_docs.py`: PASS.

## Back out

1. Revert f265b9be and push the revert.
2. Run `make d0 install argocd` with a31f91da's AppProjects, which list both URLs.
3. Hard-refresh the Applications.
