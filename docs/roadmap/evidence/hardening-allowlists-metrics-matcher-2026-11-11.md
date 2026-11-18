# Allowlists and metrics namespace matcher live on demo333 (2026-11-11)

Live switch of the post-demo hardening item 4 decisions (user decisions of 2026-11-11, recorded in the ADR-0603
amendment of that date), by session zuno-avancement with the user's explicit go. The window ran from 22:34 to 22:45 UTC
and was announced to zuno-main and zuno-demo, who held their own live work.

## Change

Commit 17b2e7c0, applied with `make d2 install mcp` (22:34 to 22:41 UTC, exit 0). The change is values only: no image was
rebuilt.

- **mcp-gateway:** `METRICS_NAMESPACES_BY_GROUP` gives `ocp-ai-ops` the 13 namespaces that mcp-k8s reads, plus
  `nvidia-gpu-operator`.
- **confluence-mcp:** `consultant`, `board`, `cdp` and `lightspeed_readonly` get SXSI, SXS, SXSD and SAC. The `"*"`
  entries of `sales`, `finance`, `adv` and `recrut` are gone.
- **git-forge-mcp:** `consultant`, `board` and `cdp` get `github:startxfr/*`. The same four `"*"` entries are gone.

## Golden path

22:41 to 22:42 UTC: `make demo golden-path` gave RESULT PASS. 14 moments passed and the world model was shown as
roadmap. The `tools` moment (consultant-01, `search_confluence "onboarding"`) found 7 pages.

## Allowed and refused calls

Each call went through the mcp-gateway REST path (`/v1/tools/<capability>/invoke`) with a `zuno-evaluations` token of
the persona, as agent `tekos`, task `answer-technical-question`, at class C2.

| Persona | Call | Result |
|---|---|---|
| consultant-01 | `search_confluence` "onboarding", space SXSI | 200, 7 pages, all in SXSI |
| consultant-01 | `search_confluence` "onboarding", space CDF (a customer space) | refused: "space 'CDF' is outside the space allowlist of the caller's groups (ADR-0603 M12)" |
| consultant-01 | `search_confluence` "OpenShift", no space | 200, pages from SXSI and SXSD only |
| consultant-01 | `git.repository.read` github startxfr/zuno-demo README.md | 200, the file |
| consultant-01 | `git.repository.read` github kubernetes/kubernetes README.md | refused: "repository 'github:kubernetes/kubernetes' is outside the repository allowlist of the caller's groups (ADR-0603 M12)" |
| ai-ops-01 | `metrics.query` `count(kube_pod_info{namespace="zuno-ai-run"})` | 200, 33 |
| ai-ops-01 | `metrics.query` `count(kube_pod_info{namespace="openshift-etcd"})` | 200, empty vector: the added matcher ANDs with the caller's own |
| ai-ops-01 | `metrics.query` `count by (namespace) (kube_pod_info)` | 200, exactly the 14 allowed namespaces (zuno-ai-build 219, zuno-ai-run 33, nvidia-gpu-operator 21, and so on) |

The gateway returns a refusal as HTTP 502 with the server's tool error, the same as any other tool error.

## Back out

Revert the values in `gitops/apps/mcp/application-d1.yaml`, `gitops/apps/mcp-confluence/application-d1.yaml` and
`gitops/apps/mcp-git-forge/application-d1.yaml`, then run `make d2 install mcp` again.
